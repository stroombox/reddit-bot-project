import requests
import xml.etree.ElementTree as ET
from functools import lru_cache

# URLs of our sitemaps (no UTM params here)
SITEMAP_URLS = [
    "https://scalpsusa.com/post-sitemap.xml",
    "https://scalpsusa.com/page-sitemap.xml"
]
# UTM parameters to append for tracking
UTM_PARAMS = "?utm_source=Reddit&utm_campaign=Reddit_Response_bot"

@lru_cache(maxsize=1)
def fetch_all_blog_links():
    """
    Fetches and parses each sitemap, returning a flat list of all article base URLs (no UTM).
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
                    # Store base URL without UTM
                    links.append(loc)
        except Exception as e:
            print(f"Warning: failed to fetch/parse {sitemap_url}: {e}")
    return links


def choose_relevant_link(post_title, post_body):
    """
    Chooses the most relevant blog link based on keywords in the post title or body.
    Falls back to the general SMP guide if no match.
    """
    text = (post_title + " " + post_body).lower()
    for base_link in fetch_all_blog_links():
        # Heuristic: match words from slug in text
        slug = base_link.rstrip('/').split('/')[-1].replace('-', ' ')
        for word in slug.split():
            if len(word) > 3 and word in text:
                return base_link
    # Default fallback base URL
    return "https://scalpsusa.com/scalp-micropigmentation-guide/"

# LLM prompt template with markdown link syntax: display text without UTM, target with UTM.
LLM_PROMPT_TEMPLATE = """
You are a highly skilled professional SMP artist answering questions about hair loss and SMP.

Title: {title}
Body: {body}
Post URL: {url}
Images: {images}

Your initial thoughts (from user, if any): {user_thought}

Provide a clear, concise answer (2–3 sentences, one dry quip) and include one relevant link for more detail:
More detail here: [{display_link}]({utm_link})
"""

def build_llm_prompt(post_title, post_selftext, post_url, image_urls, user_thought):
    """
    Constructs the final prompt for the Google LLM, selecting a relevant link via sitemap
    and formatting it with UTM for tracking, while showing the clean URL in markdown.
    """
    # Pick the base link and append UTM for tracking
    base_link = choose_relevant_link(post_title, post_selftext or "")
    utm_link = base_link + UTM_PARAMS
    # Prepare images list
    images = ','.join(image_urls) if image_urls else '[No images]'
    # Build prompt
    return LLM_PROMPT_TEMPLATE.format(
        title=post_title,
        body=post_selftext or '[No body content]',
        url=post_url,
        images=images,
        user_thought=user_thought,
        display_link=base_link,
        utm_link=utm_link
    )
