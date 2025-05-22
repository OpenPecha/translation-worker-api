FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies and pre-download Botok resources in a single layer
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import botok; tokenizer = botok.WordTokenizer(); print('Botok resources downloaded successfully')"

# Copy application code
COPY . .

# Make sure the application directory is in the Python path
ENV PYTHONPATH=/app

# Create any necessary directories
RUN mkdir -p /app/data /app/flower-db

# Expose ports
EXPOSE 8000
EXPOSE 5555

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Command to run the application
CMD ["python", "app.py"]
