# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy only package.json first (npm install will create fresh lock file for alpine)
# This avoids rollup native module mismatch issues between glibc and musl
COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build
# Telegram Mini App — отдельная сборка со своим конфигом и своим outDir.
# Намеренно отдельной командой: сборка веб-версии выше не меняется, и если
# мини-апп когда-то не соберётся, будет видно, что упало именно оно.
RUN npm run build:miniapp

# Stage 2: Final image
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies in stages to avoid memory/timeout issues
# Stage 1: Basic tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    unrar-free \
    libheif-dev \
    libmagic1 \
    wget \
    gnupg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: LibreOffice (for document parsing - docx, xlsx, pptx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer-nogui \
    libreoffice-calc-nogui \
    libreoffice-impress-nogui \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy backend files
COPY backend/ .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set Playwright browser path to a known location
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

# Install Playwright browsers (Chromium only for smaller image size)
# This also installs system dependencies needed for the browser
RUN mkdir -p $PLAYWRIGHT_BROWSERS_PATH && \
    playwright install chromium --with-deps

# Verify Playwright installation
RUN python -c "from playwright.sync_api import sync_playwright; print('Playwright installed successfully')"

# Copy built frontend from stage 1
COPY --from=frontend-builder /frontend/dist ./static
# Мини-апп рядом, отдельным каталогом — main.py монтирует его на /miniapp
COPY --from=frontend-builder /frontend/dist-miniapp ./static-miniapp

# chrome-extension перенесён в backend/chrome-extension и уже попадает в образ
# выше через `COPY backend/ .` — отдельный COPY больше не нужен (и сломал бы
# сборку, т.к. в корне репозитория этой папки уже нет).

# Create uploads directory
RUN mkdir -p /app/uploads/calls

# Make startup script executable
RUN chmod +x start.sh

# Railway injects PORT environment variable
ENV PORT=8000
EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start with migrations + server
CMD ["./start.sh"]
