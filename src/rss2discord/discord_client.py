import httpx
import time
import logging
import re
from typing import Optional, Dict, Any, Tuple
from .models import WebhookConfig, FeedItem, FeedConfig, RouteConfig

logger = logging.getLogger(__name__)

def hex_to_int(hex_str: str) -> int:
    hex_str = hex_str.lstrip("#")
    try:
        return int(hex_str, 16)
    except ValueError:
        return 0x5865F2  # Discord Blurple default

def sanitize_username(name: Optional[str]) -> Optional[str]:
    if not name or not name.strip():
        return None
    # Discord API restricts usernames containing "discord", "clyde", "@", ":", or "```"
    sanitized = re.sub(r'discord', 'FeedHub', name, flags=re.IGNORECASE)
    sanitized = re.sub(r'clyde', 'Bot', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'[@:`]', '', sanitized)
    sanitized = sanitized.strip()[:80]
    return sanitized if sanitized else None

class DiscordWebhookClient:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def send_embed(
        self,
        webhook: WebhookConfig,
        item: FeedItem,
        feed: FeedConfig,
        route: Optional[RouteConfig] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Sends an RSS item to a Discord webhook as a rich embed payload.
        Handles HTTP rate limiting (429) automatically.
        """
        embed_color_hex = (
            (route.override_color if route and route.override_color else None) or
            feed.custom_color or
            webhook.color or
            "#5865F2"
        )
        
        embed: Dict[str, Any] = {
            "title": item.title[:256] if item.title else "Untitled Item",
            "url": item.link if item.link.startswith(("http://", "https://")) else None,
            "description": item.description[:2048] if item.description else None,
            "color": hex_to_int(embed_color_hex),
            "footer": {
                "text": f"Source: {feed.name}"
            }
        }

        # Remove null values
        embed = {k: v for k, v in embed.items() if v is not None}

        if item.author:
            embed["author"] = {"name": item.author[:256]}

        if item.image_url:
            embed["image"] = {"url": item.image_url}

        if item.published:
            embed["footer"]["text"] += f" • {item.published}"

        payload: Dict[str, Any] = {
            "embeds": [embed]
        }

        if webhook.username:
            sanitized_name = sanitize_username(webhook.username)
            if sanitized_name:
                payload["username"] = sanitized_name

        if webhook.avatar_url:
            payload["avatar_url"] = webhook.avatar_url

        if route and route.message_prefix:
            payload["content"] = route.message_prefix

        return self.post_payload(webhook.url, payload)

    def send_test_message(self, webhook_url: str, name: str = "Test Webhook", username: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        payload: Dict[str, Any] = {
            "embeds": [
                {
                    "title": "Webhook Connection Test Successful!",
                    "description": f"The Discord webhook for **{name}** is configured correctly and ready to receive RSS feed updates.",
                    "color": 0x57F287,  # Green
                    "footer": {
                        "text": "RSS-to-Discord Router • Test System"
                    }
                }
            ]
        }
        if username:
            sanitized_name = sanitize_username(username)
            if sanitized_name:
                payload["username"] = sanitized_name
        return self.post_payload(webhook_url, payload)

    def post_payload(self, webhook_url: str, payload: Dict[str, Any], max_retries: int = 3) -> Tuple[bool, Optional[str]]:
        headers = {"Content-Type": "application/json"}
        
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(webhook_url, json=payload, headers=headers)

                    if resp.status_code in (200, 204):
                        return True, None
                    elif resp.status_code == 429:
                        # Rate limited
                        retry_after = 2.0
                        try:
                            rate_data = resp.json()
                            retry_after = float(rate_data.get("retry_after", 2.0))
                        except Exception:
                            pass
                        logger.warning(f"Discord rate limited (429). Retrying after {retry_after}s...")
                        time.sleep(min(retry_after, 10.0))
                        continue
                    else:
                        return False, f"Discord Webhook API returned HTTP {resp.status_code}: {resp.text}"
            except Exception as e:
                if attempt == max_retries - 1:
                    return False, f"HTTP Connection Exception: {str(e)}"
                time.sleep(1.0)

        return False, "Exceeded maximum retry attempts"
