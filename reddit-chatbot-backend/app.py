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

# ─── Google API Key and Model (UPDATED) ──────────────────────────────────
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

# ─── Utility ────────────────────────────────────────────────────────────────
def extract_submission_id(permalink):
    parts = permalink.rstrip('/').split('/')
    if 'comments' in parts:
        idx = parts.index('comments')
        if len(parts) > idx + 1:
            return parts[idx + 1]
    return None

# ─── Routes ─────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET'])
def health():
    return jsonify({"status":"ok"}), 200

@app.route('/suggestions', methods=['GET'])
def list_suggestions():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM suggestions').fetchall()
    posted = {r['submission_id'] for r in conn.execute('SELECT submission_id FROM posted_submissions').fetchall()}
    conn.close()

    out = []
    for r in rows:
        if r['submission_id'] in posted:
            continue
        out.append({
            "id": r['submission_id'],
            "redditPostTitle": r['title'],
            "subreddit": r['subreddit'],
            "redditPostSelftext": r['selftext'],
            "redditPostUrl": r['post_url'],
            "image_urls": json.loads(r['image_urls']),
            "suggestedComment": r['suggested_comment']
        })
    return jsonify(out)

@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    data = request.get_json() or {}
    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO suggestions (submission_id, title, subreddit, selftext, post_url, image_urls, created_utc) VALUES (?,?,?,?,?,?,?)',
        (
            data.get('submission_id'),
            data.get('redditPostTitle') or data.get('title',''),
            data.get('subreddit',''),
            data.get('redditPostSelftext') or data.get('selftext',''),
            data.get('redditPostUrl') or data.get('post_url',''),
            json.dumps(data.get('image_urls', [])),
            data.get('created_utc', time.time())
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

    prompt = build_llm_prompt(
        row['title'], row['selftext'], row['post_url'],
        json.loads(row['image_urls']), user_thought, BLOG_URLS
    )
    app.logger.debug(f"Prompt for {submission_id}: {prompt}")

    # --- PAYLOAD AND RESPONSE PARSING UPDATED ---
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        resp = requests.post(
            REST_ENDPOINT,
            headers={"Content-Type":"application/json"},
            params={"key": GOOGLE_API_KEY},
            json=payload
        )
        resp.raise_for_status()
        result = resp.json()
        
        candidates = result.get("candidates", [])
        if not candidates or "content" not in candidates[0] or "parts" not in candidates[0]["content"]:
            raise ValueError("Invalid or empty response from generative API")
            
        comment = candidates[0]["content"]["parts"][0].get("text", "").strip()
        if not comment:
            raise ValueError("Empty text in response from generative API")

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
        conn = get_db_connection()
        row = conn.execute('SELECT suggested_comment FROM suggestions WHERE submission_id=?',(submission_id,)).fetchone()
        conn.close()
        if not row or not row['suggested_comment']:
             return jsonify({"error":"nothing to post"}), 400
        comment_to_post = row['suggested_comment']

    submission = reddit_poster.submission(id=submission_id)
    submission.reply(comment_to_post)

    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)',(submission_id,))
    conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"posted"}), 200

@app.route('/suggestions/<submission_id>', methods=['DELETE'])
def delete_suggestion(submission_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"deleted"}), 200

@app.route('/suggestions/<submission_id>/post-direct', methods=['POST'])
def post_direct(submission_id):
    if not reddit_poster:
        return jsonify({"error":"Reddit not configured"}), 500
    data = request.get_json() or {}
    comment = data.get('direct_comment','')
    submission = reddit_poster.submission(id=submission_id)
    submission.reply(comment)

    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)',(submission_id,))
    conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"direct posted"}), 200

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)