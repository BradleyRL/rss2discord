import feedparser
import httpx
import re
import html
from typing import List, Optional, Tuple
from .models import FeedItem

def clean_html_to_markdown(html_text: str) -> str:
    if not html_text:
        return ""
    # Unescape HTML entities
    text = html.unescape(html_text)
    
    # Remove script and style elements
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert hyperlinks <a href="URL">TEXT</a> -> [TEXT](URL)
    def href_sub(match):
        url = match.group(1)
        content = match.group(2)
        # strip inner HTML tags from content
        clean_content = re.sub(r'<.*?>', '', content).strip()
        if not clean_content:
            clean_content = url
        return f"[{clean_content}]({url})"

    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', href_sub, text, flags=re.DOTALL | re.IGNORECASE)

    # Convert <b> and <strong> -> **bold**
    text = re.sub(r'<(b|strong)>(.*?)</\1>', r'**\2**', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert <i> and <em> -> *italic*
    text = re.sub(r'<(i|em)>(.*?)</\1>', r'*\2*', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert line breaks and paragraph breaks
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)

    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Normalize whitespace
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    
    # Discord text length limit safety
    if len(text) > 1500:
        text = text[:1497] + "..."
        
    return text

def extract_image_url(entry, raw_content: str = "") -> Optional[str]:
    # 1. Media content / thumbnail tags
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        if isinstance(entry.media_thumbnail, list) and len(entry.media_thumbnail) > 0:
            return entry.media_thumbnail[0].get("url")
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            if isinstance(media, dict) and media.get("medium") == "image" or media.get("type", "").startswith("image/"):
                return media.get("url")
            elif isinstance(media, dict) and media.get("url"):
                return media.get("url")

    # 2. Enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/") or enc.get("href", "").lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                return enc.get("href")

    # 3. Search raw content or summary for <img> tags
    content_sources = [raw_content]
    if hasattr(entry, "summary"):
        content_sources.append(entry.summary)
    if hasattr(entry, "content"):
        for c in entry.content:
            if isinstance(c, dict) and "value" in c:
                content_sources.append(c["value"])

    for src_text in content_sources:
        if not src_text:
            continue
        img_match = re.search(r'<img\s+[^>]*src=["\']([^"\']+)["\']', src_text, re.IGNORECASE)
        if img_match:
            img_url = img_match.group(1)
            if img_url.startswith("http://") or img_url.startswith("https://"):
                return img_url

    return None

class RSSFetcher:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch_feed(self, feed_id: str, url: str) -> Tuple[List[FeedItem], Optional[str]]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RSS2Discord/1.0"
        }
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                response = client.get(url)
                response.raise_for_status()
                content = response.content
        except Exception as e:
            return [], f"HTTP Error fetching feed: {str(e)}"

        try:
            parsed = feedparser.parse(content)
            if parsed.bozo and not parsed.entries:
                return [], f"Failed to parse XML/RSS feed: {parsed.bozo_exception}"
            
            items: List[FeedItem] = []
            for entry in parsed.entries:
                title = entry.get("title", "Untitled Story").strip()
                link = entry.get("link", "").strip()
                guid = entry.get("id", entry.get("guid", link or title)).strip()
                
                # Summary / Description
                raw_desc = ""
                if hasattr(entry, "summary"):
                    raw_desc = entry.summary
                elif hasattr(entry, "description"):
                    raw_desc = entry.description
                elif hasattr(entry, "content") and entry.content:
                    raw_desc = entry.content[0].get("value", "")

                description = clean_html_to_markdown(raw_desc)
                
                # Author
                author = entry.get("author") or entry.get("author_detail", {}).get("name")
                
                # Published date
                published = entry.get("published") or entry.get("updated") or entry.get("pubDate")
                
                # Image
                image_url = extract_image_url(entry, raw_desc)
                
                # Categories
                categories = []
                if hasattr(entry, "tags"):
                    categories = [tag.get("term", "") for tag in entry.tags if tag.get("term")]

                item = FeedItem(
                    feed_id=feed_id,
                    title=title,
                    link=link,
                    guid=guid,
                    description=description,
                    published=published,
                    author=author,
                    image_url=image_url,
                    categories=categories
                )
                items.append(item)

            return items, None
        except Exception as e:
            return [], f"Error processing feed entries: {str(e)}"
