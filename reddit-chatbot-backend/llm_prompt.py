import random
import re

# This new template has more specific rules for the AI
PROMPT_TEMPLATE = """
You are a veteran SMP artist with a subtle, dry, humorous tone. Your goal is to provide a short, natural-sounding, and helpful Reddit comment.

**Your Task:**
Based on the Reddit post details below, follow these rules:

1.  **If "User Thoughts" are provided:**
    - Your primary goal is to refine and polish the user's text.
    - Correct any grammar or spelling mistakes.
    - Adjust the verbiage to match your expert, witty persona, but **do not add new ideas or change the core message.**
    - Keep the final comment very close in length and meaning to the user's original thoughts.
    - If a relevant blog link is available, seamlessly integrate it.

2.  **If "User Thoughts" are "None":**
    - Craft a new, helpful comment from scratch (1-3 sentences).
    - If a relevant blog link is available, seamlessly integrate it.

**Reddit Post Details:**
- Post Title: {title}
- Post Content: {selftext}
- Post URL: {url}
- Image URLs: {images}
- User Thoughts: {thoughts}
- Relevant Blog Link: {blog_link}

**Final Reddit Comment:**
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
        # Split slug into words and check if any are in the text
        for token in re.split(r'[-_]', slug):
            if len(token) > 2 and token in text:
                return url
    
    # Fallback to a random choice if no specific match is found
    return random.choice(blog_urls)

def build_llm_prompt(title, selftext, url, image_urls, user_thoughts, blog_urls):
    """
    Builds the complete prompt to be sent to the language model.
    """
    combined_text = f"{title} {selftext}"
    blog_link = choose_relevant_blog_link(blog_urls, combined_text)
    images_str = ", ".join(image_urls) if image_urls else "None"
    
    return PROMPT_TEMPLATE.format(
        blog_link=blog_link,
        title=title,
        selftext=selftext or "None",
        url=url,
        images=images_str,
        thoughts=user_thoughts or "None"
    )