from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import secrets
import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager

from ..storage import Storage, DEFAULT_DB_PATH
from ..models import WebhookConfig, FeedConfig, RouteConfig
from ..engine import RSSEngine
from ..discord_client import DiscordWebhookClient
from ..telegram_client import TelegramClient
from ..rss_parser import RSSFetcher

logger = logging.getLogger("rss2discord.server")
security = HTTPBasic(auto_error=False)

def create_app(
    db_path: str = DEFAULT_DB_PATH,
    auth_user: Optional[str] = None,
    auth_pass: Optional[str] = None,
    enable_background_poll: bool = True,
    poll_interval_seconds: int = 300
) -> FastAPI:

    storage = Storage(db_path)
    engine = RSSEngine(storage)
    discord_client = DiscordWebhookClient()
    telegram_client = TelegramClient()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        poll_task = None
        if enable_background_poll:
            async def poll_worker():
                logger.info(f"Background RSS polling worker started (checking every {poll_interval_seconds}s)")
                while True:
                    await asyncio.sleep(poll_interval_seconds)
                    try:
                        logger.info("Background worker executing RSS sync cycle...")
                        res = await asyncio.to_thread(engine.run_sync)
                        logger.info(f"Background worker sync complete: {res.get('items_dispatched', 0)} items dispatched.")
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Error in background polling worker: {e}")

            poll_task = asyncio.create_task(poll_worker())

        yield

        if poll_task:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="RSS to Discord Router", version="1.0.0", lifespan=lifespan)

    # Determine authentication credentials from arguments or environment variables
    env_user = auth_user or os.getenv("ADMIN_USER") or os.getenv("RSS2DISCORD_AUTH_USER")
    env_pass = auth_pass or os.getenv("ADMIN_PASS") or os.getenv("RSS2DISCORD_AUTH_PASS")

    def verify_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
        # If authentication credentials are not configured, allow access
        if not env_user or not env_pass:
            return True

        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": 'Basic realm="RSS-to-Discord Router Dashboard"'},
            )

        is_user_correct = secrets.compare_digest(credentials.username.encode("utf-8"), env_user.encode("utf-8"))
        is_pass_correct = secrets.compare_digest(credentials.password.encode("utf-8"), env_pass.encode("utf-8"))

        if not (is_user_correct and is_pass_correct):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": 'Basic realm="RSS-to-Discord Router Dashboard"'},
            )
        return True

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    os.makedirs(static_dir, exist_ok=True)

    # Apply authentication dependency globally to protected API endpoints
    auth_dep = [Depends(verify_auth)]

    # --- REST API Routes ---
    @app.get("/api/stats", dependencies=auth_dep)
    def get_stats():
        return storage.get_stats()

    # Webhooks
    @app.get("/api/webhooks", dependencies=auth_dep)
    def list_webhooks():
        return [w.to_dict() for w in storage.list_webhooks()]

    @app.post("/api/webhooks", dependencies=auth_dep)
    def save_webhook(data: Dict[str, Any]):
        webhook = WebhookConfig.from_dict(data)
        saved = storage.save_webhook(webhook)
        return saved.to_dict()

    @app.delete("/api/webhooks/{webhook_id}", dependencies=auth_dep)
    def delete_webhook(webhook_id: str):
        success = storage.delete_webhook(webhook_id)
        if not success:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"status": "deleted"}

    @app.post("/api/webhooks/{webhook_id}/test", dependencies=auth_dep)
    def test_webhook(webhook_id: str):
        webhook = storage.get_webhook(webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook/Destination not found")
        
        target_type = getattr(webhook, "target_type", "discord") or "discord"
        if target_type == "telegram":
            success, error = telegram_client.send_test_message(webhook.telegram_bot_token or "", webhook.telegram_chat_id or "", webhook.name)
        else:
            success, error = discord_client.send_test_message(webhook.url, webhook.name, webhook.username)

        if not success:
            raise HTTPException(status_code=400, detail=error or "Failed to send test message")
        return {"status": "success", "message": f"Test message sent to '{webhook.name}'"}

    # Feeds
    @app.get("/api/feeds", dependencies=auth_dep)
    def list_feeds():
        return [f.to_dict() for f in storage.list_feeds()]

    @app.post("/api/feeds", dependencies=auth_dep)
    def save_feed(data: Dict[str, Any]):
        feed = FeedConfig.from_dict(data)
        saved = storage.save_feed(feed)
        return saved.to_dict()

    @app.delete("/api/feeds/{feed_id}", dependencies=auth_dep)
    def delete_feed(feed_id: str):
        success = storage.delete_feed(feed_id)
        if not success:
            raise HTTPException(status_code=404, detail="Feed not found")
        return {"status": "deleted"}

    @app.post("/api/feeds/{feed_id}/fetch", dependencies=auth_dep)
    def fetch_single_feed(feed_id: str):
        feed = storage.get_feed(feed_id)
        if not feed:
            raise HTTPException(status_code=404, detail="Feed not found")
        result = engine.run_sync(feed_id=feed_id)
        return result

    @app.post("/api/feeds/preview", dependencies=auth_dep)
    def preview_feed(data: Dict[str, Any]):
        url = data.get("url")
        if not url:
            raise HTTPException(status_code=400, detail="Missing feed URL")
        fetcher = RSSFetcher()
        items, error = fetcher.fetch_feed("preview", url)
        if error:
            raise HTTPException(status_code=400, detail=error)
        return {
            "count": len(items),
            "items": [
                {
                    "title": item.title,
                    "link": item.link,
                    "guid": item.guid,
                    "description": item.description,
                    "published": item.published,
                    "author": item.author,
                    "image_url": item.image_url,
                    "item_hash": item.item_hash
                } for item in items[:10]  # preview first 10 items
            ]
        }

    # Routes
    @app.get("/api/routes", dependencies=auth_dep)
    def list_routes():
        return [r.to_dict() for r in storage.list_routes()]

    @app.post("/api/routes", dependencies=auth_dep)
    def save_route(data: Dict[str, Any]):
        route = RouteConfig.from_dict(data)
        saved = storage.save_route(route)
        return saved.to_dict()

    @app.delete("/api/routes/{route_id}", dependencies=auth_dep)
    def delete_route(route_id: str):
        success = storage.delete_route(route_id)
        if not success:
            raise HTTPException(status_code=404, detail="Route not found")
        return {"status": "deleted"}

    # Logs
    @app.get("/api/logs", dependencies=auth_dep)
    def list_logs(limit: int = 50):
        return [l.to_dict() for l in storage.list_logs(limit)]

    # Manual Sync Trigger
    @app.post("/api/sync", dependencies=auth_dep)
    def trigger_sync():
        result = engine.run_sync()
        return result

    # Config Export / Import
    @app.get("/api/config/export", dependencies=auth_dep)
    def export_config():
        yaml_str = storage.export_yaml()
        return Response(content=yaml_str, media_type="application/x-yaml", headers={"Content-Disposition": "attachment; filename=rss2discord.yaml"})

    @app.post("/api/config/import", dependencies=auth_dep)
    async def import_config(file: UploadFile = File(...)):
        content = await file.read()
        storage.import_yaml(content.decode("utf-8"))
        return {"status": "imported"}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    # Serve static assets (protected by auth)
    @app.get("/", dependencies=auth_dep)
    def read_index():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return HTMLResponse("<h2>RSS to Discord Router API</h2>")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
