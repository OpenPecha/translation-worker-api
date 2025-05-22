# FastAPI + Celery Translation Queue Worker

This is a FastAPI application that implements a message queue system using Celery with Redis as the broker. It allows you to:

- Add translation tasks to Celery queues with priority support
- Check task status
- Process translation tasks with automatic retries
- Monitor tasks with Flower dashboard

## Features

- RESTful API with FastAPI
- Celery-based task processing with Redis broker
- Multiple priority queues (high_priority, default)
- Automatic task retries with exponential backoff
- Task monitoring with Flower dashboard
- Translation service integration

## Requirements

- Python 3.7+
- Redis server
- Celery
- Flower (for monitoring)

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Configure Redis connection in `.env` file:
   ```
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_DB=0
   REDIS_PASSWORD=
   ```

3. Start the application (includes FastAPI server, Celery worker, and Flower dashboard):
   ```
   python app.py
   ```

4. Alternatively, you can start components separately:
   
   Start FastAPI server:
   ```
   uvicorn app:app --reload
   ```
   
   Start Celery worker with multiple queues:
   ```
   celery -A celery_app worker --loglevel=info --pool=solo -Q high_priority,default
   ```
   
   Start Flower dashboard:
   ```
   celery -A celery_app flower --port=5555
   ```

## API Endpoints

- `GET /`: Health check
- `POST /messages`: Add a translation task to the queue
- `GET /messages/{message_id}`: Get task status
- `GET /messages/next`: Get the next pending task (for backward compatibility)
- `POST /messages/process`: Process a pending task manually (for backward compatibility)
- `POST /messages/{message_id}/status`: Update task status
- `GET /queue/stats`: Get queue statistics

## Example Usage

### Add a translation task

```bash
curl -X POST "http://localhost:8000/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hello world! This text needs to be translated.",
    "model_name": "gpt-4",
    "api_key": "your-api-key-here",
    "priority": 10,
    "metadata": {
      "source_language": "en",
      "target_language": "fr",
      "domain": "general"
    }
  }'
```

### Check task status

```bash
curl -X GET "http://localhost:8000/messages/{message_id}"
```

### Using Celery directly in Python

```python
from celery_app import process_message, get_queue_for_priority

# Create message data
message_data = {
    "id": "unique-id-here",
    "content": "Text to translate",
    "model_name": "gpt-4",
    "api_key": "your-api-key",
    "priority": 8  # High priority
}

# Determine queue based on priority
queue = get_queue_for_priority(message_data["priority"])

# Queue the task
task = process_message.apply_async(
    args=[message_data],
    queue=queue
)

print(f"Task ID: {task.id}")
```

## Documentation

Interactive API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Monitoring

Celery tasks can be monitored using the Flower dashboard:
- Flower UI: http://localhost:5555

## Architecture

The application uses the following components:

1. **FastAPI**: Provides the REST API endpoints for task management
2. **Celery**: Handles task queuing, processing, and automatic retries
3. **Redis**: Acts as the message broker and result backend for Celery
4. **Flower**: Provides a web-based monitoring dashboard for Celery tasks

### Queue Structure

The application uses two Celery queues for priority handling:

- `high_priority`: For tasks with priority >= 5
- `default`: For tasks with priority < 5

### Automatic Retries

Tasks are automatically retried on failure with exponential backoff:

- Maximum retries: 5
- Backoff factor: Exponential with jitter
- Maximum backoff: 10 minutes
