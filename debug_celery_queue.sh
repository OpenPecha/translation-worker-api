#!/bin/bash

# 🔍 Celery Queue & Worker Diagnostic Script
# Identifies why tasks stay in pending status instead of processing immediately

echo "🔍 CELERY QUEUE & WORKER DIAGNOSTIC"
echo "==================================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "📊 STEP 1: CHECK DOCKER SERVICES"
echo "================================"
echo "Docker container status:"
sudo docker-compose ps

echo ""
echo "Worker container logs (last 20 lines):"
sudo docker-compose logs worker --tail=20

echo ""
echo "📋 STEP 2: CHECK REDIS CONNECTION"
echo "================================="

echo "Testing Redis connection:"
sudo docker exec translation-worker-api-redis-1 redis-cli ping || echo "❌ Redis not responding"

echo ""
echo "Redis queue inspection:"
echo "Keys matching message patterns:"
sudo docker exec translation-worker-api-redis-1 redis-cli keys "*message*" | head -10

echo ""
echo "Active Celery queues in Redis:"
sudo docker exec translation-worker-api-redis-1 redis-cli keys "*celery*" | head -10

echo ""
echo "📋 STEP 3: CHECK CELERY WORKER STATUS"
echo "======================================"

echo "Celery worker inspection from inside worker container:"
sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect active 2>/dev/null || echo "❌ No active tasks"

echo ""
echo "Celery worker stats:"
sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect stats 2>/dev/null || echo "❌ Cannot get worker stats"

echo ""
echo "Registered tasks:"
sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect registered 2>/dev/null || echo "❌ Cannot get registered tasks"

echo ""
echo "Available workers:"
sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect active_queues 2>/dev/null || echo "❌ Cannot get active queues"

echo ""
echo "🔍 STEP 4: CHECK TASK ROUTING"
echo "============================="

echo "Checking queue lengths in Redis:"
echo "High priority queue length:"
sudo docker exec translation-worker-api-redis-1 redis-cli llen high_priority 2>/dev/null || echo "0 (or queue doesn't exist)"

echo "Default queue length:"
sudo docker exec translation-worker-api-redis-1 redis-cli llen default 2>/dev/null || echo "0 (or queue doesn't exist)"

echo ""
echo "Celery queue inspection:"
sudo docker exec translation-worker-api-redis-1 redis-cli keys "*queue*" 2>/dev/null || echo "No queue keys found"

echo ""
echo "🧪 STEP 5: TEST TASK SUBMISSION"
echo "==============================="

echo "Testing simple task submission:"
# Create a test task submission
cat > /tmp/test_task.py << 'EOF'
import sys
sys.path.append('/app')

from celery_app import celery_app, process_message
import json

# Test data
test_message = {
    "id": "test-123",
    "content": "Hello test",
    "model_name": "test-model",
    "api_key": "test-key",
    "priority": 0
}

print("Submitting test task...")
try:
    task = process_message.apply_async(args=[test_message], queue='default')
    print(f"✅ Task submitted successfully: {task.id}")
    print(f"Task state: {task.state}")
except Exception as e:
    print(f"❌ Task submission failed: {e}")
    import traceback
    traceback.print_exc()
EOF

sudo docker exec translation-worker-api-worker-1 python /tmp/test_task.py

echo ""
echo "🔍 STEP 6: CHECK WORKER PROCESS"
echo "==============================="

echo "Worker container processes:"
sudo docker exec translation-worker-api-worker-1 ps aux | grep -E "(celery|python)"

echo ""
echo "Worker container environment:"
sudo docker exec translation-worker-api-worker-1 env | grep -E "(CELERY|REDIS)" | sort

echo ""
echo "🆘 STEP 7: COMMON ISSUES & FIXES"
echo "================================="

echo "Checking for common issues..."

# Check if worker is actually running the right command
WORKER_CMD=$(sudo docker exec translation-worker-api-worker-1 ps aux | grep "celery.*worker" | grep -v grep)
if [ -z "$WORKER_CMD" ]; then
    echo "❌ ISSUE: No Celery worker process found!"
    echo "🔧 FIX: Worker container might not be running the celery command"
    echo "   Check docker-compose.yml command for worker service"
else
    echo "✅ Celery worker process found: $WORKER_CMD"
fi

# Check if queues are properly configured
DEFAULT_QUEUE_EXISTS=$(sudo docker exec translation-worker-api-redis-1 redis-cli exists default 2>/dev/null)
if [ "$DEFAULT_QUEUE_EXISTS" = "0" ]; then
    echo "⚠️  WARNING: Default queue doesn't exist in Redis yet"
    echo "   This is normal if no tasks have been submitted"
fi

# Check worker connectivity
WORKER_PING=$(sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect ping 2>/dev/null)
if echo "$WORKER_PING" | grep -q "pong"; then
    echo "✅ Worker is responding to ping"
else
    echo "❌ ISSUE: Worker not responding to ping!"
    echo "🔧 FIXES TO TRY:"
    echo "   1. Restart worker: sudo docker-compose restart worker"
    echo "   2. Check worker logs: sudo docker-compose logs worker"
    echo "   3. Check Redis connectivity from worker"
fi

echo ""
echo "📋 DIAGNOSTIC SUMMARY"
echo "===================="
echo "Docker services: $(sudo docker-compose ps --services --filter 'status=running' | wc -l) running"
echo "Redis status: $(sudo docker exec translation-worker-api-redis-1 redis-cli ping 2>/dev/null || echo 'ERROR')"

WORKER_STATUS="UNKNOWN"
if sudo docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "translation-worker-api-worker-1.*Up"; then
    if echo "$WORKER_CMD" | grep -q "celery.*worker"; then
        WORKER_STATUS="RUNNING"
    else
        WORKER_STATUS="CONTAINER_UP_BUT_NO_WORKER_PROCESS"
    fi
else
    WORKER_STATUS="CONTAINER_DOWN"
fi

echo "Worker status: $WORKER_STATUS"

case $WORKER_STATUS in
    "RUNNING")
        echo "✅ Worker appears to be running correctly"
        echo "❓ If tasks are still pending, check:"
        echo "   - API task submission (check API logs)"
        echo "   - Task routing configuration"
        echo "   - Worker queue consumption"
        ;;
    "CONTAINER_UP_BUT_NO_WORKER_PROCESS")
        echo "❌ Worker container is up but celery process is not running"
        echo "🔧 RESTART WORKER: sudo docker-compose restart worker"
        ;;
    "CONTAINER_DOWN")
        echo "❌ Worker container is not running"
        echo "🔧 START WORKER: sudo docker-compose up worker -d"
        ;;
esac

echo ""
echo "🎯 NEXT STEPS:"
echo "=============="
echo "1. If worker is not running: sudo docker-compose restart worker"
echo "2. If worker is running but not processing: Check task submission in API logs"
echo "3. Monitor with: sudo docker-compose logs worker -f"
echo "4. Test task submission via API: curl -X POST http://localhost:8000/messages ..." 