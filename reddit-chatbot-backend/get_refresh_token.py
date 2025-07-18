import praw
import os
from dotenv import load_dotenv

# Load your existing credentials
load_dotenv()
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")

# This is a temporary Reddit instance for authorization
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    redirect_uri="http://localhost:8080",  # Temporary redirect
    user_agent="get_token_script_v1"
)

# Define the permissions your bot needs
# 'identity' lets it know who you are
# 'read' lets it read posts
# 'submit' lets it post comments
required_scopes = ["identity", "read", "submit"]

# Generate the authorization URL
auth_url = reddit.auth.url(scopes=required_scopes, state="...", duration="permanent")

print("\n--- Step 1: Authorize Your Bot ---")
print("1. Visit the following URL in your web browser:")
print(f"\n{auth_url}\n")
print("2. Click 'Allow' or 'Accept'.")
print("3. You will be redirected to a 'localhost' page that won't load. This is normal.")
print("4. Copy the ENTIRE URL from your browser's address bar after you are redirected.")

# Get the full redirect URL from the user
redirected_url = input("\n--- Step 2: Paste the full redirect URL here: ")

# Extract the authorization code from the URL
try:
    code = redirected_url.split("code=")[1].split("&")[0]
    print("\nAuthorization code found successfully.")
except IndexError:
    print("\nCould not find 'code' in the URL. Please make sure you copied the full redirect URL.")
    exit()

# Use the code to get a new refresh token
try:
    print("Requesting new refresh token...")
    new_refresh_token = reddit.auth.authorize(code)
    print("\n--- SUCCESS! ---")
    print("Your new, permanent refresh token is:\n")
    print(new_refresh_token)
    print("\nUpdate your .env file and Render environment variables with this new token.")
except Exception as e:
    print(f"\nAn error occurred: {e}")