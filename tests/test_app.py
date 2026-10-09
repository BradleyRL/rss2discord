import unittest
import os
import shutil
import tempfile
from src.rss2discord.models import FeedConfig, WebhookConfig, RouteConfig, FeedItem, DeliveryLog
from src.rss2discord.storage import Storage
from src.rss2discord.rss_parser import clean_html_to_markdown, extract_image_url
from src.rss2discord.engine import matches_filters
from src.rss2discord.discord_client import DiscordWebhookClient, hex_to_int

class TestRSS2Discord(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_rss2discord.db")
        self.storage = Storage(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_storage_webhooks(self):
        wh = WebhookConfig(id="", name="Test WH", url="https://discord.com/api/webhooks/test", color="#FF0000")
        saved = self.storage.save_webhook(wh)
        self.assertTrue(saved.id)
        
        retrieved = self.storage.get_webhook(saved.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Test WH")
        self.assertEqual(retrieved.color, "#FF0000")

        all_wh = self.storage.list_webhooks()
        self.assertEqual(len(all_wh), 1)

        self.storage.delete_webhook(saved.id)
        self.assertEqual(len(self.storage.list_webhooks()), 0)

    def test_storage_feeds(self):
        fd = FeedConfig(id="", name="HN Feed", url="https://news.ycombinator.com/rss", include_keywords=["python"], exclude_keywords=["crypto"])
        saved = self.storage.save_feed(fd)
        self.assertTrue(saved.id)

        retrieved = self.storage.get_feed(saved.id)
        self.assertEqual(retrieved.include_keywords, ["python"])
        self.assertEqual(retrieved.exclude_keywords, ["crypto"])

    def test_storage_routes_and_duplicate_prevention(self):
        wh = self.storage.save_webhook(WebhookConfig(id="", name="WH", url="http://test"))
        fd = self.storage.save_feed(FeedConfig(id="", name="Feed", url="http://test"))
        rt = self.storage.save_route(RouteConfig(id="", name="Route", feed_id=fd.id, webhook_id=wh.id))

        item_hash = "abc123hash"
        self.assertFalse(self.storage.is_item_sent(item_hash, wh.id))

        self.storage.mark_item_sent(item_hash, fd.id, wh.id)
        self.assertTrue(self.storage.is_item_sent(item_hash, wh.id))

    def test_html_cleaner(self):
        raw_html = '<p>Check out <a href="https://example.com"><b>this article</b></a> about Python!</p><br><script>alert("xss")</script>'
        cleaned = clean_html_to_markdown(raw_html)
        self.assertIn("[this article](https://example.com)", cleaned)
        self.assertNotIn("alert", cleaned)
        self.assertNotIn("<p>", cleaned)

    def test_keyword_filters(self):
        fd = FeedConfig(id="1", name="F", url="U", include_keywords=["python", "ai"], exclude_keywords=["spam"])

        item_pass = FeedItem(feed_id="1", title="New Python 3.14 Release", link="L", guid="G", description="Awesome update")
        self.assertTrue(matches_filters(item_pass, fd))

        item_fail_include = FeedItem(feed_id="1", title="Java update", link="L", guid="G", description="Boring text")
        self.assertFalse(matches_filters(item_fail_include, fd))

        item_fail_exclude = FeedItem(feed_id="1", title="Python spam offer", link="L", guid="G", description="Get cheap spam now")
        self.assertFalse(matches_filters(item_fail_exclude, fd))

    def test_hex_color(self):
        self.assertEqual(hex_to_int("#FF0000"), 0xFF0000)
        self.assertEqual(hex_to_int("5865F2"), 0x5865F2)

if __name__ == "__main__":
    unittest.main()
