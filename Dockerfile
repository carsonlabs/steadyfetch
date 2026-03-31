FROM python:3.12-slim

# Install system deps for Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    fonts-liberation \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY pyproject.toml README.md ./
COPY steadyfetch/ steadyfetch/
RUN pip install --no-cache-dir .

# Install Playwright browsers
RUN playwright install chromium
RUN crawl4ai-setup || true

# Cache directory
RUN mkdir -p /tmp/steadyfetch_cache

EXPOSE 8200

ENV PORT=8200
ENV HOST=0.0.0.0
ENV STEADYFETCH_TRANSPORT=streamable-http

CMD ["python", "-m", "steadyfetch.server"]
