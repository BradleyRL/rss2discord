import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone

from .storage import Storage
from .models import FeedConfig, WebhookConfig, RouteConfig, FeedItem, DeliveryLog
from .rss_parser import RSSFetcher
from .discord_client import DiscordWebhookClient

logger = logging.getLogger(__name__)

def matches_filters(item: FeedItem, feed: FeedConfig) -> bool:
    text_corpus = f"{item.title} {item.description}".lower()

    # Exclude filter check
    if feed.exclude_keywords:
        for kw in feed.exclude_keywords:
            if kw.lower() in text_corpus:
                return False

    # Include filter check
    if feed.include_keywords:
        matched_any = False
        for kw in feed.include_keywords:
            if kw.lower() in text_corpus:
                matched_any = True
                break
        if not matched_any:
            return False

    return True

class RSSEngine:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.fetcher = RSSFetcher()
        self.discord_client = DiscordWebhookClient()

    def run_sync(self, feed_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs a sync cycle across all enabled feeds (or a single feed if specified).
        Returns a summary report of items fetched, dispatched, skipped, and errors.
        """
        all_feeds = self.storage.list_feeds()
        if feed_id:
            all_feeds = [f for f in all_feeds if f.id == feed_id]
        else:
            all_feeds = [f for f in all_feeds if f.enabled]

        all_routes = [r for r in self.storage.list_routes() if r.enabled]
        all_webhooks = {w.id: w for w in self.storage.list_webhooks() if w.enabled}

        stats = {
            "feeds_processed": 0,
            "items_found": 0,
            "items_dispatched": 0,
            "items_skipped_duplicate": 0,
            "items_skipped_filter": 0,
            "errors": []
        }

        for feed in all_feeds:
            stats["feeds_processed"] += 1
            # Find routes for this feed
            feed_routes = [r for r in all_routes if r.feed_id == feed.id and r.webhook_id in all_webhooks]
            
            if not feed_routes:
                logger.info(f"Feed '{feed.name}' has no enabled route mappings. Skipping fetch.")
                self.storage.update_feed_fetch_status(feed.id, "ok_no_routes")
                continue

            items, fetch_error = self.fetcher.fetch_feed(feed.id, feed.url)
            if fetch_error:
                logger.error(f"Error fetching feed '{feed.name}': {fetch_error}")
                self.storage.update_feed_fetch_status(feed.id, "error", fetch_error)
                stats["errors"].append({"feed_name": feed.name, "error": fetch_error})
                continue

            is_first_fetch = (
                feed.last_fetched_at is None or
                feed.last_status in ("never_fetched", "ok_no_routes", "no_routes") or
                not self.storage.has_sent_items_for_feed(feed.id)
            )
            self.storage.update_feed_fetch_status(feed.id, "ok")
            stats["items_found"] += len(items)

            # Filter items matching feed keyword rules
            matching_items = [item for item in items if matches_filters(item, feed)]
            stats["items_skipped_filter"] += (len(items) - len(matching_items))

            # Restrict initial dispatch on first run for newly added feed
            if is_first_fetch and items:
                init_mode = getattr(feed, "initial_fetch_mode", "latest_only") or "latest_only"
                if init_mode == "latest_only":
                    if matching_items:
                        target_item = matching_items[0]
                        items_to_process = [target_item]
                        for other_item in items:
                            if other_item.item_hash != target_item.item_hash:
                                for route in feed_routes:
                                    self.storage.mark_item_sent(other_item.item_hash, feed.id, route.webhook_id)
                        logger.info(f"First run for feed '{feed.name}': Sending 1 latest story ('{target_item.title}'), muting {len(items)-1} historical stories.")
                    else:
                        items_to_process = []
                        for other_item in items:
                            for route in feed_routes:
                                self.storage.mark_item_sent(other_item.item_hash, feed.id, route.webhook_id)
                elif init_mode == "mute_all":
                    items_to_process = []
                    for muted_item in items:
                        for route in feed_routes:
                            self.storage.mark_item_sent(muted_item.item_hash, feed.id, route.webhook_id)
                    logger.info(f"First run for feed '{feed.name}': Muted all {len(items)} historical stories.")
                else:
                    items_to_process = matching_items
            else:
                items_to_process = matching_items

            for item in items_to_process:
                item_hash = item.item_hash

                for route in feed_routes:
                    webhook = all_webhooks[route.webhook_id]

                    # Check duplicate
                    if self.storage.is_item_sent(item_hash, webhook.id):
                        stats["items_skipped_duplicate"] += 1
                        continue

                    # Send to Discord
                    success, error_msg = self.discord_client.send_embed(webhook, item, feed, route)

                    log_entry = DeliveryLog(
                        feed_id=feed.id,
                        feed_name=feed.name,
                        webhook_id=webhook.id,
                        webhook_name=webhook.name,
                        route_id=route.id,
                        item_title=item.title,
                        item_link=item.link,
                        item_hash=item_hash,
                        status="success" if success else "failed",
                        error_message=error_msg,
                        delivered_at=datetime.now(timezone.utc).isoformat()
                    )

                    if success:
                        self.storage.mark_item_sent(item_hash, feed.id, webhook.id)
                        self.storage.add_log(log_entry)
                        stats["items_dispatched"] += 1
                        logger.info(f"Dispatched item '{item.title}' from feed '{feed.name}' to webhook '{webhook.name}'")
                    else:
                        self.storage.add_log(log_entry)
                        logger.error(f"Failed dispatching item '{item.title}' to webhook '{webhook.name}': {error_msg}")
                        stats["errors"].append({"feed_name": feed.name, "webhook_name": webhook.name, "error": error_msg})

        return stats
