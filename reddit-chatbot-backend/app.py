# app.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
import praw
import time
import sqlite3
import json
from dotenv import load_dotenv

# **NEW IMPORT**
from llm_prompt import build_llm_prompt

# ─── Setup ────────────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
CORS(app)
DATABASE_FILE = 'bot_data.db'
# … your db init code here …

# ─── Google LLM Setup ─────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# … your LLM config code here …

# ─── Reddit Poster Setup ──────────────────────────────────────────────────────
# … your PRAW config here …

# ─── Helper function extract_submission_id … (unchanged) …

# ─── Purge expired suggestions … (unchanged) …

# ─── 1) List suggestions … (unchanged) …

# ─── 2) Add a new suggestion … (unchanged) …

# ─── 3) Generate LLM comment ─────────────────────────────────────────────────
@app.route('/suggestions/<submission_id>/generate', methods=['POST'])
def generate_comment_for_post(submission_id):
    if not llm_model:
        return jsonify({"error":"LLM not configured"}), 500

    data = request.json or {}
    user_thought = data.get('user_thought', '')

    # fetch the post from your DB
    with get_db_connection() as conn:
        c = conn.cursor()
        row = c.execute(
            'SELECT * FROM suggestions WHERE submission_id = ?',
            (submission_id,)
        ).fetchone()
    if not row:
        return jsonify({"error":"Post not found"}), 404

    # **BUILD THE FULL PROMPT** using our new module
    final_prompt = build_llm_prompt(
        post_title    = row['title'],
        post_selftext = row['selftext'],
        post_url      = row['post_url'],
        image_urls    = json.loads(row['image_urls']),
        user_thought  = user_thought
    )

    try:
        response = llm_model.generate_content(final_prompt)
        comment = response.text.strip() if hasattr(response, 'text') else ''
        if not comment:
            raise ValueError("Empty LLM response")

        # save it back to the DB
        with get_db_connection() as conn:
            conn.execute(
                'UPDATE suggestions SET suggested_comment = ? WHERE submission_id = ?',
                (comment, submission_id)
            )
            conn.commit()

        return jsonify({"suggestedComment": comment, "id": submission_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── 4) Approve & post comment … (unchanged) …

# ─── 5) Reject suggestion … (unchanged) …

# ─── 6) Direct post comment … (unchanged) …

if __name__ == '__main__':
    if not llm_model or not reddit_poster:
        print("\n--- CANNOT START: missing keys/creds ---")
    else:
        app.run(debug=True)
