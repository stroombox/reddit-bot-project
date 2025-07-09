from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
import praw
import time
import sqlite3
import json
from dotenv import load_dotenv

# ─── Setup ────────────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
CORS(app)
DATABASE_FILE = 'bot_data.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        # Already-posted table
        c.execute('''
            CREATE TABLE IF NOT EXISTS posted_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT UNIQUE NOT NULL,
                timestamp REAL DEFAULT (strftime('%s','now'))
            )
        ''')
        # Suggestions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT UNIQUE NOT NULL,
                title TEXT,
                subreddit TEXT,
                selftext TEXT,
                post_url TEXT,
                image_urls TEXT,
                created_utc REAL,
                suggested_comment TEXT DEFAULT '',
                added_at REAL DEFAULT (strftime('%s','now'))
            )
        ''')
        # Settings table (unchanged)
        c.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_name TEXT UNIQUE NOT NULL,
                setting_value TEXT
            )
        ''')
        conn.commit()
    print(f"Database initialized: {DATABASE_FILE}")

with app.app_context():
    init_db()

# ─── Google LLM Setup ─────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    llm_model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    print("FATAL ERROR: GOOGLE_API_KEY not found.")
    llm_model = None

# ─── Reddit Poster Setup ──────────────────────────────────────────────────────
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
    print("PRAW poster configured with refresh token")
else:
    print("FATAL ERROR: Missing Reddit posting credentials.")
    reddit_poster = None

# ─── Helper: Extract submission ID from permalink ─────────────────────────────
def extract_submission_id(permalink):
    # permalink looks like "https://reddit.com/r/xxx/comments/ID/slug"
    parts = permalink.rstrip('/').split('/')
    # The ID is always after 'comments'
    if 'comments' in parts:
        idx = parts.index('comments')
        if len(parts) > idx + 1:
            return parts[idx + 1]
    return None

# ─── Purge expired suggestions (call once daily from cron or manually) ────────
@app.route('/purge_expired_suggestions', methods=['POST'])
def purge_expired_suggestions():
    now = time.time()
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM suggestions WHERE subreddit="smpchat" AND (? - added_at) > ?', (now, 3*24*60*60))
        c.execute('DELETE FROM suggestions WHERE subreddit!="smpchat" AND (? - added_at) > ?', (now, 24*60*60))
        conn.commit()
    print("Purged expired suggestions")
    return jsonify({"message":"Expired suggestions purged"}), 200

# ─── 1) List suggestions (NO DELETE HERE) ─────────────────────────────────────
@app.route('/suggestions', methods=['GET'])
def get_suggestions():
    now = time.time()
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT s.* FROM suggestions s
            LEFT JOIN posted_submissions p
              ON s.submission_id = p.submission_id
            WHERE p.submission_id IS NULL
        ''')
        rows = c.fetchall()

    out = []
    for row in rows:
        age = now - row['added_at']
        window = 3*24*60*60 if row['subreddit'].lower() == "smpchat" else 24*60*60
        if age > window:
            continue  # Do not delete, just don't return
        out.append({
            "id":              row['submission_id'],
            "redditPostTitle": row['title'],
            "subreddit":       row['subreddit'],
            "redditPostSelftext": row['selftext'],
            "redditPostUrl":   row['post_url'],
            "image_urls":      json.loads(row['image_urls']),
            "suggestedComment": row['suggested_comment']
        })

    return jsonify(out)

# ─── 2) Add a new suggestion (called by your scraper) ────────────────────────
@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    data = request.json or {}
    sub_id = extract_submission_id(data.get("redditPostUrl",""))
    if not sub_id:
        return jsonify({"error":"Invalid Reddit URL"}), 400

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO suggestions
            (submission_id, title, subreddit, selftext, post_url, image_urls, created_utc)
            VALUES (?,?,?,?,?,?,?)
        ''', (
            sub_id,
            data.get("redditPostTitle",""),
            data.get("subreddit",""),
            data.get("redditPostSelftext",""),
            data.get("redditPostUrl",""),
            json.dumps(data.get("image_urls",[])),
            time.time()
        ))
        conn.commit()

    print(f"Added suggestion {sub_id}")
    return jsonify({"message":"Suggestion added","id":sub_id}), 201

# ─── 3) Generate LLM comment ─────────────────────────────────────────────────
BASE_LLM_PROMPT_TEXT = """You are a Reddit bot. Analyze the following post and the user's thoughts, then provide a helpful, concise comment.
Title: {post_title}
Text: {post_selftext}
Images: {image_urls}
User thoughts: {user_thought}
"""

