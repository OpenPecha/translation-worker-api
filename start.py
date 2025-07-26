"""
Startup script for the translation queue system
This script starts both the FastAPI server and Celery worker
"""
import os
import sys
import subprocess
import threading
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("startup")

def start_celery_worker():
    """Start the Celery worker with beat scheduler in a separate process"""
    
    # Command to start Celery worker with beat scheduler
    cmd = [
        sys.executable, "-m", "celery", 
        "-A", "celery_worker", "worker", 
        "--beat", 
        "--loglevel=info",
        "--concurrency=1",
        "--pool=solo"  # Use solo pool to avoid permission errors on Windows
    ]
    
    # Start the process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
        # Log output from the FastAPI server
    def log_output():
        for line in process.stdout:
            logger.info(f"[FastAPI] {line.strip()}")
    # Start logging in a separate thread
    log_thread = threading.Thread(target=log_output, daemon=True)
    log_thread.start()
    
    return process

def start_fastapi_server():
    """Start the FastAPI server in a separate process"""
    
    # Command to start FastAPI server with increased request size limit
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "app:app", 
        "--host", "0.0.0.0", 
        "--port", "9000",
        "--limit-concurrency", "100",
        "--limit-max-requests", str(100 * 1024 * 1024)  # 100MB max request size
    ]
    
    # Start the process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # Log output from the FastAPI server
    def log_output():
        for line in process.stdout:
            logger.info(f"[FastAPI] {line.strip()}")
    
    # Start logging in a separate thread
    log_thread = threading.Thread(target=log_output, daemon=True)
    log_thread.start()
    
    return process

if __name__ == "__main__":
    try:
        # Start Celery worker
        celery_process = start_celery_worker()
        
        # Wait a moment for Celery to initialize
        time.sleep(2)
        
        # Start FastAPI server
        fastapi_process = start_fastapi_server()
        
        
        # Wait for processes to complete (they won't unless terminated)
        fastapi_process.wait()
        celery_process.wait()
        
    except KeyboardInterrupt:
        # Terminate processes
        if 'fastapi_process' in locals():
            fastapi_process.terminate()
        if 'celery_process' in locals():
            celery_process.terminate()
    
    except Exception as e:
        logger.error(f"Error starting translation queue system: {str(e)}")
        sys.exit(1)
