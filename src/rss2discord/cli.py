import argparse
import sys
import os
import time
import logging
import uvicorn
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from .storage import Storage, DEFAULT_DB_PATH
from .engine import RSSEngine
from .discord_client import DiscordWebhookClient
from .models import FeedConfig, WebhookConfig, RouteConfig
from .web.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("rss2discord.cli")

def main():
    parser = argparse.ArgumentParser(description="RSS-to-Discord Router: Read RSS feeds and send rich embeds to multiple Discord webhooks.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to SQLite database file")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="Run continuous background daemon to poll feeds periodically")
    p_daemon.add_argument("--interval", type=int, default=300, help="Daemon poll loop check interval in seconds (default: 300)")

    # sync
    p_sync = subparsers.add_parser("sync", help="Run a single feed polling and dispatch cycle")
    p_sync.add_argument("--feed-id", help="Optional specific feed ID to sync")

    # serve
    default_host = os.getenv("HOST", "0.0.0.0")
    default_port = int(os.getenv("PORT", "8000"))
    p_serve = subparsers.add_parser("serve", help="Launch the Web UI Dashboard & REST API server")
    p_serve.add_argument("--host", default=default_host, help=f"Host address (default: {default_host})")
    p_serve.add_argument("--port", type=int, default=default_port, help=f"Port number (default: {default_port})")
    p_serve.add_argument("--auth", help="Enable Basic Auth formatted as 'username:password'")
    p_serve.add_argument("--auth-user", default=os.getenv("ADMIN_USER"), help="Basic Auth username (or ADMIN_USER env var)")
    p_serve.add_argument("--auth-pass", default=os.getenv("ADMIN_PASS"), help="Basic Auth password (or ADMIN_PASS env var)")

    # test-webhook
    p_test = subparsers.add_parser("test-webhook", help="Send a test message to a Discord Webhook URL")
    p_test.add_argument("url", help="Discord Webhook URL")
    p_test.add_argument("--name", default="Test Webhook", help="Custom webhook name")

    # add-webhook
    p_add_wh = subparsers.add_parser("add-webhook", help="Add a new Discord Webhook")
    p_add_wh.add_argument("--name", required=True, help="Webhook name")
    p_add_wh.add_argument("--url", required=True, help="Webhook URL")
    p_add_wh.add_argument("--color", default="#5865F2", help="Embed accent hex color")
    p_add_wh.add_argument("--username", help="Override Discord username")
    p_add_wh.add_argument("--avatar", help="Override Discord avatar URL")

    # add-feed
    p_add_feed = subparsers.add_parser("add-feed", help="Add a new RSS Feed")
    p_add_feed.add_argument("--name", required=True, help="Feed name")
    p_add_feed.add_argument("--url", required=True, help="RSS / Atom feed URL")
    p_add_feed.add_argument("--interval", type=int, default=15, help="Poll interval in minutes")
    p_add_feed.add_argument("--include", help="Comma-separated keywords to include")
    p_add_feed.add_argument("--exclude", help="Comma-separated keywords to exclude")

    # add-route
    p_add_route = subparsers.add_parser("add-route", help="Link a Feed to a Webhook")
    p_add_route.add_argument("--name", required=True, help="Route name")
    p_add_route.add_argument("--feed-id", required=True, help="Source Feed ID")
    p_add_route.add_argument("--webhook-id", required=True, help="Target Webhook ID")
    p_add_route.add_argument("--prefix", help="Message prefix (e.g. @everyone)")

    # list
    subparsers.add_parser("list", help="List configured webhooks, feeds, and routes")

    # export-config
    p_export = subparsers.add_parser("export-config", help="Export database setup to YAML format")
    p_export.add_argument("-o", "--output", default="config.yaml", help="Output YAML filename")

    # import-config
    p_import = subparsers.add_parser("import-config", help="Import feeds, webhooks, and routes from YAML file")
    p_import.add_argument("file", help="Path to YAML file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    storage = Storage(args.db)

    if args.command == "serve":
        auth_user = args.auth_user
        auth_pass = args.auth_pass
        if args.auth and ":" in args.auth:
            auth_user, auth_pass = args.auth.split(":", 1)

        app = create_app(args.db, auth_user=auth_user, auth_pass=auth_pass)
        
        effective_user = auth_user or os.getenv("ADMIN_USER") or os.getenv("RSS2DISCORD_AUTH_USER")
        if effective_user:
            logger.info(f"Basic Auth enabled for dashboard (User: '{effective_user}')")
        else:
            logger.warning("Basic Auth disabled. Dashboard is accessible without authentication.")

        logger.info(f"Starting RSS-to-Discord Router Web Dashboard on http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.command == "sync":
        engine = RSSEngine(storage)
        logger.info("Executing sync cycle...")
        result = engine.run_sync(feed_id=args.feed_id)
        logger.info(f"Sync complete! Processed: {result['feeds_processed']} feeds, Dispatched: {result['items_dispatched']} items, Skipped: {result['items_skipped_duplicate']} duplicates.")

    elif args.command == "daemon":
        engine = RSSEngine(storage)
        logger.info(f"Starting RSS-to-Discord Router Daemon loop (Checking every {args.interval}s)... Press Ctrl+C to stop.")
        try:
            while True:
                logger.info("Daemon running scheduled sync...")
                res = engine.run_sync()
                logger.info(f"Daemon sync complete: {res['items_dispatched']} items dispatched.")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")

    elif args.command == "test-webhook":
        client = DiscordWebhookClient()
        success, error = client.send_test_message(args.url, args.name)
        if success:
            logger.info(f"SUCCESS: Test message sent to '{args.name}'")
        else:
            logger.error(f"FAILURE: Could not send test message: {error}")
            sys.exit(1)

    elif args.command == "add-webhook":
        wh = WebhookConfig(
            id="",
            name=args.name,
            url=args.url,
            color=args.color,
            username=args.username,
            avatar_url=args.avatar
        )
        saved = storage.save_webhook(wh)
        logger.info(f"Saved Webhook: ID='{saved.id}', Name='{saved.name}'")

    elif args.command == "add-feed":
        inc = [k.strip() for k in args.include.split(",")] if args.include else []
        exc = [k.strip() for k in args.exclude.split(",")] if args.exclude else []
        fd = FeedConfig(
            id="",
            name=args.name,
            url=args.url,
            fetch_interval_minutes=args.interval,
            include_keywords=inc,
            exclude_keywords=exc
        )
        saved = storage.save_feed(fd)
        logger.info(f"Saved Feed: ID='{saved.id}', Name='{saved.name}'")

    elif args.command == "add-route":
        rt = RouteConfig(
            id="",
            name=args.name,
            feed_id=args.feed_id,
            webhook_id=args.webhook_id,
            message_prefix=args.prefix
        )
        saved = storage.save_route(rt)
        logger.info(f"Saved Route: ID='{saved.id}', Name='{saved.name}'")

    elif args.command == "list":
        webhooks = storage.list_webhooks()
        feeds = storage.list_feeds()
        routes = storage.list_routes()

        print("\n--- WEBHOOKS ---")
        for w in webhooks:
            print(f"[{w.id[:8]}] {w.name} -> {w.url[:40]}... (Color: {w.color})")

        print("\n--- FEEDS ---")
        for f in feeds:
            print(f"[{f.id[:8]}] {f.name} -> {f.url} (Interval: {f.fetch_interval_minutes}m, Status: {f.last_status})")

        print("\n--- ROUTES ---")
        for r in routes:
            print(f"[{r.id[:8]}] {r.name}: Feed[{r.feed_id[:8]}] -> Webhook[{r.webhook_id[:8]}]")
        print()

    elif args.command == "export-config":
        yaml_data = storage.export_yaml()
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(yaml_data)
        logger.info(f"Exported configuration to {args.output}")

    elif args.command == "import-config":
        with open(args.file, "r", encoding="utf-8") as f:
            yaml_data = f.read()
        storage.import_yaml(yaml_data)
        logger.info(f"Successfully imported configuration from {args.file}")

if __name__ == "__main__":
    main()
