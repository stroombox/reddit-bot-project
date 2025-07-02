import praw

CLIENT_ID     = "<YOUR_CLIENT_ID>"
CLIENT_SECRET = "<YOUR_CLIENT_SECRET>"
REDIRECT_URI  = "http://localhost:8080"   # any localhost callback works
USER_AGENT    = "refresh-token-generator by u/YourRedditUsername"

reddit = praw.Reddit(
    client_id     = CLIENT_ID,
    client_secret = CLIENT_SECRET,
    redirect_uri  = REDIRECT_URI,
    user_agent    = USER_AGENT
)

# 1) Generate the URL and open it in your browser:
scopes = ["identity", "read", "submit"]
url = reddit.auth.url(scopes, "random_state", "permanent")
print("1) Open this URL in your browser:\n\n", url)

# 2) Authorize the app; after you click Allow, Reddit will redirect to localhost with a ?code=VALUE
code = input("\n2) Paste the “code” query-param here: ").strip()

# 3) Exchange the code for a refresh token
refresh_token = reddit.auth.authorize(code)
print("\n🔑 Your refresh token is:\n", refresh_token)
