# llm_prompt.py
# ----------------
# Streamlined LLM prompt: refine user-provided draft only, and suggest one verified blog resource via sitemap lookup.

import requests
import xml.etree.ElementTree as ET

# Fetch and parse sitemaps at runtime to build a set of valid URLs
def get_valid_blog_urls():
    urls = set()
    for sitemap_url in (
        "https://scalpsusa.com/post-sitemap.xml",
        "https://scalpsusa.com/page-sitemap.xml"
    ):
        try:
            resp = requests.get(sitemap_url, timeout=5)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
                urls.add(elem.text.strip())
        except Exception:
            continue
    return urls

VALID_BLOG_URLS = get_valid_blog_urls()

LLM_PROMPT = """
You are a professional scalp micropigmentation (SMP) artist.

When the user provides initial thoughts (user_draft), your **PRIMARY GOAL** is to refine and polish their text:
- Preserve the user's original ideas, length, and tone.
- Fix grammar, improve clarity, and choose natural phrasing.
- Do **NOT** add new sentences, concepts, or sales pitches.

After refining, suggest **exactly one** relevant, **verified** blog link by selecting from the preloaded sitemap URLs.
Append the chosen link under the heading **Resource** on its own line.

Reddit Post Title: {post_title}
Reddit Post Body: {post_selftext}
User Draft: {user_thought}

**Refined Draft:**
"""


def build_llm_prompt(post_title, post_selftext, post_url, image_urls, user_thought):
    """
    Fill in the LLM_PROMPT template with post data and the user's draft.
    """
    imgs = ", ".join(image_urls) if isinstance(image_urls, (list, tuple)) else image_urls
    return LLM_PROMPT.format(
        post_title=post_title or "",
        post_selftext=post_selftext or "",
        post_url=post_url or "",
        image_urls=imgs,
        user_thought=user_thought or ""
    )
