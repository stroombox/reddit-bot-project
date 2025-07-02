from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
import praw
import time
import sqlite3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- Database Configuration ---
DATABASE_FILE = 'bot_data.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posted_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT UNIQUE NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_name TEXT UNIQUE NOT NULL,
                setting_value TEXT
            )
        ''')
        conn.commit()
    print(f"Database initialized: {DATABASE_FILE}")

def load_prompt_from_file(file_path="llm_prompt.txt"):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"FATAL ERROR: Prompt file '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"FATAL ERROR: Could not read prompt file: {e}")
        return None

with app.app_context():
    init_db()

# --- Google Generative AI (LLM) Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    llm_model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    print("FATAL ERROR: GOOGLE_API_KEY not found in environment variables.")
    llm_model = None

# --- Load LLM Prompt from File ---
BASE_LLM_PROMPT_TEXT = load_prompt_from_file()
if not BASE_LLM_PROMPT_TEXT:
    print("ERROR: llm_prompt.txt not found. Using a basic fallback prompt.")
    BASE_LLM_PROMPT_TEXT = "Generate a short helpful comment for this Reddit post. Title: {post_title}. Body: {post_selftext}. User thought: {user_thought}"
else:
    print("Successfully loaded LLM prompt from llm_prompt.txt.")

# --- Reddit API Credentials (for posting) via refresh token ---
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.getenv("REDDIT_REFRESH_TOKEN")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT")

if all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_REFRESH_TOKEN, REDDIT_USER_AGENT]):
    reddit_poster = praw.Reddit(
        client_id     = REDDIT_CLIENT_ID,
        client_secret = REDDIT_CLIENT_SECRET,
        refresh_token = REDDIT_REFRESH_TOKEN,
        user_agent    = REDDIT_USER_AGENT
    )
    print("PRAW instance for posting configured with refresh token")
else:
    print("FATAL ERROR: Missing one or more Reddit posting credentials.")
    reddit_poster = None


# --- In-memory storage for posts ---
pending_suggestions = {}
suggestion_id_counter = 1

@app.route('/suggestions', methods=['GET'])
def get_suggestions():
    return jsonify(list(pending_suggestions.values()))

@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    global suggestion_id_counter
    data = request.json
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    
    new_suggestion = {
        "id": str(suggestion_id_counter),
        "redditPostTitle": data.get("redditPostTitle", "No Title"),
        "subreddit": data.get("subreddit", "Unknown"),
        "redditPostSelftext": data.get("redditPostSelftext", ""),
        "redditPostUrl": data.get("redditPostUrl", "#"),
        "suggestedComment": "",
        "image_urls": data.get("image_urls", []),
        "redditPostPermalink": data.get("redditPostUrl", "#")
    }
    pending_suggestions[new_suggestion['id']] = new_suggestion
    suggestion_id_counter += 1
    print(f"Received new post: {new_suggestion['redditPostTitle']} (ID: {new_suggestion['id']})")
    return jsonify({"message": "Raw post added", "id": new_suggestion['id']}), 201

@app.route('/suggestions/<suggestion_id>/generate', methods=['POST'])
def generate_comment_for_post(suggestion_id):
    if not llm_model:
        return jsonify({"error": "LLM not configured on server"}), 500
    if suggestion_id not in pending_suggestions:
        return jsonify({"error": "Post not found"}), 404
    post = pending_suggestions[suggestion_id]
    user_thought = request.json.get('user_thought', '')
    final_prompt = BASE_LLM_PROMPT_TEXT.format(
        post_title=post['redditPostTitle'],
        post_selftext=post.get('redditPostSelftext', "[No body content]"),
        post_url=post['redditPostUrl'],
        image_urls=', '.join(post.get('image_urls', [])) or "[No image URLs]",
        user_thought=user_thought
    )
    try:
        response = llm_model.generate_content(final_prompt)
        if hasattr(response, 'text') and response.text.strip():
            generated_comment = response.text.strip()
            post['suggestedComment'] = generated_comment
            print(f"Generated comment for post ID {suggestion_id}.")
            return jsonify({"suggestedComment": generated_comment, "id": suggestion_id})
        else:
            print(f"ERROR: LLM generated empty text for post ID {suggestion_id}.")
            return jsonify({"error": "Failed to generate comment", "details": "LLM output was empty"}), 500
    except Exception as e:
        print(f"ERROR: LLM generation failed for post ID {suggestion_id}: {e}")
        return jsonify({"error": f"Could not generate comment: {e}"}), 500

@app.route('/suggestions/<suggestion_id>/approve-and-post', methods=['POST'])
def approve_and_post_comment(suggestion_id):
    if not reddit_poster:
        return jsonify({"error": "Reddit poster not configured on server"}), 500
    if suggestion_id not in pending_suggestions:
        return jsonify({"error": "Post not found"}), 404

    request_data = request.get_json()
    edited_comment_content = request_data.get('approved_comment')

    if not edited_comment_content or not edited_comment_content.strip():
        return jsonify({"error": "Cannot post an empty comment"}), 400

    post_to_process = pending_suggestions.pop(suggestion_id)
    
    try:
        submission_id_str = post_to_process['redditPostPermalink'].split('/')[-3]
        submission = reddit_poster.submission(id=submission_id_str)
        submission.reply(edited_comment_content)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO posted_submissions (submission_id) VALUES (?)", (submission_id_str,))
            conn.commit()
        
        print(f"Successfully posted EDITED comment to Reddit post ID: {submission_id_str}")
        print(f"Comment content: {edited_comment_content}")
        return jsonify({"message": "Comment posted and suggestion processed"})
    except Exception as e:
        pending_suggestions[suggestion_id] = post_to_process
        print(f"ERROR: Failed to post comment to Reddit for ID {suggestion_id}: {e}")
        return jsonify({"error": f"Failed to post to Reddit: {e}"}), 500

@app.route('/suggestions/<suggestion_id>/post-direct', methods=['POST'])
def post_direct_comment(suggestion_id):
    if not reddit_poster:
        return jsonify({"error": "Reddit poster not configured on server"}), 500
    if suggestion_id not in pending_suggestions:
        return jsonify({"error": "Post not found"}), 404
    data = request.json
    direct_comment_content = data.get('direct_comment', '').strip()
    if not direct_comment_content:
        return jsonify({"error": "Direct comment content is empty"}), 400
    post_to_process = pending_suggestions.pop(suggestion_id)
    try:
        submission_id_str = post_to_process['redditPostPermalink'].split('/')[-3]
        submission = reddit_poster.submission(id=submission_id_str)
        submission.reply(direct_comment_content)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO posted_submissions (submission_id) VALUES (?)", (submission_id_str,))
            conn.commit()
        print(f"Successfully posted DIRECT comment to Reddit post ID: {submission_id_str}")
        return jsonify({"message": "Direct comment posted and suggestion processed"})
    except Exception as e:
        pending_suggestions[suggestion_id] = post_to_process
        print(f"ERROR: Failed to post DIRECT comment to Reddit for ID {suggestion_id}: {e}")
        return jsonify({"error": f"Failed to post directly to Reddit: {e}"}), 500

@app.route('/suggestions/<suggestion_id>', methods=['DELETE'])
def handle_reject_action(suggestion_id):
    if suggestion_id in pending_suggestions:
        pending_suggestions.pop(suggestion_id)
        print(f"Suggestion {suggestion_id} rejected and removed.")
        return jsonify({"message": "Suggestion rejected"})
    return jsonify({"error": "Suggestion not found"}), 404

if __name__ == '__main__':
    if not all([llm_model, reddit_poster]):
        print("\n--- APPLICATION CANNOT START ---")
        print("One or more critical API keys or credentials are missing from your .env file.")
    else:
        app.run(debug=True)