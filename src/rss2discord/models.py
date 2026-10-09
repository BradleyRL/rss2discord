from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import hashlib

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class WebhookConfig:
    id: str
    name: str
    url: str
    avatar_url: Optional[str] = None
    username: Optional[str] = None
    color: str = "#5865F2"  # Discord blurple hex
    enabled: bool = True
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebhookConfig":
        return cls(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            url=data.get("url", ""),
            avatar_url=data.get("avatar_url"),
            username=data.get("username"),
            color=data.get("color", "#5865F2"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at") or utc_now_iso()
        )


@dataclass
class FeedConfig:
    id: str
    name: str
    url: str
    fetch_interval_minutes: int = 15
    enabled: bool = True
    include_keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    custom_color: Optional[str] = None
    initial_fetch_mode: str = "latest_only"  # latest_only, mute_all, all
    last_fetched_at: Optional[str] = None
    last_status: str = "never_fetched"  # ok, error, never_fetched
    last_error: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedConfig":
        inc = data.get("include_keywords") or []
        exc = data.get("exclude_keywords") or []
        if isinstance(inc, str):
            inc = [k.strip() for k in inc.split(",") if k.strip()]
        if isinstance(exc, str):
            exc = [k.strip() for k in exc.split(",") if k.strip()]
        return cls(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            url=data.get("url", ""),
            fetch_interval_minutes=int(data.get("fetch_interval_minutes", 15)),
            enabled=data.get("enabled", True),
            include_keywords=inc,
            exclude_keywords=exc,
            custom_color=data.get("custom_color"),
            initial_fetch_mode=data.get("initial_fetch_mode", "latest_only"),
            last_fetched_at=data.get("last_fetched_at"),
            last_status=data.get("last_status", "never_fetched"),
            last_error=data.get("last_error"),
            created_at=data.get("created_at") or utc_now_iso()
        )


@dataclass
class RouteConfig:
    id: str
    name: str
    feed_id: str
    webhook_id: str
    enabled: bool = True
    message_prefix: Optional[str] = None  # e.g., @everyone or <@&role_id>
    override_color: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouteConfig":
        return cls(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            feed_id=str(data.get("feed_id", "")),
            webhook_id=str(data.get("webhook_id", "")),
            enabled=data.get("enabled", True),
            message_prefix=data.get("message_prefix"),
            override_color=data.get("override_color"),
            created_at=data.get("created_at") or utc_now_iso()
        )


@dataclass
class FeedItem:
    feed_id: str
    title: str
    link: str
    guid: str
    description: str
    published: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    categories: List[str] = field(default_factory=list)

    @property
    def item_hash(self) -> str:
        raw = f"{self.feed_id}:{self.guid or self.link or self.title}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class DeliveryLog:
    id: Optional[int] = None
    feed_id: str = ""
    feed_name: str = ""
    webhook_id: str = ""
    webhook_name: str = ""
    route_id: str = ""
    item_title: str = ""
    item_link: str = ""
    item_hash: str = ""
    status: str = "success"  # success, failed, skipped
    error_message: Optional[str] = None
    delivered_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
