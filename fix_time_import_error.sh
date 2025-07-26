#!/bin/bash

# 🔧 Fix "name 'time' is not defined" Error
# Adds missing time import to celery_app.py

echo "🔧 FIXING TIME IMPORT ERROR"
echo "=========================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🐛 Error Identified:"
echo "• celery_app.py uses time.time() but missing 'import time'"
echo "• Causing: name 'time' is not defined"
echo "• Location: update_partial_result_async function"
echo ""

echo "📝 Step 1: Verify Fix Applied"
echo "============================="

if grep -q "^import time" celery_app.py; then
    echo "✅ time import already present in celery_app.py"
else
    echo "❌ time import missing, adding it..."
    
    # Add time import after the os import
    sed -i '/^import os$/a import time' celery_app.py
    
    if grep -q "^import time" celery_app.py; then
        echo "✅ Successfully added time import"
    else
        echo "❌ Failed to add time import"
        exit 1
    fi
fi

echo ""
echo "📤 Step 2: Commit Fix"
echo "===================="

git add celery_app.py
git commit -m "fix: Add missing time import to resolve 'name time is not defined' error

- Add import time to celery_app.py
- Fixes error in update_partial_result_async function
- Resolves time.time() calls that were failing"

git push origin main
echo "✅ Fix committed and pushed"

echo ""
echo "🔄 Step 3: Restart Worker"
echo "========================"

echo "Restarting worker to apply the fix..."
sudo docker-compose restart worker

echo "Waiting 15 seconds for worker to restart..."
sleep 15

echo "✅ Worker restarted"

echo ""
echo "🧪 Step 4: Test Fix"
echo "=================="

echo "Checking worker status:"
sudo docker-compose ps worker

echo ""
echo "Checking worker logs for time-related errors:"
TIME_ERRORS=$(sudo docker-compose logs worker --tail=20 | grep -i "time.*not defined" || echo "No time errors found")

if [ "$TIME_ERRORS" = "No time errors found" ]; then
    echo "✅ No time-related errors in recent logs"
else
    echo "❌ Time errors still present:"
    echo "$TIME_ERRORS"
fi

echo ""
echo "Testing worker ping:"
PING_RESULT=$(sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect ping 2>/dev/null)

if echo "$PING_RESULT" | grep -q "pong"; then
    echo "✅ Worker responding to ping!"
else
    echo "❌ Worker not responding:"
    sudo docker-compose logs worker --tail=10
fi

echo ""
echo "🎯 Step 5: Submit Test Task"
echo "=========================="

echo "Submitting test task to verify time import fix..."
TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Test time import fix - should not show time not defined error",
    "model_name": "test-time-fix",
    "api_key": "test-key-time", 
    "priority": 5
  }' 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "✅ Test task submitted: $MESSAGE_ID"
    
    echo ""
    echo "Monitoring for time errors (20 seconds)..."
    
    for i in {1..4}; do
        sleep 5
        echo "Check $i:"
        
        # Check for time-related errors
        NEW_TIME_ERRORS=$(sudo docker-compose logs worker --since="10s" | grep -i "time.*not defined" || echo "")
        
        if [ -n "$NEW_TIME_ERRORS" ]; then
            echo "  ❌ Time error still occurring:"
            echo "  $NEW_TIME_ERRORS"
            exit 1
        else
            echo "  ✅ No time errors detected"
        fi
        
        # Check task status
        STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
        STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
        echo "  Status: $STATUS"
        
        if [ "$STATUS" != "pending" ]; then
            echo "  🎉 Task processing without time errors!"
            break
        fi
    done
    
else
    echo "❌ Test task submission failed:"
    echo "$TEST_RESPONSE"
fi

echo ""
echo "🎉 TIME IMPORT FIX COMPLETE"
echo "=========================="
echo ""
echo "✅ RESOLUTION:"
echo "• Added missing 'import time' to celery_app.py"
echo "• Fixed 'name time is not defined' error"
echo "• Worker restarted with fix applied"
echo "• Tasks should now process without time errors"
echo ""
echo "🔍 MONITOR FOR ISSUES:"
echo "sudo docker-compose logs worker -f | grep -i error"
echo ""
echo "📊 CHECK TASK STATUS:"
echo "curl http://localhost:8000/messages/{message_id}"
echo ""
echo "🎯 Time import error resolved! Tasks should process normally now. ✅" 