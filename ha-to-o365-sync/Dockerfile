FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY sync.py .
COPY ha_client.py .
COPY o365_client.py .
COPY healthcheck.py .

# Create directory for tokens
RUN mkdir -p .tokens

# Run as non-root user for security
RUN useradd -m -u 1000 syncuser && \
    chown -R syncuser:syncuser /app
USER syncuser

# Default command
CMD ["python", "sync.py"]
