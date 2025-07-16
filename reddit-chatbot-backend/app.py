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
CORS(app)

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

# Load blog URLs once at startup
BLOG_URLS = fetch_sitemap_urls()
app.logger.info(f"Loaded {len(BLOG_URLS)} sitemap URLs.")

# ─── Database Helpers ──────────────────────────────────────────────────────
def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database tables
with app.app_context():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS posted_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT UNIQUE NOT NULL,
            timestamp REAL DEFAULT (strftime('%s','now'))
        )
    ''')
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
    conn.commit()
    conn.close()

# ─── Google LLM Setup ───────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    llm_model = genai
else:
    llm_model = None
    app.logger.error("FATAL ERROR: Missing Google API key for LLM.")

# ─── Reddit Poster Setup ────────────────────────────────────────────────────
REDDIT_CLIENT_ID      = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET  = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN  = os.getenv("REDDIT_REFRESH_TOKEN")
REDDIT_USER_AGENT     = os.getenv("REDDIT_USER_AGENT")

if all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_REFRESH_TOKEN, REDDIT_USER_AGENT]):
    reddit_poster = praw.Reddit(
        client_id     = REDDIT_CLIENT_ID,
        client_secret = REDDIT_CLIENT_SECRET,
        refresh_token = REDDIT_REFRESH_TOKEN,
        user_agent    = REDDIT_USER_AGENT
    )
else:
    reddit_poster = None
    app.logger.error("FATAL ERROR: Missing Reddit posting credentials.")

# ─── Routes ─────────────────────────────────────────────────────────────────
@app.route('/suggestions', methods=['GET'])
def list_suggestions():
    conn = get_db_connection()
    suggestions = conn.execute('SELECT * FROM suggestions').fetchall()
    conn.close()
    return jsonify([dict(row) for row in suggestions])

@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    data = request.json or {}
    sub = data.get('submission_id')
    title = data.get('title')
    subreddit = data.get('subreddit')
    selftext = data.get('selftext')
    url = data.get('post_url')
    images = json.dumps(data.get('image_urls', []))
    created = data.get('created_utc', time.time())

    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO suggestions (submission_id, title, subreddit, selftext, post_url, image_urls, created_utc) VALUES (?,?,?,?,?,?,?)',
        (sub, title, subreddit, selftext, url, images, created)
    )
    conn.commit()
    conn.close()
    return jsonify({"message":"Suggestion added"}), 201

@app.route('/suggestions/<submission_id>/generate', methods=['POST'])
def generate_comment_for_post(submission_id):
    if not llm_model:
        return jsonify({"error":"LLM not configured"}), 500
    data = request.json or {}
    user_thought = data.get('user_thought', '')

    conn = get_db_connection()
    row = conn.execute(
        'SELECT * FROM suggestions WHERE submission_id = ?',
        (submission_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error":"Post not found"}), 404

    # Build prompt including blog URLs
    prompt = build_llm_prompt(
        row['title'],
        row['selftext'],
        row['post_url'],
        json.loads(row['image_urls']),
        user_thought,
        BLOG_URLS
    )

    try:
        response = genai.generate_text(
            model='gemini-1.5-flash-latest',
            prompt=prompt
        )
        comment = response.text.strip()
        if not comment:
            raise ValueError("Empty LLM response")

        conn = get_db_connection()
        conn.execute(
            'UPDATE suggestions SET suggested_comment = ? WHERE submission_id = ?',
            (comment, submission_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"suggested_comment": comment})

    except Exception as e:
        app.logger.error(f"LLM error: {e}")
        return jsonify({"error":"LLM generation failed"}), 500

@app.route('/suggestions/<submission_id>/approve', methods=['POST'])
def approve_and_post(submission_id):
    data = request.json or {}
    subreddit = data.get('subreddit')
    if not reddit_poster:
        return jsonify({"error":"Reddit poster not configured"}), 500

    conn = get_db_connection()
    row = conn.execute(
        'SELECT * FROM suggestions WHERE submission_id = ?',
        (submission_id,)
    ).fetchone()

    if not row or not row['suggested_comment']:
        conn.close()
        return jsonify({"error":"No comment to post"}), 400

    submission = reddit_poster.submission(id=submission_id)
    submission.reply(row['suggested_comment'])

    now_ts = time.time()
    conn.execute(
        'INSERT OR IGNORE INTO posted_submissions (submission_id, timestamp) VALUES (?,?)',
        (submission_id, now_ts)
    )
    conn.execute('DELETE FROM suggestions WHERE submission_id = ?', (submission_id,))
    conn.commit()
    conn.close()

    return jsonify({"message":"Posted comment and removed suggestion"})

@app.route('/suggestions/<submission_id>/reject', methods=['POST'])
def reject_suggestion(submission_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM suggestions WHERE submission_id = ?', (submission_id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"Suggestion rejected"})

@app.route('/post_direct', methods=['POST'])
def post_direct():
    data = request.json or {}
    submission_id = data['submission_id']
    comment = data['comment']
    subreddit = data.get('subreddit')
    if not reddit_poster:
        return jsonify({"error":"Reddit poster not configured"}), 500

    submission = reddit_poster.submission(id=submission_id)
    submission.reply(comment)

    conn = get_db_connection()
    now_ts = time.time()
    conn.execute(
        'INSERT OR IGNORE INTO posted_submissions (submission_id, timestamp) VALUES (?,?)',
        (submission_id, now_ts)
    )
    conn.execute('DELETE FROM suggestions WHERE submission_id = ?', (submission_id,))
    conn.commit()
    conn.close()

    return jsonify({"message":"Posted direct comment and removed suggestion"})

if __name__ == '__main__':
    if not llm_model or not reddit_poster:
        app.logger.error("Cannot start server: missing configuration.")
    else:
        app.run(debug=True)
