import os
import time
import json
import sqlite3
import requests
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify
from flask_cors import CORS
import praw
import google.generativeai as genai
from llm_prompt import build_llm_prompt
from dotenv import load_dotenv

# ─── Setup ──────────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
# Allow all origins (adjust for production as needed)
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
        resp = requests.get(sitemap, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for loc in root.findall('.//ns:loc', ns):
            urls.append(loc.text)
    return urls

# Load blog links at startup
BLOG_URLS = fetch_sitemap_urls()
app.logger.info(f"Loaded {len(BLOG_URLS)} sitemap URLs.")

# ─── Database Helpers ──────────────────────────────────────────────────────
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
    # Seed a test suggestion if none exist (for debugging)
    existing = conn.execute('SELECT COUNT(*) as cnt FROM suggestions').fetchone()['cnt']
    if existing == 0:
        conn.execute(
            'INSERT OR IGNORE INTO suggestions (submission_id, title, subreddit, selftext, post_url, image_urls, created_utc) VALUES (?,?,?,?,?,?,?)',
            ('test123', 'My Test Post', 'r/test', 'Hello world', 'https://reddit.com/r/test/test123', '[]', time.time())
        )
        conn.commit()
    conn.close()

# ─── Google LLM Setup ───────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    llm_model = genai
else:
    llm_model = None
    app.logger.error("Missing GOOGLE_API_KEY.")

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
    app.logger.error("Missing Reddit credentials.")

# ─── Routes ─────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET'])
def health_check():
    return 'OK', 200

@app.route('/suggestions', methods=['GET'])
def list_suggestions():
    """
    Return all pending suggestions, mapped to front-end shape.
    """
    now = time.time()
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT * FROM suggestions'
    ).fetchall()
    conn.close()

    out = []
    for row in rows:
        # Skip if already posted
        posted = conn = get_db_connection(); posted_ids = [r['submission_id'] for r in conn.execute('SELECT submission_id FROM posted_submissions').fetchall()]; conn.close()
        if row['submission_id'] in posted_ids:
            continue
        out.append({
            "id": row['submission_id'],
            "redditPostTitle": row['title'],
            "subreddit": row['subreddit'],
            "redditPostSelftext": row['selftext'],
            "redditPostUrl": row['post_url'],
            "image_urls": json.loads(row['image_urls']),
            "suggestedComment": row['suggested_comment']
        })
    return jsonify(out)

@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    data = request.get_json() or {}
    sub = data.get('submission_id')
    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO suggestions (submission_id, title, subreddit, selftext, post_url, image_urls, created_utc) VALUES (?,?,?,?,?,?,?)',
        (
            sub,
            data.get('redditPostTitle') or data.get('title',''),
            data.get('subreddit',''),
            data.get('redditPostSelftext') or data.get('selftext',''),
            data.get('redditPostUrl')   or data.get('post_url',''),
            json.dumps(data.get('image_urls', [])),
            data.get('created_utc', time.time())
        )
    )
    conn.commit()
    conn.close()
    return jsonify({"message":"Suggestion added"}), 201

@app.route('/suggestions/<submission_id>/generate', methods=['POST'])
def generate_comment(submission_id):
    if not llm_model:
        return jsonify({"error":"LLM not configured"}), 500
    user_thought = request.json.get('user_thought','')
    conn = get_db_connection()
    row = conn.execute(
        'SELECT * FROM suggestions WHERE submission_id=?', (submission_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error":"Not found"}), 404

    prompt = build_llm_prompt(
        row['title'], row['selftext'], row['post_url'],
        json.loads(row['image_urls']), user_thought, BLOG_URLS
    )
    try:
        resp = genai.generate_text(model='gemini-1.5-flash-latest', prompt=prompt)
        comment = resp.text.strip()
        conn = get_db_connection()
        conn.execute(
            'UPDATE suggestions SET suggested_comment=? WHERE submission_id=?',
            (comment, submission_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"suggestedComment": comment})
    except Exception as e:
        app.logger.error(e)
        return jsonify({"error":"LLM failed"}), 500

@app.route('/suggestions/<submission_id>/approve-and-post', methods=['POST'])
def approve_and_post(submission_id):
    if not reddit_poster:
        return jsonify({"error":"Reddit not configured"}), 500
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM suggestions WHERE submission_id=?', (submission_id,)).fetchone()
    conn.close()
    if not row or not row['suggested_comment']:
        return jsonify({"error":"No comment to post"}), 400
    submission = reddit_poster.submission(id=submission_id)
    submission.reply(row['suggested_comment'])
    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)', (submission_id,))
    conn.execute('DELETE FROM suggestions WHERE submission_id=?', (submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"Posted"})

@app.route('/suggestions/<submission_id>', methods=['DELETE'])
def delete_suggestion(submission_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM suggestions WHERE submission_id=?', (submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"Deleted"})

@app.route('/suggestions/<submission_id>/post-direct', methods=['POST'])
def post_direct(submission_id):
    if not reddit_poster:
        return jsonify({"error":"Reddit not configured"}), 500
    comment = request.json.get('direct_comment','')
    submission = reddit_poster.submission(id=submission_id)
    submission.reply(comment)
    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)', (submission_id,))
    conn.execute('DELETE FROM suggestions WHERE submission_id=?', (submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"Direct posted"})

if __name__ == '__main__':
    app.run(debug=True)
