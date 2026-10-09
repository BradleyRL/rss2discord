import httpx
import logging
import html
import time
from typing import Optional, Tuple, Dict, Any
from .models import WebhookConfig, FeedItem, FeedConfig, RouteConfig

logger = logging.getLogger(__name__)

class TelegramClient:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def send_message(
        self,
        webhook: WebhookConfig,
        item: FeedItem,
        feed: FeedConfig,
        route: Optional[RouteConfig] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Sends an RSS feed item to a Telegram channel or group via Telegram Bot API.
        """
        bot_token = webhook.telegram_bot_token
        chat_id = webhook.telegram_chat_id

        if not bot_token or not chat_id:
            return False, "Missing Telegram Bot Token or Chat ID"

        # Format message in HTML
        title_esc = html.escape(item.title or "Untitled Item")
        feed_esc = html.escape(feed.name or "RSS Feed")

        lines = []
        if route and route.message_prefix:
            lines.append(html.escape(route.message_prefix))

        if item.link:
            lines.append(f"<b><a href=\"{item.link}\">{title_esc}</a></b>")
        else:
            lines.append(f"<b>{title_esc}</b>")

        if item.description:
            clean_desc = html.escape(item.description[:1000])
            lines.append(f"\n{clean_desc}")

        lines.append(f"\n📡 <i>Source: {feed_esc}</i>")

        text_content = "\n".join(lines)

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text_content,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        return self.post_payload(url, payload)

    def send_test_message(self, bot_token: str, chat_id: str, name: str = "Test Destination") -> Tuple[bool, Optional[str]]:
        if not bot_token or not chat_id:
            return False, "Missing Telegram Bot Token or Chat ID"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        text_content = (
            f"🚀 <b>Telegram Connection Test Successful!</b>\n\n"
            f"The Telegram destination <b>{html.escape(name)}</b> is configured correctly and ready to receive RSS feed updates."
        )
        payload = {
            "chat_id": chat_id,
            "text": text_content,
            "parse_mode": "HTML"
        }
        return self.post_payload(url, payload)

    def post_payload(self, url: str, payload: Dict[str, Any], max_retries: int = 3) -> Tuple[bool, Optional[str]]:
        headers = {"Content-Type": "application/json"}
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            return True, None
                        else:
                            return False, f"Telegram API Error: {data.get('description', 'Unknown error')}"
                    elif resp.status_code == 429:
                        time.sleep(2.0)
                        continue
                    else:
                        return False, f"Telegram API returned HTTP {resp.status_code}: {resp.text}"
            except Exception as e:
                if attempt == max_retries - 1:
                    return False, f"HTTP Connection Exception: {str(e)}"
                time.sleep(1.0)
        return False, "Exceeded maximum retry attempts"
