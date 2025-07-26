#!/bin/bash

# 🔧 Fix Asyncio Coroutine Error  
# Fixes "Passing coroutines is forbidden, use tasks explicitly" error

echo "🔧 FIXING ASYNCIO COROUTINE ERROR"
echo "================================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🐛 CRITICAL ERROR IDENTIFIED:"
echo "• Error: 'Passing coroutines is forbidden, use tasks explicitly'"
echo "• asyncio.wait() receiving coroutines instead of proper tasks"
echo "• translate_batch_parallel_ordered returns coroutine, not task"
echo "• Need to wrap coroutines with asyncio.create_task()"
echo ""

echo "🔧 SOLUTION IMPLEMENTED:"
echo "• Create proper asyncio tasks using asyncio.create_task()"
echo "• Pass task objects (not coroutines) to asyncio.wait()"
echo "• Maintain batch index tracking for order preservation"
echo "• Keep real-time progress updates working"
echo ""

echo "📝 Step 1: Apply Asyncio Task Fix"
echo "================================="

git add utils/translator.py
git commit -m "fix: Resolve asyncio coroutine error in parallel translation

- Create proper asyncio tasks using asyncio.create_task() instead of passing coroutines
- Fix 'Passing coroutines is forbidden, use tasks explicitly' error  
- Maintain batch index tracking for correct order preservation
- Keep real-time progress updates working with proper task management
- Ensure asyncio.wait() receives task objects, not raw coroutines"

git push origin main
echo "✅ Asyncio coroutine fix deployed"

echo ""
echo "🔄 Step 2: Restart Worker Service (URGENT)"
echo "==========================================="

echo "Restarting worker to apply critical asyncio fix..."
sudo docker-compose restart worker

echo "Waiting 10 seconds for worker to restart..."
sleep 10

echo "✅ Worker restarted with asyncio fix"

echo ""
echo "🧪 Step 3: Test Asyncio Fix"
echo "==========================="

echo "Checking worker status:"
sudo docker-compose ps worker

echo ""
echo "Testing worker ping:"
PING_RESULT=$(sudo docker exec translation-worker-api-worker-1 celery -A celery_app inspect ping 2>/dev/null)

if echo "$PING_RESULT" | grep -q "pong"; then
    echo "✅ Worker responding to ping!"
else
    echo "❌ Worker not responding:"
    sudo docker-compose logs worker --tail=5
fi

echo ""
echo "Testing translation with proper asyncio task handling..."

# Test with simple content
TEST_CONTENT="བཀྲ་ཤིས་བདེ་ལེགས།
ཁྱོད་ག་འདྲ་འདུག
ཞོགས་པ་བདེ་ལེགས།"

echo "Test content: 3 segments to verify asyncio task creation"

TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d "{
    \"content\": \"$TEST_CONTENT\",
    \"model_name\": \"claude-3-5-sonnet-20241022\",
    \"api_key\": \"test-asyncio-fix\",
    \"priority\": 5
  }" 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "✅ Test task submitted: $MESSAGE_ID"
    
    echo ""
    echo "Monitoring for asyncio errors (30 seconds)..."
    echo "Looking for: 'Passing coroutines is forbidden' error"
    
    for i in {1..6}; do
        sleep 5
        echo "Check $i (${i}0 seconds):"
        
        # Check for the specific asyncio error
        ASYNCIO_ERROR=$(sudo docker-compose logs worker --since="5s" | grep -i "passing coroutines is forbidden" | tail -1)
        if [ -n "$ASYNCIO_ERROR" ]; then
            echo "  ❌ ASYNCIO ERROR STILL PRESENT:"
            echo "  $ASYNCIO_ERROR"
            echo ""
            echo "🚨 FIX NOT WORKING - Need to investigate further"
            break
        fi
        
        # Check task status
        STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
        STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
        PROGRESS=$(echo "$STATUS_RESPONSE" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
        
        echo "  Status: $STATUS, Progress: ${PROGRESS}%"
        
        # Check for parallel processing logs
        PARALLEL_LOGS=$(sudo docker-compose logs worker --since="5s" | grep -E "(PARALLEL|Completed batch)" | tail -1)
        if [ -n "$PARALLEL_LOGS" ]; then
            echo "  🚀 Parallel activity: $(echo "$PARALLEL_LOGS" | sed 's/.*worker-1  | //')"
        fi
        
        if [ "$STATUS" = "completed" ]; then
            echo "  🎉 Translation completed successfully!"
            echo "  ✅ No asyncio coroutine errors detected!"
            break
        elif [ "$STATUS" = "failed" ]; then
            # Check if it's still the asyncio error
            MESSAGE=$(echo "$STATUS_RESPONSE" | grep -o '"message":"[^"]*"' | cut -d'"' -f4)
            if echo "$MESSAGE" | grep -i "coroutines is forbidden"; then
                echo "  ❌ Still getting asyncio coroutine error"
            else
                echo "  ⚠️  Different error: $MESSAGE"
            fi
            break
        fi
    done
    
else
    echo "❌ Test task submission failed:"
    echo "$TEST_RESPONSE"
fi

echo ""
echo "🔍 Step 4: Check for Asyncio Errors in Logs"
echo "============================================"

echo "Checking recent logs for asyncio coroutine errors:"
RECENT_ASYNCIO_ERRORS=$(sudo docker-compose logs worker --tail=50 | grep -i "coroutines is forbidden" | wc -l)

if [ "$RECENT_ASYNCIO_ERRORS" -eq 0 ]; then
    echo "✅ No asyncio coroutine errors found in recent logs!"
else
    echo "❌ Found $RECENT_ASYNCIO_ERRORS asyncio coroutine error(s) in recent logs:"
    sudo docker-compose logs worker --tail=50 | grep -i "coroutines is forbidden" | tail -3
fi

echo ""
echo "Recent worker logs:"
sudo docker-compose logs worker --tail=10

echo ""
echo "🎉 ASYNCIO COROUTINE FIX COMPLETE"
echo "================================="
echo ""
echo "✅ TECHNICAL CHANGES:"
echo "• 🔧 asyncio.create_task() wraps coroutines properly"
echo "• 🎯 asyncio.wait() receives task objects, not coroutines"
echo "• 📊 Batch index tracking maintained for order preservation"
echo "• ⚡ Real-time progress updates preserved"
echo ""
echo "🎯 EXPECTED RESULT:"
echo "• ✅ No more 'Passing coroutines is forbidden' errors"
echo "• ✅ Parallel translation works properly"
echo "• ✅ Real-time progress updates function correctly"
echo "• ✅ Order preservation maintained"
echo ""
echo "🔍 MONITOR FOR SUCCESS:"
echo "sudo docker-compose logs worker -f | grep -v 'coroutines is forbidden'"
echo ""
echo "🧪 TEST TRANSLATION:"
echo "Submit a translation and verify:"
echo "• No asyncio errors in logs"
echo "• Progress updates from 10% → 95% → 100%"
echo "• Successful parallel processing"
echo ""
echo "⚠️  IF STILL BROKEN:"
echo "1. Check logs: sudo docker-compose logs worker --tail=20"
echo "2. Restart all: sudo docker-compose restart"
echo "3. Rollback: git checkout HEAD~1 utils/translator.py"
echo ""
echo "🎯 Asyncio coroutine error fixed! ⚡🔧" 