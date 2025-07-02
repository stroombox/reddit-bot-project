import praw

CLIENT_ID     = "<LIMpbhTAYeb9ERnFGU0ryA>"
CLIENT_SECRET = "<PKaho8HfTu5mdObB653t21NGnwWKGQ>"
REDIRECT_URI  = "http://localhost:8080"
USER_AGENT    = "refresh-token-generator by /u/Alex_Ash_"

reddit = praw.Reddit(
    client_id     = CLIENT_ID,
    client_secret = CLIENT_SECRET,
    redirect_uri  = REDIRECT_URI,
    user_agent    = USER_AGENT
)

# 1) Open this URL in your browser and approve the app:
scopes = ["identity", "read", "submit"]
url = reddit.auth.url(scopes, "dummy_state", "permanent")
print("1) Open this URL in your browser:\n\n", url)

# 2) After clicking Allow, you’ll be redirected to localhost with ?code=XYZ
code = input("\n2) Paste the “code” part here and press Enter: ").strip()

# 3) Exchange that code for a refresh token
refresh_token = reddit.auth.authorize(code)
print("\n🎉 Your NEW refresh token is:\n", refresh_token)
