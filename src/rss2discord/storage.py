import sqlite3
import json
import os
import yaml
import uuid
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from .models import WebhookConfig, FeedConfig, RouteConfig, DeliveryLog

DEFAULT_DB_PATH = "rss2discord.db"

class Storage:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT DEFAULT '',
                    avatar_url TEXT,
                    username TEXT,
                    color TEXT DEFAULT '#5865F2',
                    enabled INTEGER DEFAULT 1,
                    target_type TEXT DEFAULT 'discord',
                    telegram_bot_token TEXT,
                    telegram_chat_id TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            try:
                cursor.execute("ALTER TABLE webhooks ADD COLUMN target_type TEXT DEFAULT 'discord'")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE webhooks ADD COLUMN telegram_bot_token TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE webhooks ADD COLUMN telegram_chat_id TEXT")
            except sqlite3.OperationalError:
                pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS feeds (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    fetch_interval_minutes INTEGER DEFAULT 15,
                    enabled INTEGER DEFAULT 1,
                    include_keywords TEXT DEFAULT '[]',
                    exclude_keywords TEXT DEFAULT '[]',
                    custom_color TEXT,
                    initial_fetch_mode TEXT DEFAULT 'latest_only',
                    last_fetched_at TEXT,
                    last_status TEXT DEFAULT 'never_fetched',
                    last_error TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            try:
                cursor.execute("ALTER TABLE feeds ADD COLUMN initial_fetch_mode TEXT DEFAULT 'latest_only'")
            except sqlite3.OperationalError:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS routes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    feed_id TEXT NOT NULL,
                    webhook_id TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    message_prefix TEXT,
                    override_color TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
                    FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_history (
                    item_hash TEXT NOT NULL,
                    feed_id TEXT NOT NULL,
                    webhook_id TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (item_hash, webhook_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS delivery_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_id TEXT,
                    feed_name TEXT,
                    webhook_id TEXT,
                    webhook_name TEXT,
                    route_id TEXT,
                    item_title TEXT,
                    item_link TEXT,
                    item_hash TEXT,
                    status TEXT,
                    error_message TEXT,
                    delivered_at TEXT
                )
            """)
            conn.commit()

    # --- Webhooks ---
    def save_webhook(self, webhook: WebhookConfig) -> WebhookConfig:
        if not webhook.id:
            webhook.id = str(uuid.uuid4())
        target_type = getattr(webhook, "target_type", "discord") or "discord"
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO webhooks (id, name, url, avatar_url, username, color, enabled, target_type, telegram_bot_token, telegram_chat_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    url=excluded.url,
                    avatar_url=excluded.avatar_url,
                    username=excluded.username,
                    color=excluded.color,
                    enabled=excluded.enabled,
                    target_type=excluded.target_type,
                    telegram_bot_token=excluded.telegram_bot_token,
                    telegram_chat_id=excluded.telegram_chat_id
            """, (
                webhook.id, webhook.name, webhook.url, webhook.avatar_url,
                webhook.username, webhook.color, 1 if webhook.enabled else 0,
                target_type, webhook.telegram_bot_token, webhook.telegram_chat_id,
                webhook.created_at
            ))
            conn.commit()
        return webhook

    def get_webhook(self, webhook_id: str) -> Optional[WebhookConfig]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
            if row:
                keys = row.keys()
                return WebhookConfig(
                    id=row["id"], name=row["name"], url=row["url"] or "",
                    avatar_url=row["avatar_url"], username=row["username"],
                    color=row["color"], enabled=bool(row["enabled"]),
                    target_type=row["target_type"] if "target_type" in keys else "discord",
                    telegram_bot_token=row["telegram_bot_token"] if "telegram_bot_token" in keys else None,
                    telegram_chat_id=row["telegram_chat_id"] if "telegram_chat_id" in keys else None,
                    created_at=row["created_at"]
                )
        return None

    def list_webhooks(self) -> List[WebhookConfig]:
        webhooks = []
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM webhooks ORDER BY name ASC").fetchall()
            for row in rows:
                keys = row.keys()
                webhooks.append(WebhookConfig(
                    id=row["id"], name=row["name"], url=row["url"] or "",
                    avatar_url=row["avatar_url"], username=row["username"],
                    color=row["color"], enabled=bool(row["enabled"]),
                    target_type=row["target_type"] if "target_type" in keys else "discord",
                    telegram_bot_token=row["telegram_bot_token"] if "telegram_bot_token" in keys else None,
                    telegram_chat_id=row["telegram_chat_id"] if "telegram_chat_id" in keys else None,
                    created_at=row["created_at"]
                ))
        return webhooks

    def delete_webhook(self, webhook_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
            conn.execute("DELETE FROM routes WHERE webhook_id = ?", (webhook_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Feeds ---
    def save_feed(self, feed: FeedConfig) -> FeedConfig:
        if not feed.id:
            feed.id = str(uuid.uuid4())
        inc_json = json.dumps(feed.include_keywords)
        exc_json = json.dumps(feed.exclude_keywords)
        initial_mode = getattr(feed, "initial_fetch_mode", "latest_only") or "latest_only"
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO feeds (id, name, url, fetch_interval_minutes, enabled, include_keywords, exclude_keywords, custom_color, initial_fetch_mode, last_fetched_at, last_status, last_error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    url=excluded.url,
                    fetch_interval_minutes=excluded.fetch_interval_minutes,
                    enabled=excluded.enabled,
                    include_keywords=excluded.include_keywords,
                    exclude_keywords=excluded.exclude_keywords,
                    custom_color=excluded.custom_color,
                    initial_fetch_mode=excluded.initial_fetch_mode,
                    last_fetched_at=excluded.last_fetched_at,
                    last_status=excluded.last_status,
                    last_error=excluded.last_error
            """, (
                feed.id, feed.name, feed.url, feed.fetch_interval_minutes,
                1 if feed.enabled else 0, inc_json, exc_json, feed.custom_color,
                initial_mode, feed.last_fetched_at, feed.last_status, feed.last_error, feed.created_at
            ))
            conn.commit()
        return feed

    def update_feed_fetch_status(self, feed_id: str, status: str, error: Optional[str] = None):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            if status == "ok_no_routes":
                conn.execute("""
                    UPDATE feeds SET last_status = ?, last_error = ? WHERE id = ?
                """, (status, error, feed_id))
            else:
                conn.execute("""
                    UPDATE feeds SET last_fetched_at = ?, last_status = ?, last_error = ? WHERE id = ?
                """, (now, status, error, feed_id))
            conn.commit()

    def get_feed(self, feed_id: str) -> Optional[FeedConfig]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
            if row:
                return FeedConfig(
                    id=row["id"], name=row["name"], url=row["url"],
                    fetch_interval_minutes=row["fetch_interval_minutes"],
                    enabled=bool(row["enabled"]),
                    include_keywords=json.loads(row["include_keywords"] or "[]"),
                    exclude_keywords=json.loads(row["exclude_keywords"] or "[]"),
                    custom_color=row["custom_color"],
                    initial_fetch_mode=row["initial_fetch_mode"] if "initial_fetch_mode" in row.keys() else "latest_only",
                    last_fetched_at=row["last_fetched_at"],
                    last_status=row["last_status"],
                    last_error=row["last_error"],
                    created_at=row["created_at"]
                )
        return None

    def list_feeds(self) -> List[FeedConfig]:
        feeds = []
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM feeds ORDER BY name ASC").fetchall()
            for row in rows:
                feeds.append(FeedConfig(
                    id=row["id"], name=row["name"], url=row["url"],
                    fetch_interval_minutes=row["fetch_interval_minutes"],
                    enabled=bool(row["enabled"]),
                    include_keywords=json.loads(row["include_keywords"] or "[]"),
                    exclude_keywords=json.loads(row["exclude_keywords"] or "[]"),
                    custom_color=row["custom_color"],
                    initial_fetch_mode=row["initial_fetch_mode"] if "initial_fetch_mode" in row.keys() else "latest_only",
                    last_fetched_at=row["last_fetched_at"],
                    last_status=row["last_status"],
                    last_error=row["last_error"],
                    created_at=row["created_at"]
                ))
        return feeds

    def delete_feed(self, feed_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
            conn.execute("DELETE FROM routes WHERE feed_id = ?", (feed_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Routes ---
    def save_route(self, route: RouteConfig) -> RouteConfig:
        if not route.id:
            route.id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO routes (id, name, feed_id, webhook_id, enabled, message_prefix, override_color, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    feed_id=excluded.feed_id,
                    webhook_id=excluded.webhook_id,
                    enabled=excluded.enabled,
                    message_prefix=excluded.message_prefix,
                    override_color=excluded.override_color
            """, (
                route.id, route.name, route.feed_id, route.webhook_id,
                1 if route.enabled else 0, route.message_prefix, route.override_color,
                route.created_at
            ))
            conn.commit()
        return route

    def list_routes(self) -> List[RouteConfig]:
        routes = []
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM routes ORDER BY name ASC").fetchall()
            for row in rows:
                routes.append(RouteConfig(
                    id=row["id"], name=row["name"], feed_id=row["feed_id"],
                    webhook_id=row["webhook_id"], enabled=bool(row["enabled"]),
                    message_prefix=row["message_prefix"], override_color=row["override_color"],
                    created_at=row["created_at"]
                ))
        return routes

    def delete_route(self, route_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Sent History & Logs ---
    def is_item_sent(self, item_hash: str, webhook_id: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM sent_history WHERE item_hash = ? AND webhook_id = ?",
                (item_hash, webhook_id)
            ).fetchone()
            return row is not None

    def has_sent_items_for_feed(self, feed_id: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM sent_history WHERE feed_id = ?",
                (feed_id,)
            ).fetchone()
            return row is not None

    def mark_item_sent(self, item_hash: str, feed_id: str, webhook_id: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO sent_history (item_hash, feed_id, webhook_id, sent_at)
                VALUES (?, ?, ?, ?)
            """, (item_hash, feed_id, webhook_id, now))
            conn.commit()

    def add_log(self, log: DeliveryLog):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO delivery_logs (feed_id, feed_name, webhook_id, webhook_name, route_id, item_title, item_link, item_hash, status, error_message, delivered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log.feed_id, log.feed_name, log.webhook_id, log.webhook_name,
                log.route_id, log.item_title, log.item_link, log.item_hash,
                log.status, log.error_message, log.delivered_at
            ))
            conn.commit()

    def list_logs(self, limit: int = 50) -> List[DeliveryLog]:
        logs = []
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM delivery_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            for row in rows:
                logs.append(DeliveryLog(
                    id=row["id"], feed_id=row["feed_id"] or "", feed_name=row["feed_name"] or "",
                    webhook_id=row["webhook_id"] or "", webhook_name=row["webhook_name"] or "",
                    route_id=row["route_id"] or "", item_title=row["item_title"] or "",
                    item_link=row["item_link"] or "", item_hash=row["item_hash"] or "",
                    status=row["status"] or "unknown", error_message=row["error_message"],
                    delivered_at=row["delivered_at"] or ""
                ))
        return logs

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total_feeds = conn.execute("SELECT COUNT(*) FROM feeds").fetchone()[0]
            active_feeds = conn.execute("SELECT COUNT(*) FROM feeds WHERE enabled = 1").fetchone()[0]
            total_webhooks = conn.execute("SELECT COUNT(*) FROM webhooks").fetchone()[0]
            total_routes = conn.execute("SELECT COUNT(*) FROM routes WHERE enabled = 1").fetchone()[0]
            total_dispatched = conn.execute("SELECT COUNT(*) FROM sent_history").fetchone()[0]
            failed_logs = conn.execute("SELECT COUNT(*) FROM delivery_logs WHERE status = 'failed'").fetchone()[0]
            success_logs = conn.execute("SELECT COUNT(*) FROM delivery_logs WHERE status = 'success'").fetchone()[0]

        return {
            "total_feeds": total_feeds,
            "active_feeds": active_feeds,
            "total_webhooks": total_webhooks,
            "active_routes": total_routes,
            "total_dispatched": total_dispatched,
            "failed_dispatches": failed_logs,
            "successful_dispatches": success_logs
        }

    # --- YAML Import / Export ---
    def export_yaml(self) -> str:
        data = {
            "webhooks": [w.to_dict() for w in self.list_webhooks()],
            "feeds": [f.to_dict() for f in self.list_feeds()],
            "routes": [r.to_dict() for r in self.list_routes()]
        }
        return yaml.dump(data, sort_keys=False)

    def import_yaml(self, yaml_content: str):
        parsed = yaml.safe_load(yaml_content) or {}

        # Webhooks
        for w in parsed.get("webhooks", []):
            wh = WebhookConfig.from_dict(w)
            self.save_webhook(wh)

        # Feeds
        for f in parsed.get("feeds", []):
            fd = FeedConfig.from_dict(f)
            self.save_feed(fd)

        # Routes
        for r in parsed.get("routes", []):
            rt = RouteConfig.from_dict(r)
            self.save_route(rt)