@app.route('/suggestions/<submission_id>/generate', methods=['POST'])
def generate_comment_for_post(submission_id):
    if not llm_model:
        return jsonify({"error":"LLM not configured"}), 500

    data = request.json or {}
    with get_db_connection() as conn:
        c = conn.cursor()
        row = c.execute(
            'SELECT * FROM suggestions WHERE submission_id = ?',
            (submission_id,)
        ).fetchone()
    if not row:
        return jsonify({"error":"Post not found"}), 404

    user_thought = data.get('user_thought','')
    final_prompt = BASE_LLM_PROMPT_TEXT.format(
        post_title   = row['title'],
        post_selftext= row['selftext'] or "[No body content]",
        image_urls   = ','.join(json.loads(row['image_urls'])) or "[No images]",
        user_thought = user_thought
    )

    try:
        response = llm_model.generate_content(final_prompt)
        comment = response.text.strip() if hasattr(response, 'text') else ''
        if not comment:
            raise ValueError("Empty LLM response")

        with get_db_connection() as conn:
            conn.execute(
                'UPDATE suggestions SET suggested_comment = ? WHERE submission_id = ?',
                (comment, submission_id)
            )
            conn.commit()

        print(f"Generated comment for {submission_id}")
        return jsonify({"suggestedComment":comment,"id":submission_id})
    except Exception as e:
        print(f"LLM error for {submission_id}: {e}")
        return jsonify({"error":str(e)}), 500

# ─── 4) Approve & post comment to Reddit ─────────────────────────────────────
@app.route('/suggestions/<submission_id>/approve-and-post', methods=['POST'])
def approve_and_post_comment(submission_id):
    data = request.get_json() or {}
    comment_text = data.get('approved_comment','').strip()
    if not comment_text:
        return jsonify({"error":"Cannot post empty comment"}), 400
    if not reddit_poster:
        return jsonify({"error":"Reddit poster not configured"}), 500

    try:
        submission = reddit_poster.submission(id=submission_id)
        submission.reply(comment_text)
    except Exception as e:
        print(f"Reddit post error for {submission_id}: {e}")
        return jsonify({"error":str(e)}), 500

    now = time.time()
    with get_db_connection() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO posted_submissions(submission_id, timestamp) VALUES(?,?)',
            (submission_id, now)
        )
        conn.execute(
            'DELETE FROM suggestions WHERE submission_id = ?',
            (submission_id,)
        )
        conn.commit()

    print(f"Posted and removed suggestion {submission_id}")
    return jsonify({"message":"Comment posted and suggestion removed"})

# ─── 5) Reject without posting ───────────────────────────────────────────────
@app.route('/suggestions/<submission_id>', methods=['DELETE'])
def reject_suggestion(submission_id):
    with get_db_connection() as conn:
        conn.execute(
            'DELETE FROM suggestions WHERE submission_id = ?',
            (submission_id,)
        )
        conn.commit()
    print(f"Rejected suggestion {submission_id}")
    return jsonify({"message":"Suggestion rejected"})

# ─── 6) Direct post without LLM ─────────────────────────────────────────────
@app.route('/suggestions/<submission_id>/post-direct', methods=['POST'])
def post_direct_comment(submission_id):
    data = request.get_json() or {}
    text = data.get('direct_comment','').strip()
    if not text:
        return jsonify({"error":"Empty direct comment"}), 400
    if not reddit_poster:
        return jsonify({"error":"Reddit poster not configured"}), 500

    try:
        submission = reddit_poster.submission(id=submission_id)
        submission.reply(text)
    except Exception as e:
        print(f"Direct post error for {submission_id}: {e}")
        return jsonify({"error":str(e)}), 500

    now = time.time()
    with get_db_connection() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO posted_submissions(submission_id, timestamp) VALUES(?,?)',
            (submission_id, now)
        )
        conn.execute(
            'DELETE FROM suggestions WHERE submission_id = ?',
            (submission_id,)
        )
        conn.commit()

    print(f"Direct-posted and removed suggestion {submission_id}")
    return jsonify({"message":"Posted direct comment and removed suggestion"})

# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not llm_model or not reddit_poster:
        print("\n--- CANNOT START: missing keys/creds ---")
    else:
        app.run(debug=True)
