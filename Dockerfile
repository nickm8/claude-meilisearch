FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ .
COPY . .

# Create directories for data persistence
RUN mkdir -p raw_json

# Expose port
EXPOSE 8000

# Use environment variable to determine which script to run
CMD sh -c 'if [ "$SERVICE_TYPE" = "api" ]; then \
    uvicorn app:app --host 0.0.0.0 --port 8000; \
    else \
    python indexer.py; \
    fi'
