import requests
import xml.etree.ElementTree as ET
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
        # (existing table creation code)
        conn.commit()

with app.app_context():
    init_db()

# ─── 1) Load & parse SMP blog sitemap(s) ────────────────────────────────────
SITEMAP_URLS = [
    "https://scalpsusa.com/post-sitemap.xml",
    "https://scalpsusa.com/page-sitemap.xml",
]
sitemap_links = []

def load_sitemaps():
    global sitemap_links
    sitemap_links = []
    for url in SITEMAP_URLS:
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            # XML namespace handling
            namespace = {'ns': root.tag.split('}')[0].strip('{')}
            for loc in root.findall('.//ns:loc', namespace):
                sitemap_links.append(loc.text)
        except Exception as e:
            print(f"Warning: failed to load sitemap {url}: {e}")
    print(f"Loaded {len(sitemap_links)} sitemap URLs.")

# Load on startup
load_sitemaps()

# ─── Google LLM Setup ─────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# (existing LLM setup)

# ─── Reddit Poster Setup ──────────────────────────────────────────────────────
# (existing PRAW setup)

# ─── Remaining Flask routes unchanged ────────────────────────────────────────
# purge_expired_suggestions, get_suggestions, add_suggestion, generate, approve, reject, post_direct
# (unchanged code)
if __name__ == '__main__':
    if not GOOGLE_API_KEY or not os.getenv("REDDIT_CLIENT_ID"):
        print("\n--- CANNOT START: missing keys/creds ---")
    else:
        app.run(debug=True)
