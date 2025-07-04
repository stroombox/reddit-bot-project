import os
import time
from dotenv import load_dotenv
import praw
import requests

# Load local .env (for dev); in Render it will just skip if none
load_dotenv()

# — Reddit & Flask creds —
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.getenv("REDDIT_REFRESH_TOKEN")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT")
# Strip trailing whitespace/newlines here
FLASK_BACKEND_URL    = os.getenv("FLASK_BACKEND_URL", "").strip()

# Ensure required env vars are present
for var in [
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "REDDIT_REFRESH_TOKEN",
    "REDDIT_USER_AGENT",
    "FLASK_BACKEND_URL"
]:
    if not os.getenv(var):
        print(f"❌ Missing {var} – exiting.")
        exit(1)

# Initialize Reddit client with refresh token
reddit = praw.Reddit(
    client_id     = REDDIT_CLIENT_ID,
    client_secret = REDDIT_CLIENT_SECRET,
    refresh_token = REDDIT_REFRESH_TOKEN,
    user_agent    = REDDIT_USER_AGENT
)

# Grab our bot’s username for skip-logic
BOT_USERNAME = reddit.user.me().name.lower()

# Keywords for relevance
KEYWORDS = [
    "smp","hair","scalp","bald","follicle","loss","density",
    "microblading","tattoo","pigmentation","hairline","scar","scars"
]

def get_new_smp_posts(subreddit_name, limit=25):
    """
    Fetches posts from the given subreddit within the correct time window,
    skipping any that the bot has already commented on or that don't match keywords.
    """
    now    = time.time()
    # 3 days for SMPchat, 1 day for others
    window = 3*24*60*60 if subreddit_name.lower() == "smpchat" else 24*60*60
    cutoff = now - window
    new_posts = []

    for sub in reddit.subreddit(subreddit_name).new(limit=limit):
        if sub.created_utc < cutoff:
            continue

        # skip if our bot already commented
        sub.comments.replace_more(limit=0)
        if any(
            comment.author and comment.author.name.lower() == BOT_USERNAME
            for comment in sub.comments.list()
        ):
            continue

        tl = sub.title.lower()
        bl = sub.selftext.lower()
        # for non-SMPchat, require a keyword match
        if subreddit_name.lower() != "smpchat" and not any(k in tl or k in bl for k in KEYWORDS):
            continue

        # build the post data
        post_info = {
            "id": sub.id,
            "title": sub.title,
            "selftext": sub.selftext,
            "permalink": f"https://reddit.com{sub.permalink}",
            "subreddit": sub.subreddit.display_name,
            "url": sub.url,
            "image_urls": []
        }

        # handle galleries
        if hasattr(sub, "gallery_data") and sub.gallery_data:
            for item in sub.gallery_data["items"]:
                mid  = item.get("media_id")
                meta = sub.media_metadata.get(mid, {})
                if meta.get("s", {}).get("u"):
                    post_info["image_urls"].append(meta["s"]["u"])
        # handle single images
        elif not sub.is_self and sub.url.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
            post_info["image_urls"].append(sub.url)

        new_posts.append(post_info)

    return new_posts

if __name__ == "__main__":
    # list of subreddits to scrape
    subs    = ["SMPchat", "Hairloss", "bald", "tressless"]
    all_new = []

    # fetch from each
    for s in subs:
        posts = get_new_smp_posts(s, limit=50)
        print(f"Fetched {len(posts)} new from r/{s}")
        all_new.extend(posts)

    print(f"Found {len(all_new)} total new posts.")

    # send each to your Flask dashboard
    for post in all_new:
        payload = {
            "redditPostTitle":    post["title"],
            "subreddit":          post["subreddit"],
            "redditPostSelftext": post["selftext"],
            "redditPostUrl":      post["permalink"],
            "image_urls":         post["image_urls"]
        }
        try:
            r = requests.post(FLASK_BACKEND_URL, json=payload)
            r.raise_for_status()
            print(f"✅ Sent: {post['title']}")
        except Exception as e:
            print(f"❌ Failed to send {post['title']}: {e}")
