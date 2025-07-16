import random
import re

PROMPT_TEMPLATE = (
    "You are a veteran SMP artist providing friendly, expert advice. "
    "Based on the following discussion, craft a helpful comment. "
    "Include exactly one relevant article link to our blog: {blog_link}\n\n"
    "Post Title: {title}\n"
    "Post Content: {selftext}\n"
    "Post URL: {url}\n"
    "Image URLs: {images}\n"
    "User Thoughts: {thoughts}\n\n"
    "Comment:"
)

def choose_relevant_blog_link(blog_urls, text):
    text = text.lower()
    for url in blog_urls:
        slug = url.rstrip('/').split('/')[-1]
        for token in re.split(r'[-_]', slug):
            if token and token in text:
                return url
    return random.choice(blog_urls) if blog_urls else ''

def build_llm_prompt(title, selftext, url, image_urls, user_thoughts, blog_urls):
    combined = f"{title} {selftext}"
    blog_link = choose_relevant_blog_link(blog_urls, combined)
    images = ", ".join(image_urls) if image_urls else "None"
    return PROMPT_TEMPLATE.format(
        blog_link=blog_link,
        title=title,
        selftext=selftext or "None",
        url=url,
        images=images,
        thoughts=user_thoughts or "None"
    )
