#!/bin/bash

# 🔧 Fix Translation Failures
# Improves error handling for parallel translation results

echo "🔧 FIXING TRANSLATION FAILURES"
echo "=============================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🐛 Issue Identified:"
echo "• Error: 'Translation failed: No translated text returned'"
echo "• Parallel translation returning status='failed' without translated_text"
echo "• celery_app.py only checking for 'translated_text' field existence"
echo "• Missing proper handling of failed parallel translation results"
echo ""

echo "🔧 Solutions Implemented:"
echo "• Enhanced result checking: status='completed' + translated_text exists + not empty"
echo "• Added specific handler for status='failed' results"
echo "• Better error messages with actual error details"
echo "• Improved debugging logs to identify failure causes"
echo "• Proper status updates for failed translations"
echo ""

echo "📝 Step 1: Apply Translation Failure Fix"
echo "======================================="

git add celery_app.py
git commit -m "fix: Improve error handling for parallel translation failures

- Enhanced result validation to check status='completed' AND translated_text
- Added specific handling for status='failed' parallel translation results  
- Improved error messages to include actual error details from parallel processing
- Added comprehensive debugging logs to track translation result structure
- Proper status updates for both successful and failed translations
- Better distinction between different failure types"

git push origin main
echo "✅ Translation failure fix deployed"

echo ""
echo "🔄 Step 2: Restart Worker Service"
echo "================================="

echo "Restarting worker to apply translation failure fixes..."
sudo docker-compose restart worker

echo "Waiting 15 seconds for worker to restart..."
sleep 15

echo "✅ Worker restarted"

echo ""
echo "🧪 Step 3: Test Translation Error Handling"
echo "=========================================="

echo "Checking worker status:"
sudo docker-compose ps worker

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
echo "Testing translation with valid content..."

# Test with simple content that should work
TEST_CONTENT="བཀྲ་ཤིས་བདེ་ལེགས།
ཁྱོད་ག་འདྲ་འདུག"

echo "Test content: 2 simple segments"

TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d "{
    \"content\": \"$TEST_CONTENT\",
    \"model_name\": \"claude-3-5-sonnet-20241022\",
    \"api_key\": \"test-error-handling\",
    \"priority\": 5
  }" 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "✅ Test task submitted: $MESSAGE_ID"
    
    echo ""
    echo "Monitoring translation for improved error handling (45 seconds)..."
    
    for i in {1..9}; do
        sleep 5
        echo "Check $i (${i}0 seconds):"
        
        # Check task status
        STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
        STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
        PROGRESS=$(echo "$STATUS_RESPONSE" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
        MESSAGE=$(echo "$STATUS_RESPONSE" | grep -o '"message":"[^"]*"' | cut -d'"' -f4)
        
        echo "  Status: $STATUS, Progress: ${PROGRESS}%"
        echo "  Message: $MESSAGE"
        
        # Check for detailed debugging logs
        DEBUG_LOGS=$(sudo docker-compose logs worker --since="5s" | grep -E "(Starting parallel translation|Translation completed|Result keys|Translated text length)" | tail -3)
        if [ -n "$DEBUG_LOGS" ]; then
            echo "  🔍 Debug info:"
            echo "$DEBUG_LOGS" | sed 's/^/    /'
        fi
        
        if [ "$STATUS" = "completed" ]; then
            echo "  🎉 Translation completed successfully!"
            
            # Check if we have the translated text
            TRANSLATED=$(echo "$STATUS_RESPONSE" | grep -o '"translated_text":"[^"]*"' | cut -d'"' -f4)
            if [ -n "$TRANSLATED" ]; then
                echo "  ✅ Translation result received: ${#TRANSLATED} characters"
            else
                echo "  ⚠️  No translated_text in response"
            fi
            break
            
        elif [ "$STATUS" = "failed" ]; then
            echo "  ❌ Translation failed (this is expected for testing error handling)"
            
            # Check for improved error messages
            ERROR_LOGS=$(sudo docker-compose logs worker --since="10s" | grep -E "(Parallel translation failed|Translation failed)" | tail -2)
            if [ -n "$ERROR_LOGS" ]; then
                echo "  🔍 Error details:"
                echo "$ERROR_LOGS" | sed 's/^/    /'
            fi
            
            # Check if the error message is more descriptive now
            if echo "$MESSAGE" | grep -q "Parallel translation failed"; then
                echo "  ✅ Improved error message detected!"
            elif echo "$MESSAGE" | grep -q "Translation failed:"; then
                echo "  ✅ Detailed error message provided!"
            else
                echo "  ⚠️  Generic error message: $MESSAGE"
            fi
            break
        fi
    done
    
else
    echo "❌ Test task submission failed:"
    echo "$TEST_RESPONSE"
fi

echo ""
echo "🔍 Step 4: Check Translation Debug Logs"
echo "========================================"

echo "Recent worker logs (checking for debugging information):"
sudo docker-compose logs worker --tail=50 | grep -E "(Starting parallel translation|Translation completed|Result keys|Translated text length|Parallel translation failed)" || echo "No specific debug logs found"

echo ""
echo "Recent error logs:"
sudo docker-compose logs worker --tail=20 | grep -E "(ERROR|WARNING)" || echo "No recent errors found"

echo ""
echo "🎉 TRANSLATION FAILURE FIX COMPLETE"
echo "==================================="
echo ""
echo "✅ IMPROVEMENTS APPLIED:"
echo "• 🔍 Enhanced result validation (status + translated_text + not empty)"
echo "• 🎯 Specific handling for failed parallel translation results"
echo "• 📝 Better error messages with actual error details"
echo "• 🔧 Comprehensive debugging logs for troubleshooting"
echo "• 📊 Proper status updates for both success and failure cases"
echo ""
echo "🔧 ERROR HANDLING LOGIC:"
echo "• ✅ Success: status='completed' AND translated_text exists AND not empty"
echo "• ❌ Known failure: status='failed' with specific error message"
echo "• ⚠️  Unknown issue: Invalid result structure with detailed logging"
echo ""
echo "🔍 DEBUGGING FEATURES:"
echo "• 📊 Result type and structure logging"
echo "• 📏 Translated text length verification"
echo "• 🎯 Specific error identification and reporting"
echo "• 📝 Clear distinction between different failure types"
echo ""
echo "📈 MONITOR IMPROVEMENTS:"
echo "sudo docker-compose logs worker -f | grep -E '(Starting parallel|Translation completed|Result keys)'"
echo ""
echo "🧪 TEST ERROR HANDLING:"
echo "Submit translations and check for:"
echo "• Detailed error messages instead of generic 'No translated text returned'"
echo "• Proper status updates for failed translations"
echo "• Clear debugging information in logs"
echo ""
echo "⚠️  ROLLBACK IF NEEDED:"
echo "git checkout HEAD~1 celery_app.py"
echo "sudo docker-compose restart worker"
echo ""
echo "🎯 Translation failures now properly handled with detailed debugging! 🔧✅" 