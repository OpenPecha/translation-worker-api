"""FastAPI Translation Queue API with Celery Integration

This is the main application file that initializes the FastAPI app,
sets up Redis connection, and includes the route modules.

The application provides a RESTful API for managing translation tasks with
Celery-based task processing and Redis as the message broker.
"""

import os
import logging
import sys
import threading
import subprocess
import time
from fastapi import FastAPI
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("message-queue-api")

# Initialize FastAPI app
app = FastAPI(
    title="Translation Queue API",
    description="API for managing translation tasks with Celery and Redis",
    version="1.0.0"
)

# Configure Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Connect to Redis
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    # Test the connection
    redis_client.ping()
except redis.exceptions.ConnectionError as e:
    logger.error(f"Failed to connect to Redis: {str(e)}")
    raise

# Root endpoint for health check
@app.get("/", tags=["health"])
async def root():
    """Health check endpoint"""
    return {
        "status": "ok", 
        "message": "Translation Queue API is running",
        "version": "1.0.0"
    }

# Import and include routers
from routes.messages import router as messages_router
from routes.queue import router as queue_router
from routes.translation import router as translation_router

# Define constants
NOT_FOUND_RESPONSE = {404: {"description": "Not found"}}

# Include routers with explicit prefixes to ensure they show up in Swagger
app.include_router(
    messages_router,
    prefix="/messages",
    tags=["messages"],
    responses=NOT_FOUND_RESPONSE,
)

app.include_router(
    queue_router,
    prefix="/queue",
    tags=["queue"],
    responses=NOT_FOUND_RESPONSE,
)

app.include_router(
    translation_router,
    prefix="/translation",
    tags=["translation"],
    responses=NOT_FOUND_RESPONSE,
)

# Function to start Celery worker in a separate process
def start_celery_worker():
    """Start Celery worker in a separate process"""
    def run_worker():
        # Command to start Celery worker with multiple queues
        cmd = [
            sys.executable, "-m", "celery", 
            "-A", "celery_app", "worker", 
            "--loglevel=info",
            "--concurrency=1",  # Reduced concurrency to avoid Windows permission issues
            "--pool=solo",      # Use solo pool to avoid permission errors on Windows
            "-Q", "high_priority,default"  # Specify queues to consume from
        ]
        
        # Start the process with explicit UTF-8 encoding
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            encoding='utf-8',  # Explicitly use UTF-8 encoding
            errors='replace',   # Replace invalid characters instead of failing
            cwd=os.path.dirname(os.path.abspath(__file__))  # Set working directory to project root
        )
        
        # Print output from Celery worker
        for line in process.stdout:
            print(f"[Celery] {line}", end="")
            
        process.wait()
        if process.returncode != 0:
            logger.error(f"Celery worker exited with code {process.returncode}")
    
    # Start the worker in a separate thread
    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    logger.info("Celery worker thread started")
    return thread

# Function to start Flower dashboard in a separate process
def start_flower_dashboard():
    def run_flower():

        # Construct broker URL
        broker_url = f"redis://{f':{REDIS_PASSWORD}@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

        cmd = [
            sys.executable, "-m", "celery",
            "-A", "celery_app",
            f"--broker={broker_url}",
            "flower",
            "--port=5555",
            "--persistent=True",  # Enable persistence
            "--db=flower.db",      # Use a persistent database
            "--basic_auth=admin:admin"  # Add basic auth for security
        ]

        # Set environment variable to prevent auto-shutdown
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        while True:  # Add restart loop
            try:
                logger.info("Starting Flower process...")
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    encoding='utf-8',
                    errors='replace',
                    env=env
                )

                # Read output without blocking the main thread
                for line in iter(process.stdout.readline, ''):
                    if line:  # Only print non-empty lines
                        print(f"[Flower] {line}", end="")

                # Wait for process to complete
                exit_code = process.wait()
                time.sleep(5)  # Wait before restarting
            except Exception as e:
                logger.error(f"Failed to start/run Flower: {e}")
                time.sleep(5)  # Wait before retrying

    # Use a non-daemon thread so it won't be killed automatically
    thread = threading.Thread(target=run_flower, daemon=False)
    thread.start()
    return thread

# Start the FastAPI server with Celery worker and Flower dashboard
if __name__ == "__main__":
    import uvicorn
    
    # # Start Celery worker in a separate process
    # worker_thread = start_celery_worker()
    
    # # Start Flower dashboard in a separate process
    # flower_thread = start_flower_dashboard()
    
    
    # Run the FastAPI server
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
