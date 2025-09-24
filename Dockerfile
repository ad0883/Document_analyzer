# 🐳 Document Analyzer - Production Dockerfile
FROM python:3.9-slim

# Set production environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV FLASK_ENV=production

# Install system dependencies
RUN apt-get update && apt-get install -y \
    default-jre-headless \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data during build
RUN python -c "import nltk; nltk.download('punkt', download_dir='/app/nltk_data'); nltk.download('words', download_dir='/app/nltk_data')"
ENV NLTK_DATA=/app/nltk_data

# Copy application code
COPY . .

# Create uploads directory and set permissions
RUN mkdir -p /app/uploads

# Make start script executable
RUN chmod +x start.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:$PORT/ || exit 1

# Expose port
EXPOSE $PORT

# Use start script for better reliability
CMD ["./start.sh"]
