import os
import time
from dotenv import load_dotenv
import praw

# Load environment variables from .env file
load_dotenv()

# --- Load Reddit API Credentials from .env file ---
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.getenv("REDDIT_REFRESH_TOKEN")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")

# --- Your Test Post ID ---
# You can get this from the URL of any post you want to test commenting on.
# Example: https://www.reddit.com/r/test/comments/1lkgx32/
TEST_POST_ID = "1lkgx32" 

if __name__ == "__main__":
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_REFRESH_TOKEN, REDDIT_USER_AGENT]):
        print("❌ Missing required Reddit credentials in your .env file. Exiting.")
    else:
        try:
            # Initialize PRAW with the refresh token method
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                refresh_token=REDDIT_REFRESH_TOKEN,
                user_agent=REDDIT_USER_AGENT
            )
            
            print(f"✅ Successfully authenticated with Reddit as: /u/{reddit.user.me().name}")

            submission = reddit.submission(id=TEST_POST_ID)
            print(f"✅ Found test post: '{submission.title}'")

            comment_content = f"This is an automated test comment (Timestamp: {int(time.time())})."
            print(f"Attempting to post: '{comment_content}'")
            
            new_comment = submission.reply(comment_content)
            
            print("\n--- SUCCESS! ---")
            print(f"✅ Comment posted successfully.")
            print(f"View it here: https://reddit.com{new_comment.permalink}")

        except Exception as e:
            print(f"\n--- FAILED ---")
            print(f"❌ An error occurred: {e}")
            print("Please double-check your credentials in the .env file and ensure your Reddit app has 'submit' permissions.")