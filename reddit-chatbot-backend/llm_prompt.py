import requests
import xml.etree.ElementTree as ET
from functools import lru_cache

# URLs of our sitemaps
SITEMAP_URLS = [
    "https://scalpsusa.com/post-sitemap.xml",
    "https://scalpsusa.com/page-sitemap.xml"
]
# UTM parameters to append to links
UTM_PARAMS = "?utm_source=Reddit&utm_campaign=Reddit_Response_bot"

@lru_cache(maxsize=1)
def fetch_all_blog_links():
    """
    Fetches and parses each sitemap, returning a flat list of all article URLs.
    """
    links = []
    for sitemap_url in SITEMAP_URLS:
        try:
            resp = requests.get(sitemap_url, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            # Sitemap XML uses <url><loc>URL</loc></url>
            for url_elem in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                loc = url_elem.text.strip()
                if loc:
                    links.append(loc + UTM_PARAMS)
        except Exception as e:
            print(f"Warning: failed to fetch/parse {sitemap_url}: {e}")
    return links


def choose_relevant_link(post_title, post_body):
    """
    Chooses the most relevant blog link based on keywords in the post title or body.
    Falls back to the general SMP guide if no match.
    """
    text = (post_title + " " + post_body).lower()
    for link in fetch_all_blog_links():
        # Simplest heuristic: look for any segment of the URL path in the post text
        slug = link.split('/')[-1].split('?')[0].replace('-', ' ')
        if any(word in text for word in slug.split() if len(word) > 3):
            return link
    # Default fallback
    return "https://scalpsusa.com/scalp-micropigmentation-guide/" + UTM_PARAMS

# The template prompt for the LLM
LLM_PROMPT_TEMPLATE = """
You are a highly skilled professional SMP artist answering questions about hair loss and SMP.

Title: {title}
Body: {body}
Post URL: {url}
Images: {images}

Your initial thoughts (from user, if any): {user_thought}

Provide a clear, concise answer (2–3 sentences, one dry quip) and include one relevant link for more detail:
More detail here: {link}
"""


def build_llm_prompt(post_title, post_selftext, post_url, image_urls, user_thought):
    """
    Constructs the final prompt for the Google LLM, selecting a relevant link via sitemap.
    """
    link = choose_relevant_link(post_title, post_selftext or "")
    images = ','.join(image_urls) if image_urls else '[No images]'
    return LLM_PROMPT_TEMPLATE.format(
        title=post_title,
        body=post_selftext or '[No body content]',
        url=post_url,
        images=images,
        user_thought=user_thought,
        link=link
    )
