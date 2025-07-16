import os
import time
from dotenv import load_dotenv
import praw
import requests

# Load environment variables from .env (skipped in production if absent)
load_dotenv()

# Environment configuration
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.getenv("REDDIT_REFRESH_TOKEN")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT")
FLASK_BACKEND_URL    = os.getenv("FLASK_BACKEND_URL", "").rstrip('/')

# Validate configuration
required_vars = [
    "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
    "REDDIT_REFRESH_TOKEN", "REDDIT_USER_AGENT",
    "FLASK_BACKEND_URL"
]
missing = [v for v in required_vars if not globals().get(v)]
if missing:
    print(f"❌ Missing required environment variables: {', '.join(missing)} – exiting.")
    exit(1)

# Initialize Reddit client
reddit = praw.Reddit(
    client_id     = REDDIT_CLIENT_ID,
    client_secret = REDDIT_CLIENT_SECRET,
    refresh_token = REDDIT_REFRESH_TOKEN,
    user_agent    = REDDIT_USER_AGENT
)

# Bot username to skip its own comments
BOT_USERNAME = reddit.user.me().name.lower()

# Keywords to filter relevant SMP posts
KEYWORDS = [
    "smp","hair","scalp","bald","follicle","loss","density",
    "microblading","tattoo","pigmentation","hairline","scar","scars"
]


def get_new_smp_posts(subreddit_name: str, limit: int = 25) -> list:
    """
    Fetch posts from a subreddit within a timeframe,
    skipping ones we've already commented on or that don't match keywords.
    """
    now    = time.time()
    # 3 days for SMPchat, 1 day for others
    window = 3*24*60*60 if subreddit_name.lower() == "smpchat" else 24*60*60
    cutoff = now - window
    new_posts = []

    for sub in reddit.subreddit(subreddit_name).new(limit=limit):
        # skip old posts
        if sub.created_utc < cutoff:
            continue

        # skip if bot already commented
        sub.comments.replace_more(limit=0)
        if any(
            comment.author and comment.author.name.lower() == BOT_USERNAME
            for comment in sub.comments.list()
        ):
            continue

        # filter by keywords (for non-SMPchat)
        title_text = sub.title.lower()
        body_text  = sub.selftext.lower()
        if subreddit_name.lower() != "smpchat" and not any(k in title_text or k in body_text for k in KEYWORDS):
            continue

        # gather image URLs
        images = []
        if hasattr(sub, "gallery_data") and sub.gallery_data:
            for item in sub.gallery_data["items"]:
                media_id = item.get("media_id")
                meta = sub.media_metadata.get(media_id, {})
                url = meta.get("s", {}).get("u")
                if url:
                    images.append(url)
        elif not sub.is_self and sub.url.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
            images.append(sub.url)

        new_posts.append({
            "id":          sub.id,
            "title":       sub.title,
            "selftext":    sub.selftext,
            "permalink":   f"https://reddit.com{sub.permalink}",
            "subreddit":   sub.subreddit.display_name,
            "url":         sub.url,
            "image_urls":  images
        })

    return new_posts


if __name__ == "__main__":
    # Subreddits to scan
    subs = ["SMPchat", "Hairloss", "bald", "tressless"]
    all_new = []

    # Fetch new posts from each subreddit
    for s in subs:
        posts = get_new_smp_posts(s, limit=50)
        print(f"Fetched {len(posts)} new from r/{s}")
        all_new.extend(posts)

    print(f"Total new posts: {len(all_new)}")

    # POST each new entry to the Flask backend
    for post in all_new:
        payload = {
            "redditPostTitle":    post["title"],
            "subreddit":          post["subreddit"],
            "redditPostSelftext": post["selftext"],
            "redditPostUrl":      post["permalink"],
            "image_urls":         post["image_urls"]
        }
        try:
            resp = requests.post(f"{FLASK_BACKEND_URL}/suggestions", json=payload, timeout=10)
            resp.raise_for_status()
            print(f"✅ Sent {post['id']}: {post['title']}")
        except Exception as e:
            print(f"❌ Failed to send {post['id']}: {e}")
