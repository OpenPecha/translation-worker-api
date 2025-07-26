#!/bin/bash

# 🔧 Quick Fix for Pending Tasks
# Restarts Celery worker and verifies task processing

echo "🔧 FIXING PENDING TASKS ISSUE"
echo "=============================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🛑 Step 1: Restart Celery Worker"
echo "================================="

echo "Stopping worker..."
sudo docker-compose stop worker

echo "Waiting 5 seconds..."
sleep 5

echo "Starting worker..."
sudo docker-compose up worker -d

echo "Waiting 10 seconds for worker to fully start..."
sleep 10

echo "✅ Worker restarted"

echo ""
echo "📋 Step 2: Check Worker Status"
echo "==============================="

echo "Worker container status:"
sudo docker-compose ps worker

echo ""
echo "Worker logs (last 10 lines):"
sudo docker-compose logs worker --tail=10

echo ""
echo "🧪 Step 3: Test Worker Connectivity"
echo "==================================="

echo "Testing if worker responds to ping:"
PING_RESULT=$(sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect ping 2>/dev/null)

if echo "$PING_RESULT" | grep -q "pong"; then
    echo "✅ Worker is responding to ping!"
    echo "Worker ping response: $PING_RESULT"
else
    echo "❌ Worker not responding to ping"
    echo "Checking worker process..."
    sudo docker exec translation-worker-api-worker-1 ps aux | grep celery
fi

echo ""
echo "Active queues on worker:"
sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect active_queues 2>/dev/null || echo "❌ Cannot get active queues"

echo ""
echo "🚀 Step 4: Test Task Submission"
echo "==============================="

echo "Submitting a test translation task via API..."

# Create test request
TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Test translation task to verify worker is processing",
    "model_name": "test-model",
    "api_key": "test-key-123",
    "priority": 0
  }' 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    echo "✅ Test task submitted successfully!"
    
    # Extract message ID
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "Test message ID: $MESSAGE_ID"
    
    echo ""
    echo "Waiting 5 seconds to check if task starts processing..."
    sleep 5
    
    # Check task status
    STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
    echo "Task status after 5 seconds:"
    echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' || echo "Could not get status"
    
    # Check if task moved from pending
    if echo "$STATUS_RESPONSE" | grep -q '"status_type":"pending"'; then
        echo "⚠️  Task is still pending - worker might not be picking up tasks"
    else
        echo "✅ Task status changed - worker is processing tasks!"
    fi
    
else
    echo "❌ Test task submission failed:"
    echo "$TEST_RESPONSE"
fi

echo ""
echo "📊 Step 5: Final Diagnostics"
echo "============================"

echo "Redis connection test:"
sudo docker exec translation-worker-api-redis-1 redis-cli ping

echo ""
echo "Current queue lengths:"
echo "Default queue: $(sudo docker exec translation-worker-api-redis-1 redis-cli llen default 2>/dev/null || echo '0')"
echo "High priority queue: $(sudo docker exec translation-worker-api-redis-1 redis-cli llen high_priority 2>/dev/null || echo '0')"

echo ""
echo "Active tasks on worker:"
sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect active 2>/dev/null || echo "No active tasks"

echo ""
echo "🎯 SUMMARY"
echo "=========="

WORKER_RUNNING=$(sudo docker-compose ps worker | grep -c "Up")
REDIS_PING=$(sudo docker exec translation-worker-api-redis-1 redis-cli ping 2>/dev/null)

echo "Worker container: $([ "$WORKER_RUNNING" -gt 0 ] && echo '✅ Running' || echo '❌ Not running')"
echo "Redis: $([ "$REDIS_PING" = "PONG" ] && echo '✅ Connected' || echo '❌ Not responding')"

if [ "$WORKER_RUNNING" -gt 0 ] && [ "$REDIS_PING" = "PONG" ]; then
    echo ""
    echo "🎉 Basic setup looks good!"
    echo "If tasks are still pending, check:"
    echo "  1. Task submission logs: sudo docker-compose logs api"
    echo "  2. Worker processing logs: sudo docker-compose logs worker -f"
    echo "  3. Run full diagnostic: ./debug_celery_queue.sh"
else
    echo ""
    echo "❌ Issues detected. Try:"
    echo "  1. Full restart: sudo docker-compose down && sudo docker-compose up -d"
    echo "  2. Check logs: sudo docker-compose logs"
fi 