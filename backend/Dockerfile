FROM python:3.12-slim

# ── System dependencies ────────────────────────────────────────────────────────
# Two separate Chrome/Chromium binaries are used:
#   • System `chromium`  → consumed by Lighthouse CLI (pointed via --chrome-path)
#   • Playwright Chromium → downloaded below; consumed by the crawler service
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Runtime utilities
    curl \
    wget \
    ca-certificates \
    gnupg \
    xdg-utils \
    # Node / npm (required for Lighthouse)
    nodejs \
    npm \
    # System Chromium for Lighthouse
    chromium \
    # Shared libs needed by both Chromium instances
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# ── Lighthouse ─────────────────────────────────────────────────────────────────
RUN npm install -g lighthouse

# ── Python dependencies ────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright – Chromium browser for the crawler service ──────────────────────
RUN playwright install chromium --with-deps

# ── Application source ─────────────────────────────────────────────────────────
COPY . .

# Tell Lighthouse where the system Chromium lives (can be overridden via env)
ENV LIGHTHOUSE_CHROME_PATH=/usr/bin/chromium

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
