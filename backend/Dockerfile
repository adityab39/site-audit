FROM python:3.12-slim

# ── Base system tools ──────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    ca-certificates \
    gnupg \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 (via NodeSource) ────────────────────────────────────────────────
# The Debian Bookworm default is Node.js 18; pull v20 from the official repo.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Lighthouse CLI ─────────────────────────────────────────────────────────────
RUN npm install -g lighthouse

# ── Python dependencies ────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright Chromium + all system browser dependencies ─────────────────────
# On Linux amd64 (EC2/Ubuntu), --with-deps works correctly and installs every
# system library that Playwright's Chromium needs via apt-get.
RUN playwright install chromium --with-deps

# ── System Chromium for Lighthouse ────────────────────────────────────────────
# Playwright installs its own Chromium under ~/.cache/ms-playwright/.
# Lighthouse needs a separate, stable binary at a fixed path.
# Installing the system `chromium` package is fast here because --with-deps
# already pulled in virtually every shared library it depends on.
RUN apt-get update && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*

# ── Application source ─────────────────────────────────────────────────────────
COPY . .

# Tell Lighthouse which Chrome binary to use (overridable via .env)
ENV LIGHTHOUSE_CHROME_PATH=/usr/bin/chromium

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
