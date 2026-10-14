import unittest
import os
import shutil
import tempfile
from fastapi.testclient import TestClient
from src.rss2discord.models import FeedConfig, WebhookConfig, RouteConfig, FeedItem, DeliveryLog
from src.rss2discord.storage import Storage
from src.rss2discord.rss_parser import clean_html_to_markdown, extract_image_url
from src.rss2discord.engine import matches_filters
from src.rss2discord.discord_client import DiscordWebhookClient, hex_to_int, sanitize_username
from src.rss2discord.web.server import create_app

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

    def test_username_sanitization(self):
        self.assertEqual(sanitize_username("RSS-to-Discord Router"), "RSS-to-FeedHub Router")
        self.assertEqual(sanitize_username("Discord Updates"), "FeedHub Updates")
        self.assertEqual(sanitize_username("clyde@bot"), "Botbot")

    def test_initial_fetch_mode(self):
        fd = FeedConfig(id="f1", name="New Feed", url="http://test", initial_fetch_mode="latest_only")
        saved = self.storage.save_feed(fd)
        self.assertEqual(saved.initial_fetch_mode, "latest_only")

    def test_telegram_webhook_config(self):
        tg_wh = WebhookConfig(
            id="", name="Telegram Target", url="",
            target_type="telegram",
            telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57",
            telegram_chat_id="@my_rss_channel"
        )
        saved = self.storage.save_webhook(tg_wh)
        self.assertEqual(saved.target_type, "telegram")

        retrieved = self.storage.get_webhook(saved.id)
        self.assertEqual(retrieved.target_type, "telegram")
        self.assertEqual(retrieved.telegram_bot_token, "123456:ABC-DEF1234ghIkl-zyx57")
        self.assertEqual(retrieved.telegram_chat_id, "@my_rss_channel")

    def test_basic_auth(self):
        # App with Basic Auth enabled
        app_auth = create_app(db_path=self.db_path, auth_user="admin", auth_pass="secret123")
        client = TestClient(app_auth)

        # 1. Without credentials -> 401
        res_no_auth = client.get("/api/stats")
        self.assertEqual(res_no_auth.status_code, 401)

        # 2. Wrong credentials -> 401
        res_wrong_auth = client.get("/api/stats", auth=("admin", "wrongpass"))
        self.assertEqual(res_wrong_auth.status_code, 401)

        # 3. Correct credentials -> 200
        res_correct_auth = client.get("/api/stats", auth=("admin", "secret123"))
        self.assertEqual(res_correct_auth.status_code, 200)

        # App without Basic Auth enabled -> 200 without auth
        app_no_auth = create_app(db_path=self.db_path)
        client_no_auth = TestClient(app_no_auth)
        res_open = client_no_auth.get("/api/stats")
        self.assertEqual(res_open.status_code, 200)

    def test_new_route_first_run_only_sends_one_item_discord_and_telegram(self):
        from unittest.mock import MagicMock
        from src.rss2discord.engine import RSSEngine

        engine = RSSEngine(self.storage)

        # 5 historical items in feed
        feed_items = [
            FeedItem(feed_id="f1", title=f"Story {i}", link=f"http://test/{i}", guid=f"guid-{i}", description="desc")
            for i in range(5)
        ]

        engine.fetcher.fetch_feed = MagicMock(return_value=(feed_items, None))
        engine.discord_client.send_embed = MagicMock(return_value=(True, None))
        engine.telegram_client.send_message = MagicMock(return_value=(True, None))

        # 1. Add Feed with latest_only
        feed = self.storage.save_feed(FeedConfig(id="f1", name="Test Feed", url="http://feed.xml", initial_fetch_mode="latest_only"))

        # 2. Add Route 1 to Discord
        wh_discord = self.storage.save_webhook(WebhookConfig(id="wh-d1", name="Discord WH", url="http://discord/wh", target_type="discord"))
        self.storage.save_route(RouteConfig(id="r1", name="F1 -> Discord", feed_id=feed.id, webhook_id=wh_discord.id))

        # Sync 1: First run for Discord route
        stats1 = engine.run_sync()
        self.assertEqual(stats1["items_dispatched"], 1)
        self.assertEqual(engine.discord_client.send_embed.call_count, 1)
        self.assertEqual(engine.telegram_client.send_message.call_count, 0)
        self.assertEqual(engine.discord_client.send_embed.call_args[0][1].title, "Story 0")

        # Sync 2: Run again without changes -> 0 dispatched
        engine.discord_client.send_embed.reset_mock()
        engine.telegram_client.send_message.reset_mock()
        stats2 = engine.run_sync()
        self.assertEqual(stats2["items_dispatched"], 0)
        self.assertEqual(engine.discord_client.send_embed.call_count, 0)
        self.assertEqual(engine.telegram_client.send_message.call_count, 0)

        # 3. Add Route 2 to Telegram for the SAME Feed!
        wh_telegram = self.storage.save_webhook(WebhookConfig(
            id="wh-tg1", name="Telegram Target", url="", target_type="telegram",
            telegram_bot_token="token123", telegram_chat_id="@mychat"
        ))
        self.storage.save_route(RouteConfig(id="r2", name="F1 -> Telegram", feed_id=feed.id, webhook_id=wh_telegram.id))

        # Sync 3: First run for Telegram route
        engine.discord_client.send_embed.reset_mock()
        engine.telegram_client.send_message.reset_mock()
        stats3 = engine.run_sync()

        # Discord receives 0 items (no new items in feed)
        self.assertEqual(engine.discord_client.send_embed.call_count, 0)
        # Telegram receives EXACTLY 1 item (the latest story, NOT all 5!)
        self.assertEqual(engine.telegram_client.send_message.call_count, 1)
        self.assertEqual(stats3["items_dispatched"], 1)
        sent_tg_item = engine.telegram_client.send_message.call_args[0][1]
        self.assertEqual(sent_tg_item.title, "Story 0")

        # Sync 4: Run again -> 0 dispatched to either
        engine.discord_client.send_embed.reset_mock()
        engine.telegram_client.send_message.reset_mock()
        stats4 = engine.run_sync()
        self.assertEqual(stats4["items_dispatched"], 0)
        self.assertEqual(engine.discord_client.send_embed.call_count, 0)
        self.assertEqual(engine.telegram_client.send_message.call_count, 0)

        # 4. Now a brand new story arrives in the feed
        new_item = FeedItem(feed_id="f1", title="Brand New Story", link="http://test/new", guid="guid-new", description="new")
        engine.fetcher.fetch_feed = MagicMock(return_value=([new_item] + feed_items, None))

        # Sync 5: Both Discord and Telegram receive ONLY the 1 new item!
        engine.discord_client.send_embed.reset_mock()
        engine.telegram_client.send_message.reset_mock()
        stats5 = engine.run_sync()
        self.assertEqual(stats5["items_dispatched"], 2)
        self.assertEqual(engine.discord_client.send_embed.call_count, 1)
        self.assertEqual(engine.telegram_client.send_message.call_count, 1)
        self.assertEqual(engine.discord_client.send_embed.call_args[0][1].title, "Brand New Story")
        self.assertEqual(engine.telegram_client.send_message.call_args[0][1].title, "Brand New Story")

        # 5. Add a SECOND Discord route for the same feed (e.g. #announcements)
        wh_discord2 = self.storage.save_webhook(WebhookConfig(id="wh-d2", name="Discord 2", url="http://discord/wh2", target_type="discord"))
        self.storage.save_route(RouteConfig(id="r3", name="F1 -> Discord 2", feed_id=feed.id, webhook_id=wh_discord2.id))

        # Sync 6: First run for Discord 2
        engine.discord_client.send_embed.reset_mock()
        engine.telegram_client.send_message.reset_mock()
        stats6 = engine.run_sync()

        # Existing Discord 1 and Telegram receive 0
        # Discord 2 receives EXACTLY 1 item (the latest: Brand New Story)
        self.assertEqual(engine.telegram_client.send_message.call_count, 0)
        self.assertEqual(engine.discord_client.send_embed.call_count, 1)
        sent_to_d2 = engine.discord_client.send_embed.call_args[0][0]
        self.assertEqual(sent_to_d2.id, "wh-d2")
        self.assertEqual(engine.discord_client.send_embed.call_args[0][1].title, "Brand New Story")

if __name__ == "__main__":
    unittest.main()
