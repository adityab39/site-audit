FROM python:3.12-slim

# ── System dependencies ────────────────────────────────────────────────────────
# Two separate Chromium binaries are used in this image:
#   • System `chromium`   → consumed by Lighthouse CLI via --chrome-path
#   • Playwright Chromium → downloaded later; consumed by the crawler service
#
# python:3.12-slim is based on Debian Bookworm (12). Some package names changed
# in Bookworm (e.g. t64 suffix for time_t-updated libs), so we use the correct
# Bookworm names throughout. Works on both linux/amd64 and linux/arm64
# (Apple Silicon M-series).
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Runtime utilities
    curl \
    wget \
    ca-certificates \
    gnupg \
    xdg-utils \
    # Node / npm – required for the Lighthouse CLI
    nodejs \
    npm \
    # System Chromium for Lighthouse
    chromium \
    # Shared libs used by both Chromium instances
    fonts-liberation \
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

# ── Playwright Chromium browser dependencies (manual install) ─────────────────
# Install these *manually* then call `playwright install chromium` (no --with-deps).
#
# Why: `--with-deps` references packages that no longer exist in Debian Bookworm:
#   ttf-unifont           → renamed to fonts-unifont
#   ttf-ubuntu-font-family → removed entirely from Bookworm
#
# libasound2 note: Bookworm ships libasound2t64 as the primary package.
# We try it first and fall back to libasound2 so the build works on both
# Bookworm and any derivative that still uses the old name.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-unifont \
    libatspi2.0-0 \
    libcairo2 \
    libpango-1.0-0 \
    libwayland-client0 \
    libxkbcommon0 \
    && ( apt-get install -y --no-install-recommends libasound2t64 \
      || apt-get install -y --no-install-recommends libasound2 ) \
    && rm -rf /var/lib/apt/lists/*

# ── Lighthouse CLI ─────────────────────────────────────────────────────────────
RUN npm install -g lighthouse

# ── Python dependencies ────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright Chromium browser ────────────────────────────────────────────────
# All system deps installed above; omit --with-deps to avoid the broken
# ttf-* package references in Playwright's own dependency installer.
# Works on both linux/amd64 (Intel) and linux/arm64 (Apple Silicon).
RUN playwright install chromium

# ── Application source ─────────────────────────────────────────────────────────
COPY . .

# Tell Lighthouse where the system Chromium lives (overridable via env)
ENV LIGHTHOUSE_CHROME_PATH=/usr/bin/chromium

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
