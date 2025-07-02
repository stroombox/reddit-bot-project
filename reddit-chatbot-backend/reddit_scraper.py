import os, json, base64
from github import Github, GithubException

# — Fetch or initialize our JSON “DB” on GitHub —
gh    = Github(os.environ["GH_TOKEN"])
repo  = gh.get_repo("stroombox/reddit-bot-project")
path  = "posted_submissions.json"

try:
    contents = repo.get_contents(path, ref="main")
    posted   = json.loads(base64.b64decode(contents.content).decode())
    sha      = contents.sha
except GithubException:
    posted = []
    sha    = None

# … your existing scraping logic runs here, filling new_ids = […] …

# — After posting, write back to GitHub —
for sid in new_ids:
    if sid not in posted:
        posted.append(sid)

updated = json.dumps(posted, indent=2)
if sha:
    repo.update_file(path, "update posted IDs", updated, sha, branch="main")
else:
    repo.create_file(path, "create posted IDs", updated, branch="main")

print(f"Wrote {len(new_ids)} new IDs; total is now {len(posted)}.")


import praw
import os
import requests
import sqlite3
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Database Configuration ---
DATABASE_FILE = 'bot_data.db'

# --- Reddit API Credentials (from .env file) ---
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
REDDIT_USER_AGENT = f"desktop:smp_bot_for_{REDDIT_USERNAME}:v0.1 (by /u/{REDDIT_USERNAME})"

# --- Flask Backend URL (Use environment variable for production) ---
FLASK_BACKEND_URL = os.getenv("FLASK_BACKEND_URL", "http://localhost:5000/suggestions")


def get_posted_submission_ids():
    """Connects to the DB and retrieves a set of all submission IDs that have been posted."""
    posted_ids = set()
    try:
        with sqlite3.connect(DATABASE_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT submission_id FROM posted_submissions")
            rows = cursor.fetchall()
            for row in rows:
                posted_ids.add(row[0])
        print(f"Found {len(posted_ids)} previously posted submission IDs in the database.")
    except Exception as e:
        print(f"Error connecting to database to get posted IDs: {e}")
    return posted_ids

def get_new_smp_posts(reddit_instance, subreddit_name, bot_username, posted_ids, limit=25):
    """Fetches posts with a variable time limit, skipping any that have already been processed."""
    
    if subreddit_name.lower() == 'smpchat':
        time_limit_seconds = 3 * 24 * 60 * 60  # 3 days
        print(f"Fetching posts from r/{subreddit_name} from the last 3 days...")
    else:
        time_limit_seconds = 1 * 24 * 60 * 60  # 24 hours
        print(f"Fetching posts from r/{subreddit_name} from the last 24 hours...")
        
    cutoff_time = time.time() - time_limit_seconds
    posts_data = []

    try:
        subreddit = reddit_instance.subreddit(subreddit_name)
        for submission in subreddit.new(limit=limit):
            if submission.created_utc < cutoff_time:
                break
            
            if submission.id in posted_ids:
                continue

            has_already_commented = False
            submission.comments.replace_more(limit=0)
            for comment in submission.comments.list():
                if comment.author and comment.author.name.lower() == bot_username.lower():
                    print(f" - Skipping '{submission.title}' (already commented manually).")
                    has_already_commented = True
                    break
            if has_already_commented:
                continue

            keywords = ['smp', 'hair', 'scalp', 'bald', 'follicle', 'loss', 'density', 'microblading', 'tattoo', 'pigmentation', 'hairline', 'scar', 'scars']
            is_relevant = (
                subreddit_name.lower() == 'smpchat' or
                any(keyword in submission.title.lower() or keyword in submission.selftext.lower() for keyword in keywords)
            )

            if is_relevant:
                post_info = {
                    'id': submission.id,
                    'title': submission.title,
                    'subreddit': submission.subreddit.display_name,
                    'selftext': submission.selftext,
                    'url': submission.url,
                    'permalink': f"https://www.reddit.com{submission.permalink}",
                    'image_urls': []
                }
                if hasattr(submission, 'gallery_data') and submission.gallery_data:
                    for item in submission.gallery_data['items']:
                        media_id = item.get('media_id')
                        if media_id and media_id in submission.media_metadata:
                            metadata = submission.media_metadata[media_id]
                            if metadata.get('s', {}).get('u'):
                                post_info['image_urls'].append(metadata['s']['u'])
                elif not submission.is_self and submission.url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    post_info['image_urls'].append(submission.url)

                posts_data.append(post_info)
                print(f" - Found new relevant post: {submission.title}")
                
        print(f"Post fetching complete for r/{subreddit_name}.")
    except Exception as e:
        print(f"Error fetching posts from r/{subreddit_name}: {e}")
    return posts_data

def send_raw_post_to_flask(post_data):
    """Sends the raw Reddit post data to the Flask backend."""
    payload = {
        "redditPostTitle": post_data['title'],
        "subreddit": post_data['subreddit'],
        "redditPostSelftext": post_data['selftext'],
        "redditPostUrl": post_data['permalink'],
        "image_urls": post_data['image_urls']
    }
    try:
        response = requests.post(FLASK_BACKEND_URL, json=payload)
        response.raise_for_status()
        print(f"Successfully sent raw post for '{post_data['title']}' to Flask.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending raw post for '{post_data['title']}' to Flask: {e}")
        return False

if __name__ == "__main__":
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]):
        print("CRITICAL: Reddit credentials not found in .env file. Exiting.")
    else:
        try:
            posted_submission_ids = get_posted_submission_ids()
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                username=REDDIT_USERNAME,
                password=REDDIT_PASSWORD,
                user_agent=REDDIT_USER_AGENT
            )
            print(f"Attempting to connect to Reddit as: /u/{reddit.user.me()}")
            subreddits_to_scrape = ['SMPchat', 'Hairloss', 'bald', 'tressless']
            all_new_posts = []
            for sub_name in subreddits_to_scrape:
                all_new_posts.extend(get_new_smp_posts(reddit, sub_name, REDDIT_USERNAME, posted_submission_ids, limit=50))
            print(f"\nFound {len(all_new_posts)} total new relevant posts.")
            if all_new_posts:
                print("\n--- Sending Posts to Dashboard ---")
                for post in all_new_posts:
                    send_raw_post_to_flask(post)
                print("\nScraping complete.")
            else:
                print("No new relevant posts found.")
        except Exception as e:
            print(f"An overall error occurred: {e}")