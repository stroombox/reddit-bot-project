import os, json, base64
from github import Github, GithubException
import praw
import requests
import time

# — 1) Fetch or initialize our JSON “DB” on GitHub —
gh   = Github(os.environ["GH_TOKEN"])
repo = gh.get_repo("stroombox/reddit-bot-project")
path = "posted_submissions.json"

try:
    contents = repo.get_contents(path, ref="main")
    posted   = json.loads(base64.b64decode(contents.content).decode())
    sha      = contents.sha
except GithubException:
    posted = []
    sha    = None

# — 2) Define how to pull new posts from Reddit —
def get_new_smp_posts(reddit, subreddit_name, posted_ids, limit=25):
    cutoff = time.time() - (3*24*60*60 if subreddit_name.lower()=="smpchat" else 24*60*60)
    new = []
    for sub in reddit.subreddit(subreddit_name).new(limit=limit):
        if sub.created_utc < cutoff or sub.id in posted_ids:
            continue
        # (your keyword logic here…)
        new.append({
            "id": sub.id,
            "title": sub.title,
            "selftext": sub.selftext,
            "permalink": f"https://reddit.com{sub.permalink}",
            "subreddit": sub.subreddit.display_name,
            "url": sub.url,
            "image_urls": []
        })
    return new

# — 3) Main run: authenticate & scrape —
if __name__ == "__main__":
    # (1) Check creds
    for var in ("REDDIT_CLIENT_ID","REDDIT_CLIENT_SECRET","REDDIT_USER_AGENT","GH_TOKEN","FLASK_BACKEND_URL"):
        if not os.getenv(var):
            print(f"❌ Missing {var} – exiting."); exit(1)

    # (2) Load posted IDs from GitHub
    posted_ids = set(posted)

    # (3) Connect to Reddit
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT")
    )

    # (4) Scrape each subreddit
    all_new = []
    for name in ["SMPchat","Hairloss","bald","tressless"]:
        all_new += get_new_smp_posts(reddit, name, posted_ids, limit=50)

    print(f"Found {len(all_new)} new posts.")

    # (5) Send to your Flask and update GitHub JSON
    new_ids = []
    for post in all_new:
        resp = requests.post(os.getenv("FLASK_BACKEND_URL"), json={
            "redditPostTitle": post["title"],
            "subreddit": post["subreddit"],
            "redditPostSelftext": post["selftext"],
            "redditPostUrl": post["permalink"],
            "image_urls": post["image_urls"]
        })
        if resp.ok:
            new_ids.append(post["id"])
            print(f"✅ Sent: {post['title']}")
        else:
            print(f"❌ Failed to send: {post['title']}")

    # (6) Write back any brand-new IDs
    for sid in new_ids:
        if sid not in posted:
            posted.append(sid)

    updated = json.dumps(posted, indent=2)
    if sha:
        repo.update_file(path, "update posted IDs", updated, sha, branch="main")
    else:
        repo.create_file(path, "create posted IDs", updated, branch="main")

    print(f"🔨 Wrote {len(new_ids)} new IDs; total is now {len(posted)}.")
