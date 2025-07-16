```python
import os
import time
import json
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
import praw
import google.generativeai as genai
from llm_prompt import build_llm_prompt  # new import
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


with app.app_context():
    # initialize DB if it doesn't exist
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS posted_submissions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   submission_id TEXT UNIQUE NOT NULL,
                   timestamp REAL DEFAULT (strftime('%s','now'))
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS suggestions (
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
                 )''')
    conn.commit()
    conn.close()

# ─── Google LLM Setup ─────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    llm_model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    llm_model = None
    print("FATAL ERROR: GOOGLE_API_KEY not found.")

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
else:
    reddit_poster = None
    print("FATAL ERROR: Missing Reddit posting credentials.")


def extract_submission_id(permalink):
    # Extracts the ID from a Reddit URL
    parts = permalink.rstrip('/').split('/')
    if 'comments' in parts:
        idx = parts.index('comments')
        if len(parts) > idx + 1:
            return parts[idx + 1]
    return None

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/suggestions', methods=['GET'])
def get_suggestions():
    now = time.time()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT s.* FROM suggestions s
        LEFT JOIN posted_submissions p ON s.submission_id = p.submission_id
        WHERE p.submission_id IS NULL
    ''')
    rows = c.fetchall()
    conn.close()

    out = []
    for row in rows:
        age = now - row['added_at']
        window = 3*24*60*60 if row['subreddit'].lower() == "smpchat" else 24*60*60
        if age > window:
            continue
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


@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    data = request.json or {}
    sub_id = extract_submission_id(data.get("redditPostUrl",""))
    if not sub_id:
        return jsonify({"error":"Invalid Reddit URL"}), 400

    conn = get_db_connection()
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
    conn.close()
    return jsonify({"message":"Suggestion added","id":sub_id}), 201


@app.route('/suggestions/<submission_id>/generate', methods=['POST'])
def generate_comment_for_post(submission_id):
    if not llm_model:
        return jsonify({"error":"LLM not configured"}), 500

    data = request.json or {}
    user_thought = data.get('user_thought','')

    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute(
        'SELECT * FROM suggestions WHERE submission_id = ?',
        (submission_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error":"Post not found"}), 404

    # build prompt via our new helper
    prompt = build_llm_prompt(
        row['title'],
        row['selftext'],
        row['post_url'],
        json.loads(row['image_urls']),
        user_thought
    )

    try:
        resp = llm_model.generate_content(prompt)
        comment = getattr(resp, 'text', '').strip()
        if not comment:
            raise ValueError("Empty LLM response")

        conn = get_db_connection()
        conn.execute(
            'UPDATE suggestions SET suggested_comment = ? WHERE submission_id = ?',
            (comment, submission_id)
        )
        conn.commit()
        conn.close()

        return jsonify({"suggestedComment":comment, "id":submission_id})
    except Exception as e:
        return jsonify({"error":str(e)}), 500


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
        return jsonify({"error":str(e)}), 500

    now_ts = time.time()
    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO posted_submissions(submission_id, timestamp) VALUES(?,?)',
        (submission_id, now_ts)
    )
    conn.execute(
        'DELETE FROM suggestions WHERE submission_id = ?',
        (submission_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"message":"Comment posted and suggestion removed"})


@app.route('/suggestions/<submission_id>', methods=['DELETE'])
def reject_suggestion(submission_id):
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM suggestions WHERE submission_id = ?',
        (submission_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"message":"Suggestion rejected"})


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
        return jsonify({"error":str(e)}), 500

    now_ts = time.time()
    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO posted_submissions(submission_id, timestamp) VALUES(?,?)',
        (submission_id, now_ts)
    )
    conn.execute(
        'DELETE FROM suggestions WHERE submission_id = ?',
        (submission_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"message":"Posted direct comment and removed suggestion"})


if __name__ == '__main__':
    if not llm_model or not reddit_poster:
        print("--- CANNOT START: missing keys/creds ---")
    else:
        app.run(debug=True)
```
