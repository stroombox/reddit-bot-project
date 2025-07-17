import random
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# This is the new helper function to add UTM parameters to a URL
def add_utm_parameters(url: str) -> str:
    """Appends UTM tracking parameters to a given URL."""
    utm_params = {
        'utm_source': 'reddit_proj',
        'utm_campaign': 'reddit'
    }
    # Parse the URL to safely add new query parameters
    url_parts = urlparse(url)
    query = parse_qs(url_parts.query)
    query.update(utm_params)
    
    # Rebuild the URL with the new parameters
    new_query_string = urlencode(query, doseq=True)
    new_url_parts = url_parts._replace(query=new_query_string)
    
    return urlunparse(new_url_parts)


PROMPT_TEMPLATE = """
You are an expert SMP artist with a knowledgeable, empathetic, and witty tone. Your goal is to provide a short, natural-sounding, and helpful Reddit comment.

**Your Task:**
Based on the Reddit post details below, follow these strict rules:

1.  **If "User Thoughts" are provided:**
    - Your ONLY job is to refine and polish the user's text.
    - Correct grammar and spelling, and improve the verbiage to match your persona.
    - **DO NOT** add new ideas, subjects, or information. The length and core message must remain almost identical to the user's thoughts.
    - Example: If the user says "looks great brother!", you could refine it to "That's a clean result, looks great brother!"

2.  **If "User Thoughts" are "None":**
    - Craft a new, helpful comment from scratch (1-3 sentences).

3.  **Link Integration (IMPORTANT):**
    - After your main comment, add a relevant blog link on a new line.
    - You **MUST** format the link using Reddit Markdown: `[Display Text](URL)`.
    - The display text should be natural and relevant to the article. For example: `You can read more about what to expect from the SMP process here: [What to Expect When Getting SMP](https://scalpsusa.com/what-to-expect-when-getting-smp/?utm_source=reddit_proj&utm_campaign=reddit)`

**Reddit Post Details:**
- Post Title: {title}
- Post Content: {selftext}
- Post URL: {url}
- Image URLs: {images}
- User Thoughts: {thoughts}
- Relevant Blog Link with UTM parameters: {blog_link}

**Final Reddit Comment (Formatted with Markdown Link):**
"""

def choose_relevant_blog_link(blog_urls, text):
    """
    Chooses the most relevant blog link from a list based on text content.
    """
    text = text.lower()
    if not blog_urls:
        return "None"

    # Simple keyword matching based on URL slugs
    for url in blog_urls:
        slug = url.rstrip('/').split('/')[-1]
        for token in re.split(r'[-_]', slug):
            if len(token) > 2 and token in text:
                return url
    
    return random.choice(blog_urls)

def build_llm_prompt(title, selftext, url, image_urls, user_thoughts, blog_urls):
    """
    Builds the complete prompt to be sent to the language model.
    """
    combined_text = f"{title} {selftext}"
    # Choose the base blog link
    base_blog_link = choose_relevant_blog_link(blog_urls, combined_text)
    
    # Add UTM parameters to the chosen link
    final_blog_link_with_utm = add_utm_parameters(base_blog_link) if base_blog_link != "None" else "None"

    images_str = ", ".join(image_urls) if image_urls else "None"
    
    return PROMPT_TEMPLATE.format(
        blog_link=final_blog_link_with_utm,
        title=title,
        selftext=selftext or "None",
        url=url,
        images=images_str,
        thoughts=user_thoughts or "None"
    )