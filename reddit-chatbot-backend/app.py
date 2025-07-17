import os
import time
import json
import sqlite3
import requests
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify
from flask_cors import CORS
import praw
from llm_prompt import build_llm_prompt
from dotenv import load_dotenv

# ─── Setup ──────────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Database file
DATABASE_FILE = 'bot_data.db'

# ─── Sitemap Integration ────────────────────────────────────────────────────
SITEMAP_URLS = [
    'https://scalpsusa.com/post-sitemap.xml',
    'https://scalpsusa.com/page-sitemap.xml'
]

def fetch_sitemap_urls():
    urls = []
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    for sitemap in SITEMAP_URLS:
        try:
            resp = requests.get(sitemap, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for loc in root.findall('.//ns:loc', ns):
                urls.append(loc.text)
        except requests.RequestException as e:
            app.logger.error(f"Failed to fetch sitemap {sitemap}: {e}")
    return urls

BLOG_URLS = fetch_sitemap_urls()
app.logger.info(f"Loaded {len(BLOG_URLS)} blog URLs.")

# ─── Database Helpers ───────────────────────────────────────────────────────
def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize tables
with app.app_context():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT UNIQUE NOT NULL,
            title TEXT,
            subreddit TEXT,
            selftext TEXT,
            post_url TEXT,
            image_urls TEXT,
            suggested_comment TEXT DEFAULT '',
            created_utc REAL,
            added_at REAL DEFAULT (strftime('%s','now'))
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS posted_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT UNIQUE NOT NULL,
            posted_at REAL DEFAULT (strftime('%s','now'))
        )
    ''')
    conn.commit()
    conn.close()

# ─── Google API Key and Model ───────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GENERATIVE_MODEL", "gemini-1.5-flash-latest")
REST_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# ─── Reddit Poster Setup ────────────────────────────────────────────────────
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
    app.logger.error("Reddit poster not configured; posting disabled.")

# ─── Routes ─────────────────────────────────────────────────────────────────
@app.route('/suggestions', methods=['GET'])
def list_suggestions():
    conn = get_db_connection()
    # Fetch all suggestions that haven't been posted yet
    rows = conn.execute('''
        SELECT s.* FROM suggestions s
        LEFT JOIN posted_submissions ps ON s.submission_id = ps.submission_id
        WHERE ps.submission_id IS NULL
        ORDER BY s.added_at DESC
    ''').fetchall()
    conn.close()

    # vvv THIS IS THE FIXED LOGIC vvv
    # Manually map the database columns to the expected frontend keys
    output_data = []
    for row in rows:
        output_data.append({
            "id": row['submission_id'],
            "redditPostTitle": row['title'],
            "subreddit": row['subreddit'],
            "redditPostSelftext": row['selftext'],
            "redditPostUrl": row['post_url'],
            "image_urls": json.loads(row['image_urls']),
            "suggestedComment": row['suggested_comment']
        })
    
    return jsonify(output_data)

@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    data = request.get_json() or {}
    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO suggestions (submission_id, title, subreddit, selftext, post_url, image_urls, created_utc) VALUES (?,?,?,?,?,?,?)',
        (
            data.get('submission_id'),
            data.get('redditPostTitle'),
            data.get('subreddit'),
            data.get('redditPostSelftext'),
            data.get('redditPostUrl'),
            json.dumps(data.get('image_urls', [])),
            time.time()
        )
    )
    conn.commit()
    conn.close()
    return jsonify({"message":"added"}), 201

@app.route('/suggestions/<submission_id>/generate', methods=['POST'])
def generate_comment(submission_id):
    if not GOOGLE_API_KEY:
        return jsonify({"error":"LLM not configured"}), 500
    data = request.get_json() or {}
    user_thought = data.get('user_thought','')
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM suggestions WHERE submission_id=?',(submission_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error":"not found"}), 404
    prompt = build_llm_prompt(row['title'], row['selftext'], row['post_url'], json.loads(row['image_urls']), user_thought, BLOG_URLS)
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(REST_ENDPOINT, params={"key": GOOGLE_API_KEY}, json=payload)
        resp.raise_for_status()
        result = resp.json()
        comment = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not comment: raise ValueError("Empty response from API")
        conn = get_db_connection()
        conn.execute('UPDATE suggestions SET suggested_comment=? WHERE submission_id=?',(comment,submission_id))
        conn.commit()
        conn.close()
        return jsonify({"suggestedComment": comment}), 200
    except Exception as e:
        app.logger.error(f"LLM generation failed for {submission_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/suggestions/<submission_id>/approve-and-post', methods=['POST'])
def approve_and_post(submission_id):
    if not reddit_poster:
        return jsonify({"error":"Reddit not configured"}), 500
    request_data = request.get_json() or {}
    comment_to_post = request_data.get("approved_comment")
    if not comment_to_post:
        return jsonify({"error": "No comment content provided."}), 400
    try:
        submission = reddit_poster.submission(id=submission_id)
        submission.reply(comment_to_post)
        conn = get_db_connection()
        conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)',(submission_id,))
        conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
        conn.commit()
        conn.close()
        return jsonify({"message":"posted"}), 200
    except Exception as e:
        app.logger.error(f"Failed to post to Reddit for {submission_id}: {e}")
        return jsonify({"error": f"Failed to post to Reddit: {str(e)}"}), 500

@app.route('/suggestions/<submission_id>/post-direct', methods=['POST'])
def post_direct(submission_id):
    if not reddit_poster:
        return jsonify({"error":"Reddit not configured"}), 500
    data = request.get_json() or {}
    comment = data.get('direct_comment','')
    if not comment:
        return jsonify({"error": "Cannot post an empty comment."}), 400
    try:
        submission = reddit_poster.submission(id=submission_id)
        submission.reply(comment)
        conn = get_db_connection()
        conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)',(submission_id,))
        conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
        conn.commit()
        conn.close()
        return jsonify({"message":"direct posted"}), 200
    except Exception as e:
        app.logger.error(f"Failed to post DIRECTLY to Reddit for {submission_id}: {e}")
        return jsonify({"error": f"Failed to post directly to Reddit: {str(e)}"}), 500

@app.route('/suggestions/<submission_id>', methods=['DELETE'])
def delete_suggestion(submission_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"deleted"}), 200

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)