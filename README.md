# 📡 RSS-to-Discord Router

An RSS/Atom feed reader and dispatcher that routes updates from **multiple RSS feeds** to **multiple Discord webhooks** with rich embeds, keyword filtering, duplicate prevention, and an interactive Web UI dashboard.

![Dashboard Preview](dashboard_preview.jpg)

---

## ✨ Features

- **Multi-Feed to Multi-Webhook (M:N Routing)**: Map any number of RSS/Atom/JSON feeds to any number of Discord channels/webhooks with custom message prefixes (e.g., `@everyone` or `<@&role_id>`).
- **All-in-One Web UI & Polling Worker**: A single command (`rss2discord serve`) hosts the dashboard and automatically polls feeds in the background.
- **Virtual Env & `.env` Support**: Runs cleanly inside Python virtual environments (`.venv`) or systemd services with `.env` configuration file loading.
- **Web UI Dashboard with Basic Auth**: Protect public access to your web dashboard with HTTP Basic Authentication (`--auth user:pass` or `ADMIN_USER`/`ADMIN_PASS` env vars).
- **Customizable Port & Host**: Easily change the server port (`--port` or `PORT=8080` env var).
- **Duplicate Prevention**: SQLite persistent storage ensures feed stories are dispatched exactly once, even across system restarts.
- **Rich Discord Embed Formatting**: Converts HTML descriptions to clean Markdown, extracts lead images/thumbnails (`<media:content>`, `<enclosure>`, `og:image`, `<img>`), formats publish dates, and sets custom embed accent colors per feed or webhook.
- **Keyword Filtering**: Filter stories using `include_keywords` (must contain) and `exclude_keywords` (must not contain).

---

## 🚀 Quick Start (Python Virtual Environment)

1. **Create and activate a virtual environment:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Configure your `.env` file:**

   Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

   Edit `.env`:

   ```env
   PORT=8000
   HOST=0.0.0.0
   ADMIN_USER=admin
   ADMIN_PASS=MySecretPassword123!
   ```

4. **Launch the Dashboard:**

   ```bash
   rss2discord serve
   ```

   Open `http://localhost:8000` (or `http://YOUR_SERVER_IP:8000`) in your web browser!

---

## 🛠️ CLI Usage & Commands

```bash
# Import feeds & webhooks from YAML config:
rss2discord import-config config.example.yaml

# List current setup:
rss2discord list

# Test a webhook:
rss2discord test-webhook "https://discord.com/api/webhooks/YOUR_URL"

# Run a single sync cycle:
rss2discord sync
```

---

## 📜 Systemd Service Setup

To run the application automatically on Linux boot:

Create `/etc/systemd/system/rss2discord.service`:

```ini
[Unit]
Description=RSS to Discord Router Web & Polling Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/rss2discord
ExecStart=/home/ubuntu/rss2discord/.venv/bin/rss2discord serve
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rss2discord
```

---

## 🧪 Running Tests

Run the unit test suite inside your virtual environment:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

---

## 📄 License

MIT License.
