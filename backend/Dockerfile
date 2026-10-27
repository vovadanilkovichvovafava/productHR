FROM python:3.11-slim

# Universal Chat Analyzer Backend
WORKDIR /app

# Install system dependencies including Playwright browser deps
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libreoffice-common \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    unrar-free \
    libheif-dev \
    # libmagic — нужен python-magic (api/routes/parser.py делает import magic),
    # без него uvicorn падает с ImportError на старте.
    libmagic1 \
    # Tesseract — распознавание сканов резюме для сравнения дублей (без ИИ,
    # services/resume_text_extract.py). Только русский и английский.
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
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
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy all files first (ensures requirements.txt is included)
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set Playwright browser path to a known location
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

# Install Playwright browsers and dependencies
RUN mkdir -p $PLAYWRIGHT_BROWSERS_PATH && \
    playwright install --with-deps chromium

# Verify Playwright installation
RUN python -c "from playwright.sync_api import sync_playwright; print('Playwright installed successfully')"

# Expose port
EXPOSE 8000

# Make start script executable
RUN chmod +x start.sh

# Run the application with migrations
CMD ["./start.sh"]
