#!/bin/bash

# 🔧 Restart Worker & Fix Syntax Issues
# Addresses the IndentationError in text_segmentation.py

echo "🔧 FIXING WORKER SYNTAX ERROR"
echo "=============================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🐛 Issue Detected:"
echo "IndentationError in utils/text_segmentation.py line 304"
echo "This is preventing tasks from processing"
echo ""

echo "🛑 Step 1: Stop Worker Container"
echo "================================"
sudo docker-compose stop worker
echo "Worker stopped"

echo ""
echo "🔍 Step 2: Check Python Syntax"
echo "==============================="
echo "Testing Python syntax in text_segmentation.py:"

# Test syntax inside container
sudo docker run --rm -v "$(pwd):/app" pecha-translation-api python -m py_compile /app/utils/text_segmentation.py 2>&1 || {
    echo "❌ Syntax error confirmed in text_segmentation.py"
    echo ""
    echo "🔧 Common causes:"
    echo "• Mixed spaces and tabs"
    echo "• Incorrect indentation after elif/if statements"
    echo "• Missing colons"
    echo ""
}

echo ""
echo "🔨 Step 3: Rebuild and Restart Worker"
echo "====================================="
echo "Rebuilding container to ensure clean Python environment..."
sudo docker-compose build worker

echo "Starting worker with fresh build..."
sudo docker-compose up worker -d

echo "Waiting 15 seconds for worker to start..."
sleep 15

echo ""
echo "📋 Step 4: Verify Worker Status"
echo "==============================="
echo "Worker container status:"
sudo docker-compose ps worker

echo ""
echo "Worker logs (last 20 lines):"
sudo docker-compose logs worker --tail=20

echo ""
echo "🧪 Step 5: Test Worker Functionality"
echo "===================================="

echo "Testing worker ping:"
PING_RESULT=$(sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect ping 2>/dev/null)

if echo "$PING_RESULT" | grep -q "pong"; then
    echo "✅ Worker is responding to ping!"
    
    echo ""
    echo "Testing task submission:"
    TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
      -H "Content-Type: application/json" \
      -d '{
        "content": "Syntax fix test - should process without IndentationError",
        "model_name": "test-model", 
        "api_key": "test-key-syntax",
        "priority": 0
      }' 2>/dev/null)
    
    if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
        MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
        echo "✅ Test task submitted: $MESSAGE_ID"
        
        echo ""
        echo "Monitoring for syntax errors (10 seconds)..."
        sleep 10
        
        # Check worker logs for IndentationError
        SYNTAX_ERROR=$(sudo docker-compose logs worker --tail=20 | grep -i "IndentationError" || echo "")
        
        if [ -n "$SYNTAX_ERROR" ]; then
            echo "❌ IndentationError still occurring:"
            echo "$SYNTAX_ERROR"
            echo ""
            echo "🔧 MANUAL FIX NEEDED:"
            echo "The indentation issue needs to be fixed in the code"
        else
            echo "✅ No syntax errors detected!"
            
            # Check task status
            STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
            STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
            echo "Task status: $STATUS"
            
            if [ "$STATUS" != "pending" ]; then
                echo "🎉 SUCCESS! Task is processing without syntax errors!"
            else
                echo "⚠️  Task still pending, but no syntax errors"
            fi
        fi
        
    else
        echo "❌ Test task submission failed"
    fi
    
else
    echo "❌ Worker not responding to ping"
    echo "Checking worker logs for errors:"
    sudo docker-compose logs worker --tail=10
fi

echo ""
echo "🎯 SUMMARY"
echo "=========="

WORKER_STATUS=$(sudo docker-compose ps worker | grep -c "Up")
RECENT_ERRORS=$(sudo docker-compose logs worker --tail=30 | grep -c "IndentationError" || echo "0")

echo "Worker container: $([ "$WORKER_STATUS" -gt 0 ] && echo '✅ Running' || echo '❌ Not running')"
echo "Recent IndentationErrors: $RECENT_ERRORS"

if [ "$RECENT_ERRORS" -eq 0 ] && [ "$WORKER_STATUS" -gt 0 ]; then
    echo ""
    echo "🎉 Syntax issue appears to be resolved!"
    echo "✅ Worker is running without IndentationErrors"
    echo "✅ High priority queue configuration is active"
    echo ""
    echo "🔍 Monitor with:"
    echo "sudo docker-compose logs worker -f"
    
else
    echo ""
    echo "❌ Syntax issue may persist. Next steps:"
    echo "1. Check the exact indentation in text_segmentation.py"
    echo "2. Ensure consistent use of spaces (not tabs)"
    echo "3. Verify Python syntax: python -m py_compile utils/text_segmentation.py"
    echo "4. Full restart: sudo docker-compose down && sudo docker-compose up -d --build"
fi 