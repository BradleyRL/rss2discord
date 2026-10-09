# 📡 RSS-to-Discord Router

An RSS/Atom feed reader and dispatcher that routes updates from **multiple RSS feeds** to **multiple Discord webhooks** with rich embeds, keyword filtering, duplicate prevention, and an interactive Web UI dashboard.

![Dashboard Preview](dashboard_preview.jpg)

---

## ✨ Features

- **Multi-Feed to Multi-Webhook (M:N Routing)**: Map any number of RSS/Atom/JSON feeds to any number of Discord channels/webhooks with custom message prefixes (e.g., `@everyone` or `<@&role_id>`).
- **Web UI Dashboard with Basic Auth**: Protect public access to your web dashboard with HTTP Basic Authentication (`--auth user:pass` or `ADMIN_USER`/`ADMIN_PASS` env vars).
- **Customizable Port & Host**: Easily change the server port (`--port` or `PORT=8080` env var).
- **Duplicate Prevention**: SQLite persistent storage ensures feed stories are dispatched exactly once, even across system restarts.
- **Rich Discord Embed Formatting**: Converts HTML descriptions to clean Markdown, extracts lead images/thumbnails (`<media:content>`, `<enclosure>`, `og:image`, `<img>`), formats publish dates, and sets custom embed accent colors per feed or webhook.
- **Keyword Filtering**: Filter stories using `include_keywords` (must contain) and `exclude_keywords` (must not contain).
- **Dual Operating Modes**:
  - **CLI / Daemon**: Run as a daemon (`daemon`), one-shot sync for cron (`sync`), or test webhooks (`test-webhook`).
  - **Web Dashboard**: Modern glassmorphism single-page app (`serve`) for visual management, live feed previews, and real-time delivery logs.
- **YAML Config Import/Export**: Manage state in SQLite or export/import seamlessly to `config.yaml`.
- **Rate Limit Safe**: Automatically handles Discord HTTP 429 rate limit backoff.

---

## 🚀 Quick Start

### 1. Installation

Ensure Python 3.9+ is installed. Clone the repository and install required packages:

```bash
git clone https://github.com/BradleyRL/rss2discord.git
cd rss2discord

pip install feedparser httpx fastapi uvicorn PyYAML python-multipart
```

### 2. Launch the Web UI Dashboard

Run the server command to open the visual dashboard (default port `8000`):

```bash
python3 -m rss2discord serve --port 8000
```

#### 🔒 Basic Auth & Internet Deployment

To secure the dashboard when accessing it from the internet:

```bash
# Option A: Command line flags
python3 -m rss2discord serve --port 8080 --auth admin:MySecretPassword123

# Option B: Environment variables (great for Docker / systemd)
export PORT=8080
export ADMIN_USER=admin
export ADMIN_PASS=MySecretPassword123
python3 -m rss2discord serve
```

Open `http://localhost:8080` in your browser. You will be prompted to enter your Basic Auth credentials!

---

## 🛠️ CLI Usage & Commands

### 📥 Import / Export Configuration

```bash
# Import feeds, webhooks, and routes from a YAML file:
python3 -m rss2discord import-config config.example.yaml

# Export current database setup to YAML:
python3 -m rss2discord export-config -o my_config.yaml
```

### 📋 List Setup

```bash
python3 -m rss2discord list
```

### 🧪 Test Webhook Connection

```bash
python3 -m rss2discord test-webhook "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL" --name "Tech Channel"
```

### 🔄 Run One-Shot Sync (Ideal for Cron)

```bash
python3 -m rss2discord sync
```

### 🤖 Run Continuous Background Daemon

```bash
python3 -m rss2discord daemon --interval 300
```

---

## ⚙️ Configuration File (`config.yaml`)

```yaml
webhooks:
  - id: wh-tech
    name: "Tech News Channel"
    url: "https://discord.com/api/webhooks/1234567890/EXAMPLE_WEBHOOK_TOKEN"
    color: "#5865F2"
    username: "Tech Feed Bot"
    enabled: true

feeds:
  - id: feed-hn
    name: "Hacker News Top Stories"
    url: "https://news.ycombinator.com/rss"
    fetch_interval_minutes: 15
    enabled: true
    include_keywords: ["python", "ai"]
    exclude_keywords: ["crypto"]
    custom_color: "#FF6600"

routes:
  - id: r-hn-tech
    name: "HN -> #tech-news"
    feed_id: "feed-hn"
    webhook_id: "wh-tech"
    message_prefix: ""
    enabled: true
```

---

## 📜 Systemd Daemon Service Example with Basic Auth

Create `/etc/systemd/system/rss2discord.service`:

```ini
[Unit]
Description=RSS to Discord Router Web & Daemon Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/rss2discord
Environment=PORT=8080
Environment=ADMIN_USER=admin
Environment=ADMIN_PASS=ChangeMeSecretPassword
ExecStart=/usr/bin/python3 -m rss2discord serve
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 🧪 Running Tests

Run the included unit test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

---

## 📄 License

MIT License.
