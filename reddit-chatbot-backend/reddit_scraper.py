import os
import time
from dotenv import load_dotenv
import praw
import requests
import sqlite3

# Load environment variables
load_dotenv()

# --- Configuration ---
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.getenv("REDDIT_REFRESH_TOKEN")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT")
FLASK_BACKEND_URL    = os.getenv("FLASK_BACKEND_URL", "").strip().rstrip('/')

if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_REFRESH_TOKEN, REDDIT_USER_AGENT, FLASK_BACKEND_URL]):
    print("❌ Missing required environment variables – exiting.")
    exit(1)

SUGGESTIONS_URL = FLASK_BACKEND_URL if FLASK_BACKEND_URL.endswith('/suggestions') else f"{FLASK_BACKEND_URL}/suggestions"

# --- PRAW Setup ---
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    refresh_token=REDDIT_REFRESH_TOKEN,
    user_agent=REDDIT_USER_AGENT
)
BOT_USERNAME = reddit.user.me().name.lower()

KEYWORDS = ["smp", "hair", "scalp", "bald", "follicle", "loss", "density", "microblading", "tattoo", "pigmentation", "hairline", "scar", "scars"]

def get_posted_submission_ids():
    posted_ids = set()
    try:
        db_path = os.environ.get("DB_PATH", "bot_data.db")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS posted_submissions (submission_id TEXT UNIQUE NOT NULL)")
            cursor.execute("SELECT submission_id FROM posted_submissions")
            posted_ids.update(row[0] for row in conn.cursor().fetchall())
        print(f"Found {len(posted_ids)} previously posted submission IDs.")
    except Exception as e:
        print(f"Error getting posted IDs: {e}")
    return posted_ids

def get_new_smp_posts(subreddit_name: str, limit: int = 25) -> list:
    now = time.time()
    window = 3*24*60*60 if subreddit_name.lower() == "smpchat" else 24*60*60
    cutoff = now - window
    new_posts, posted_ids = [], get_posted_submission_ids()

    for sub in reddit.subreddit(subreddit_name).new(limit=limit):
        if sub.created_utc < cutoff or sub.id in posted_ids:
            continue
        
        title_text, body_text = sub.title.lower(), sub.selftext.lower()
        if subreddit_name.lower() != "smpchat" and not any(k in title_text or k in body_text for k in KEYWORDS):
            continue
            
        sub.comments.replace_more(limit=0)
        if any(c.author and c.author.name.lower() == BOT_USERNAME for c in sub.comments.list()):
            print(f" - Skipping '{sub.title}' (already commented manually).")
            continue

        images = []
        if hasattr(sub, "gallery_data") and sub.gallery_data:
            for item in sub.gallery_data.get("items", []):
                media_id = item.get("media_id")
                if media_id in sub.media_metadata:
                    images.append(sub.media_metadata[media_id].get("s", {}).get("u"))
        elif not sub.is_self and sub.url.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
            images.append(sub.url)

        print(f"✅ Found relevant post: {sub.title}")
        new_posts.append({
            "submission_id":      sub.id,
            "redditPostTitle":    sub.title,
            "author":             sub.author.name if sub.author else "N/A",  # <-- ADDED THIS LINE
            "subreddit":          sub.subreddit.display_name,
            "redditPostSelftext": sub.selftext,
            "redditPostUrl":      f"https://reddit.com{sub.permalink}",
            "image_urls":         [img for img in images if img]
        })
    return new_posts

if __name__ == "__main__":
    subs_to_scrape = ["SMPchat", "Hairloss", "bald", "tressless"]
    for s in subs_to_scrape:
        posts = get_new_smp_posts(s, limit=50)
        print(f"Fetched {len(posts)} new from r/{s}")
        for post in posts:
            try:
                resp = requests.post(SUGGESTIONS_URL, json=post, timeout=10)
                resp.raise_for_status()
                print(f"✅ Sent {post['submission_id']}: {post['redditPostTitle']}")
            except Exception as e:
                print(f"❌ Failed to send {post['submission_id']}: {e}")