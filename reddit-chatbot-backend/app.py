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

load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
DATABASE_FILE = 'bot_data.db'

# region Sitemap Integration
SITEMAP_URLS = ['https://scalpsusa.com/post-sitemap.xml', 'https://scalpsusa.com/page-sitemap.xml']
def fetch_sitemap_urls():
    urls = []
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    for sitemap in SITEMAP_URLS:
        try:
            resp = requests.get(sitemap, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            urls.extend(loc.text for loc in root.findall('.//ns:loc', ns))
        except requests.RequestException as e:
            app.logger.error(f"Failed to fetch sitemap {sitemap}: {e}")
    return urls
BLOG_URLS = fetch_sitemap_urls()
app.logger.info(f"Loaded {len(BLOG_URLS)} blog URLs.")
# endregion

# region Database
def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

with app.app_context():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id TEXT UNIQUE NOT NULL,
            title TEXT, subreddit TEXT, author TEXT, selftext TEXT, post_url TEXT,
            image_urls TEXT, suggested_comment TEXT DEFAULT '', created_utc REAL,
            added_at REAL DEFAULT (strftime('%s','now'))
        )
    ''')
    try:
        c.execute("ALTER TABLE suggestions ADD COLUMN author TEXT")
    except sqlite3.OperationalError:
        pass # Column already exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS posted_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id TEXT UNIQUE NOT NULL,
            posted_at REAL DEFAULT (strftime('%s','now'))
        )
    ''')
    conn.commit()
    conn.close()
# endregion

# region API Clients
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GENERATIVE_MODEL", "gemini-1.5-flash-latest")
REST_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

reddit_poster = None
if all(os.getenv(k) for k in ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_REFRESH_TOKEN", "REDDIT_USER_AGENT"]):
    reddit_poster = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"), client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        refresh_token=os.getenv("REDDIT_REFRESH_TOKEN"), user_agent=os.getenv("REDDIT_USER_AGENT")
    )
else:
    app.logger.error("Reddit poster not configured; posting disabled.")
# endregion

# region Routes
@app.route('/suggestions', methods=['GET'])
def list_suggestions():
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT s.* FROM suggestions s LEFT JOIN posted_submissions ps 
        ON s.submission_id = ps.submission_id WHERE ps.submission_id IS NULL
        ORDER BY s.added_at DESC
    ''').fetchall()
    conn.close()
    
    output_data = [{
        "id": r['submission_id'], "redditPostTitle": r['title'], "subreddit": r['subreddit'],
        "author": r['author'], "redditPostSelftext": r['selftext'], "redditPostUrl": r['post_url'],
        "image_urls": json.loads(r['image_urls']), "suggestedComment": r['suggested_comment']
    } for r in rows]
    return jsonify(output_data)

@app.route('/suggestions', methods=['POST'])
def add_suggestion():
    data = request.get_json() or {}
    conn = get_db_connection()
    conn.execute(
        'INSERT OR IGNORE INTO suggestions (submission_id, title, subreddit, author, selftext, post_url, image_urls, created_utc) VALUES (?,?,?,?,?,?,?,?)',
        (data.get('submission_id'), data.get('redditPostTitle'), data.get('subreddit'), data.get('author'),
         data.get('redditPostSelftext'), data.get('redditPostUrl'), json.dumps(data.get('image_urls', [])), time.time())
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "added"}), 201

@app.route('/suggestions/<submission_id>/generate', methods=['POST'])
def generate_comment(submission_id):
    if not GOOGLE_API_KEY: return jsonify({"error":"LLM not configured"}), 500
    data, conn = request.get_json() or {}, get_db_connection()
    row = conn.execute('SELECT * FROM suggestions WHERE submission_id=?',(submission_id,)).fetchone()
    conn.close()
    if not row: return jsonify({"error":"not found"}), 404
    prompt = build_llm_prompt(row['title'], row['selftext'], row['post_url'], json.loads(row['image_urls']), data.get('user_thought',''), BLOG_URLS)
    try:
        resp = requests.post(REST_ENDPOINT, params={"key": GOOGLE_API_KEY}, json={"contents": [{"parts": [{"text": prompt}]}]})
        resp.raise_for_status()
        comment = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not comment: raise ValueError("Empty response from API")
        conn = get_db_connection()
        conn.execute('UPDATE suggestions SET suggested_comment=? WHERE submission_id=?',(comment,submission_id))
        conn.commit()
        conn.close()
        return jsonify({"suggestedComment": comment})
    except Exception as e:
        app.logger.error(f"LLM generation failed for {submission_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/suggestions/<submission_id>/approve-and-post', methods=['POST'])
def approve_and_post(submission_id):
    if not reddit_poster: return jsonify({"error":"Reddit not configured"}), 500
    comment = (request.get_json() or {}).get("approved_comment")
    if not comment: return jsonify({"error": "No comment content provided."}), 400
    try:
        reddit_poster.submission(id=submission_id).reply(comment)
        conn = get_db_connection()
        conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)',(submission_id,))
        conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
        conn.commit()
        conn.close()
        return jsonify({"message":"posted"})
    except Exception as e:
        app.logger.error(f"Failed to post to Reddit for {submission_id}: {e}")
        return jsonify({"error": f"Failed to post to Reddit: {str(e)}"}), 500

@app.route('/suggestions/<submission_id>/post-direct', methods=['POST'])
def post_direct(submission_id):
    if not reddit_poster: return jsonify({"error":"Reddit not configured"}), 500
    comment = (request.get_json() or {}).get('direct_comment','')
    if not comment: return jsonify({"error": "Cannot post an empty comment."}), 400
    try:
        reddit_poster.submission(id=submission_id).reply(comment)
        conn = get_db_connection()
        conn.execute('INSERT OR IGNORE INTO posted_submissions (submission_id) VALUES (?)',(submission_id,))
        conn.execute('DELETE FROM suggestions WHERE submission_id=?',(submission_id,))
        conn.commit()
        conn.close()
        return jsonify({"message":"direct posted"})
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
# endregion

if __name__=='__main__':
    app.run(host='0.0.0.0', port