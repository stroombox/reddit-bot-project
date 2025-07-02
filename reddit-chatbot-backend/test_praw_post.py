import praw
import os
import time # For a small delay

# --- Reddit API Credentials (Your actual values) ---
REDDIT_CLIENT_ID = "LIMpbhTAYeb9ERnFGU0ryA"
REDDIT_CLIENT_SECRET = "PKaho8HfTu5mdObB653t21NGnwWKGQ"
REDDIT_USERNAME = "Alex_Ash_"
REDDIT_PASSWORD = ""
REDDIT_USER_AGENT = "desktop:smp_bot_for_alex:v0.1 (by /u/Alex_Ash_)" # Use the exact string we discussed

# --- PRAW Reddit Instance ---
# This should be the same as your reddit_poster in app.py
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    username=REDDIT_USERNAME,
    password=REDDIT_PASSWORD,
    user_agent=REDDIT_USER_AGENT
)

# --- Your Test Post ID ---
# Make sure this is YOUR specific test post from r/test
TEST_POST_ID = "1lkgx32" 

if __name__ == "__main__":
    print("Attempting to connect to Reddit and post a test comment...")
    try:
        # Verify login by fetching user info
        print(f"Logged in as: /u/{reddit.user.me()}")

        # Get the submission object for your test post
        submission = reddit.submission(id=TEST_POST_ID)
        print(f"Found test post: '{submission.title}' by /u/{submission.author}")

        # Define the test comment content
        test_comment_content = f"This is an automated test comment from PRAW script (timestamp: {time.time()})."
        print(f"Attempting to post: '{test_comment_content}'")

        # Post the comment
        new_comment = submission.reply(test_comment_content)
        print(f"SUCCESS! Comment posted with ID: {new_comment.id}")
        print(f"View comment: {new_comment.permalink}")

    except Exception as e:
        print(f"FAILED to post comment: {e}")
        print("Please double-check your Reddit API credentials and ensure your Reddit app has 'submit' permissions.")