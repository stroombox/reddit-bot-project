import random
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# --- PROMPT TEMPLATES ---

# This prompt is used ONLY when the user provides "Initial Thoughts".
# It is highly restrictive and focused on editing.
EDITING_PROMPT_TEMPLATE = """
You are a master copy editor. Your ONLY task is to take the "User's Draft" below and refine it.
Follow these rules strictly:
1.  Correct any spelling or grammatical errors.
2.  Improve the phrasing to match the persona of a witty, knowledgeable SMP expert.
3.  **DO NOT** add any new topics, ideas, or information. The core message and intent of the user's draft MUST be preserved.
4.  After refining the text, on a new line, add a natural transition to the "Relevant Blog Link" provided.
5.  You **MUST** format the link using Reddit Markdown: `[Display Text](URL)`.

---
- User's Draft: "{thoughts}"
- Relevant Blog Link: {blog_link}
---

**Your Refined Comment (Formatted with Markdown Link):**
"""

# This prompt is used ONLY when the user leaves the thoughts box blank.
# It gives the AI creative freedom.
GENERATION_PROMPT_TEMPLATE = """
You are a veteran SMP artist with a knowledgeable, empathetic, and witty tone.
Your goal is to provide a short (1-3 sentences), natural-sounding, and helpful Reddit comment based on the post details below.

After your comment, on a new line, add a natural transition to the provided "Relevant Blog Link".
You **MUST** format the link using Reddit Markdown: `[Display Text](URL)`.

---
- Post Title: {title}
- Post Content: {selftext}
- Relevant Blog Link: {blog_link}
---

**Your Helpful Comment (Formatted with Markdown Link):**
"""

def add_utm_parameters(url: str) -> str:
    """Appends UTM tracking parameters to a given URL."""
    if not url or url == "None":
        return "None"
    utm_params = {
        'utm_source': 'reddit_proj',
        'utm_campaign': 'reddit'
    }
    url_parts = list(urlparse(url))
    query = dict(parse_qs(url_parts[4]))
    query.update(utm_params)
    url_parts[4] = urlencode(query)
    return urlunparse(url_parts)

def choose_relevant_blog_link(blog_urls, text):
    """Chooses the most relevant blog link from a list based on text content."""
    text = text.lower()
    if not blog_urls:
        return "None"

    for url in blog_urls:
        slug = url.rstrip('/').split('/')[-1]
        for token in re.split(r'[-_]', slug):
            if len(token) > 2 and token in text:
                return url
    
    return random.choice(blog_urls)

def build_llm_prompt(title, selftext, url, image_urls, user_thoughts, blog_urls):
    """
    Builds the complete prompt by selecting the correct template based on user input.
    """
    combined_text = f"{title} {selftext}"
    base_blog_link = choose_relevant_blog_link(blog_urls, combined_text)
    final_blog_link_with_utm = add_utm_parameters(base_blog_link)

    # --- NEW LOGIC: Choose the prompt based on user_thoughts ---
    if user_thoughts and user_thoughts.strip():
        # User provided thoughts, so we use the strict "Editor" prompt
        return EDITING_PROMPT_TEMPLATE.format(
            thoughts=user_thoughts,
            blog_link=final_blog_link_with_utm
        )
    else:
        # User did not provide thoughts, so we use the creative "Creator" prompt
        return GENERATION_PROMPT_TEMPLATE.format(
            title=title,
            selftext=selftext or "None",
            blog_link=final_blog_link_with_utm
        )