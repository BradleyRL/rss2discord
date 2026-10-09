from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import uvicorn

from ..storage import Storage, DEFAULT_DB_PATH
from ..models import WebhookConfig, FeedConfig, RouteConfig
from ..engine import RSSEngine
from ..discord_client import DiscordWebhookClient
from ..rss_parser import RSSFetcher

def create_app(db_path: str = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="RSS to Discord Router", version="1.0.0")
    storage = Storage(db_path)
    engine = RSSEngine(storage)
    discord_client = DiscordWebhookClient()

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    os.makedirs(static_dir, exist_ok=True)

    # --- REST API Routes ---
    @app.get("/api/stats")
    def get_stats():
        return storage.get_stats()

    # Webhooks
    @app.get("/api/webhooks")
    def list_webhooks():
        return [w.to_dict() for w in storage.list_webhooks()]

    @app.post("/api/webhooks")
    def save_webhook(data: Dict[str, Any]):
        webhook = WebhookConfig.from_dict(data)
        saved = storage.save_webhook(webhook)
        return saved.to_dict()

    @app.delete("/api/webhooks/{webhook_id}")
    def delete_webhook(webhook_id: str):
        success = storage.delete_webhook(webhook_id)
        if not success:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"status": "deleted"}

    @app.post("/api/webhooks/{webhook_id}/test")
    def test_webhook(webhook_id: str):
        webhook = storage.get_webhook(webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        success, error = discord_client.send_test_message(webhook.url, webhook.name)
        if not success:
            raise HTTPException(status_code=400, detail=error or "Failed to send test message")
        return {"status": "success", "message": f"Test message sent to '{webhook.name}'"}

    # Feeds
    @app.get("/api/feeds")
    def list_feeds():
        return [f.to_dict() for f in storage.list_feeds()]

    @app.post("/api/feeds")
    def save_feed(data: Dict[str, Any]):
        feed = FeedConfig.from_dict(data)
        saved = storage.save_feed(feed)
        return saved.to_dict()

    @app.delete("/api/feeds/{feed_id}")
    def delete_feed(feed_id: str):
        success = storage.delete_feed(feed_id)
        if not success:
            raise HTTPException(status_code=404, detail="Feed not found")
        return {"status": "deleted"}

    @app.post("/api/feeds/{feed_id}/fetch")
    def fetch_single_feed(feed_id: str):
        feed = storage.get_feed(feed_id)
        if not feed:
            raise HTTPException(status_code=404, detail="Feed not found")
        result = engine.run_sync(feed_id=feed_id)
        return result

    @app.post("/api/feeds/preview")
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
    @app.get("/api/routes")
    def list_routes():
        return [r.to_dict() for r in storage.list_routes()]

    @app.post("/api/routes")
    def save_route(data: Dict[str, Any]):
        route = RouteConfig.from_dict(data)
        saved = storage.save_route(route)
        return saved.to_dict()

    @app.delete("/api/routes/{route_id}")
    def delete_route(route_id: str):
        success = storage.delete_route(route_id)
        if not success:
            raise HTTPException(status_code=404, detail="Route not found")
        return {"status": "deleted"}

    # Logs
    @app.get("/api/logs")
    def list_logs(limit: int = 50):
        return [l.to_dict() for l in storage.list_logs(limit)]

    # Manual Sync Trigger
    @app.post("/api/sync")
    def trigger_sync():
        result = engine.run_sync()
        return result

    # Config Export / Import
    @app.get("/api/config/export")
    def export_config():
        yaml_str = storage.export_yaml()
        return Response(content=yaml_str, media_type="application/x-yaml", headers={"Content-Disposition": "attachment; filename=rss2discord.yaml"})

    @app.post("/api/config/import")
    async def import_config(file: UploadFile = File(...)):
        content = await file.read()
        storage.import_yaml(content.decode("utf-8"))
        return {"status": "imported"}

    # Serve static assets
    @app.get("/")
    def read_index():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return HTMLResponse("<h2>RSS to Discord Router API</h2>")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
