#!/bin/bash

# 🚀 Force High Priority Queue Fix
# Sets all tasks to high priority and restarts system for immediate processing

echo "🚀 FORCING ALL TASKS TO HIGH PRIORITY"
echo "====================================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "📝 Configuration Update:"
echo "• All tasks now use high_priority queue"
echo "• Default queue changed to high_priority"
echo "• Task routing updated to high_priority"
echo ""

echo "🛑 Step 1: Complete System Restart"
echo "=================================="

echo "Stopping all services..."
sudo docker-compose down --remove-orphans

echo "Waiting 10 seconds for complete shutdown..."
sleep 10

echo "Cleaning up any remaining processes..."
sudo fuser -k 8000/tcp || echo "No process on port 8000"

echo "Starting all services with updated configuration..."
sudo docker-compose up -d --build

echo "Waiting 30 seconds for all services to fully start..."
sleep 30

echo "✅ System restart completed"

echo ""
echo "📋 Step 2: Verify High Priority Configuration"
echo "============================================="

echo "Checking worker is consuming high_priority queue:"
ACTIVE_QUEUES=$(sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect active_queues 2>/dev/null)
echo "$ACTIVE_QUEUES"

if echo "$ACTIVE_QUEUES" | grep -q "high_priority"; then
    echo "✅ Worker is consuming high_priority queue"
else
    echo "⚠️  Worker might not be consuming high_priority queue properly"
fi

echo ""
echo "Worker registration check:"
sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect registered 2>/dev/null || echo "❌ Cannot get registered tasks"

echo ""
echo "🧪 Step 3: Test High Priority Task Submission"
echo "=============================================="

echo "Submitting test task (should go to high_priority queue)..."

TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "content": "High priority test task - should process immediately",
    "model_name": "test-model",
    "api_key": "test-key-high-priority",
    "priority": 0
  }' 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    echo "✅ High priority test task submitted!"
    
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "Test message ID: $MESSAGE_ID"
    
    echo ""
    echo "Monitoring task status for 15 seconds..."
    
    for i in {1..3}; do
        echo "Check $i (after ${i}0 seconds):"
        sleep 5
        
        STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
        STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
        PROGRESS=$(echo "$STATUS_RESPONSE" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
        
        echo "  Status: $STATUS, Progress: ${PROGRESS}%"
        
        if [ "$STATUS" != "pending" ]; then
            echo "✅ Task moved from pending status - high priority queue is working!"
            break
        fi
        
        if [ "$i" -eq 3 ]; then
            echo "❌ Task still pending after 15 seconds - investigating..."
        fi
    done
    
else
    echo "❌ Test task submission failed:"
    echo "$TEST_RESPONSE"
fi

echo ""
echo "🔍 Step 4: Detailed Queue Analysis"
echo "=================================="

echo "Redis queue lengths:"
HIGH_PRIORITY_LEN=$(sudo docker exec translation-worker-api-redis-1 redis-cli llen high_priority 2>/dev/null || echo "0")
DEFAULT_LEN=$(sudo docker exec translation-worker-api-redis-1 redis-cli llen default 2>/dev/null || echo "0")

echo "High priority queue: $HIGH_PRIORITY_LEN tasks"
echo "Default queue: $DEFAULT_LEN tasks"

if [ "$HIGH_PRIORITY_LEN" -gt 0 ]; then
    echo "⚠️  Tasks are queued but not being processed - worker issue!"
    echo ""
    echo "Worker diagnostics:"
    echo "Worker container status:"
    sudo docker-compose ps worker
    
    echo ""
    echo "Worker logs (last 15 lines):"
    sudo docker-compose logs worker --tail=15
    
    echo ""
    echo "Worker process check:"
    sudo docker exec translation-worker-api-worker-1 ps aux | grep -E "(celery|python)"
    
elif [ "$HIGH_PRIORITY_LEN" -eq 0 ] && [ "$STATUS" != "pending" ]; then
    echo "✅ Queue is empty and tasks are processing - system working correctly!"
    
else
    echo "🔍 Tasks might not be reaching the queue. Checking API..."
    echo "API logs (last 10 lines):"
    sudo docker-compose logs api --tail=10
fi

echo ""
echo "📊 Step 5: System Health Summary"
echo "================================"

# Check all services
REDIS_STATUS=$(sudo docker exec translation-worker-api-redis-1 redis-cli ping 2>/dev/null || echo "ERROR")
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "ERROR")
WORKER_CONTAINER=$(sudo docker-compose ps worker | grep -c "Up")

echo "Redis: $([ "$REDIS_STATUS" = "PONG" ] && echo '✅ Connected' || echo '❌ Error')"
echo "API: $([ "$API_STATUS" = "200" ] && echo '✅ Running' || echo "❌ Error (HTTP $API_STATUS)")"
echo "Worker: $([ "$WORKER_CONTAINER" -gt 0 ] && echo '✅ Running' || echo '❌ Not running')"

# Worker ping test
WORKER_PING=$(sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect ping 2>/dev/null)
if echo "$WORKER_PING" | grep -q "pong"; then
    echo "Worker connectivity: ✅ Responding"
else
    echo "Worker connectivity: ❌ Not responding"
fi

echo ""
echo "🎯 FINAL RECOMMENDATIONS"
echo "========================"

if [ "$REDIS_STATUS" = "PONG" ] && [ "$API_STATUS" = "200" ] && [ "$WORKER_CONTAINER" -gt 0 ] && echo "$WORKER_PING" | grep -q "pong"; then
    echo "🎉 All systems operational with high priority configuration!"
    echo ""
    echo "✅ Benefits of high priority setup:"
    echo "  • All tasks go to high_priority queue"
    echo "  • Worker prioritizes these tasks"
    echo "  • Faster task pickup and processing"
    echo ""
    echo "🔍 Monitor tasks with:"
    echo "  sudo docker-compose logs worker -f"
    echo "  curl http://localhost:8000/messages/{message-id}"
    
else
    echo "❌ System issues detected. Try these fixes:"
    echo ""
    echo "1. Full system restart:"
    echo "   sudo docker-compose down"
    echo "   sudo docker system prune -f"
    echo "   sudo docker-compose up -d --build"
    echo ""
    echo "2. Check detailed diagnostics:"
    echo "   ./debug_celery_queue.sh"
    echo ""
    echo "3. Manual worker restart:"
    echo "   sudo docker-compose restart worker"
    echo "   sudo docker-compose logs worker -f"
fi

echo ""
echo "📈 Current Configuration:"
echo "• Default queue: high_priority"
echo "• All tasks route to: high_priority"
echo "• Worker consumes: high_priority,default"
echo "• Priority function: Always returns high_priority" 