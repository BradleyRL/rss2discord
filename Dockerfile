FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .
RUN pip install --no-cache-dir -e .

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["python3", "-m", "rss2discord", "serve"]
