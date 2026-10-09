# 📡 RSS-to-Discord Router

An RSS/Atom feed reader and dispatcher that routes updates from **multiple RSS feeds** to **multiple Discord webhooks** with rich embeds, keyword filtering, duplicate prevention, and an interactive Web UI dashboard.

![Dashboard Preview](dashboard_preview.jpg)

---

## ✨ Features

- **Multi-Feed to Multi-Webhook (M:N Routing)**: Map any number of RSS/Atom/JSON feeds to any number of Discord channels/webhooks with custom message prefixes (e.g., `@everyone` or `<@&role_id>`).
- **Virtual Env & `.env` Support**: Runs cleanly inside Python virtual environments (`.venv`), Docker containers, or systemd services with `.env` configuration file loading.
- **Web UI Dashboard with Basic Auth**: Protect public access to your web dashboard with HTTP Basic Authentication (`--auth user:pass` or `ADMIN_USER`/`ADMIN_PASS` env vars).
- **Customizable Port & Host**: Easily change the server port (`--port` or `PORT=8080` env var).
- **Duplicate Prevention**: SQLite persistent storage ensures feed stories are dispatched exactly once, even across system restarts.
- **Rich Discord Embed Formatting**: Converts HTML descriptions to clean Markdown, extracts lead images/thumbnails (`<media:content>`, `<enclosure>`, `og:image`, `<img>`), formats publish dates, and sets custom embed accent colors per feed or webhook.
- **Keyword Filtering**: Filter stories using `include_keywords` (must contain) and `exclude_keywords` (must not contain).

---

## 🚀 Running inside Environments

### 🐍 Option 1: Python Virtual Environment (`.venv`) & `.env` file

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

4. **Run the Dashboard or Daemon:**

   ```bash
   # Run Web Dashboard (automatically loads .env):
   rss2discord serve

   # Or run continuous background daemon:
   rss2discord daemon --interval 300
   ```

---

### 🐳 Option 2: Docker & Docker Compose Container Environment

Run the application inside an isolated Docker environment:

1. **Copy `.env.example` to `.env`:**

   ```bash
   cp .env.example .env
   ```

2. **Start with Docker Compose:**

   ```bash
   docker-compose up -d
   ```

   The app will run inside a container on port `8000` with volume persistence in `./data/`.

---

## 🛠️ CLI Usage & Commands

```bash
# Import feeds & webhooks from YAML config:
rss2discord import-config config.example.yaml

# List current setup:
rss2discord list

# Test a webhook:
rss2discord test-webhook "https://discord.com/api/webhooks/YOUR_URL"

# Single sync cycle (for cron):
rss2discord sync
```

---

## 🧪 Running Tests

Run the unit test suite inside your environment:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

---

## 📄 License

MIT License.
