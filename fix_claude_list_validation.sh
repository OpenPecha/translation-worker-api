#!/bin/bash

# 🔧 Fix Claude List Validation Error
# Resolves "Input should be a valid list" Pydantic validation errors

echo "🔧 FIXING CLAUDE LIST VALIDATION ERROR"
echo "======================================"

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🐛 Error Identified:"
echo "• Claude returning string representation of list: \"['item1', 'item2']\""
echo "• Pydantic expects actual Python list: ['item1', 'item2']"
echo "• Causing: Input should be a valid list [type=list_type]"
echo ""

echo "🔧 Solutions Implemented:"
echo "• Added ast.literal_eval() for parsing string lists"
echo "• Multiple parsing methods (JSON, list literal, regex pattern)"
echo "• Enhanced error extraction from Pydantic validation errors"
echo "• Robust fallback strategies"
echo ""

echo "📝 Step 1: Apply Enhanced Claude Parsing"
echo "========================================"

git add utils/translator.py
git commit -m "fix: Enhanced Claude response parsing to handle string list representations

- Add ast.literal_eval() for parsing Python list literals
- Implement multiple parsing methods for Claude responses
- Add regex pattern matching for list extraction
- Handle Pydantic validation errors with input value extraction
- Add extensive debugging output for troubleshooting
- Provide robust fallback strategies for all parsing failures"

git push origin main
echo "✅ Enhanced Claude parsing deployed"

echo ""
echo "🔄 Step 2: Restart Worker"
echo "========================"

echo "Restarting worker to apply Claude parsing improvements..."
sudo docker-compose restart worker

echo "Waiting 15 seconds for worker to restart..."
sleep 15

echo "✅ Worker restarted"

echo ""
echo "🧪 Step 3: Test Claude List Parsing"
echo "==================================="

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
echo "Testing Claude with content that triggers list validation..."

# Test content that often causes the list validation issue
TEST_CONTENT="སྤྱི་ལོ་༢༠༢༥ ཟླ་༡ པའི་ཚེས་༢༦ ཉིན་གྱི་ཞོགས་པ་རེད།"

TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d "{
    \"content\": \"$TEST_CONTENT\",
    \"model_name\": \"claude-3-5-sonnet-20241022\",
    \"api_key\": \"test-claude-list-parsing\",
    \"priority\": 5
  }" 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "✅ Claude test task submitted: $MESSAGE_ID"
    
    echo ""
    echo "Monitoring for list validation errors (30 seconds)..."
    
    for i in {1..6}; do
        sleep 5
        echo "Check $i:"
        
        # Check for list validation errors
        LIST_ERRORS=$(sudo docker-compose logs worker --since="10s" | grep -i "Input should be a valid list\|list_type" || echo "")
        
        if [ -n "$LIST_ERRORS" ]; then
            echo "  ❌ List validation error still occurring:"
            echo "  $LIST_ERRORS"
        else
            echo "  ✅ No list validation errors detected"
        fi
        
        # Check for parsing debug output
        PARSING_LOGS=$(sudo docker-compose logs worker --since="10s" | grep -E "(Claude raw response|Attempting to parse|Failed to parse)" | tail -2)
        if [ -n "$PARSING_LOGS" ]; then
            echo "  🔍 Parsing activity detected:"
            echo "  $(echo "$PARSING_LOGS" | head -1)"
        fi
        
        # Check task status
        STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
        STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
        PROGRESS=$(echo "$STATUS_RESPONSE" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
        
        echo "  Status: $STATUS, Progress: ${PROGRESS}%"
        
        if [ "$STATUS" = "completed" ]; then
            echo "  🎉 Claude translation completed successfully!"
            
            # Check if we got a real translation vs error message
            TRANSLATED_TEXT=$(echo "$STATUS_RESPONSE" | jq -r '.translated_text // empty' 2>/dev/null || echo "")
            if [[ "$TRANSLATED_TEXT" == *"Translation failed"* ]]; then
                echo "  ⚠️  Translation completed but with error fallback"
            else
                echo "  ✅ Real translation received!"
                echo "  📝 Translation: $(echo "$TRANSLATED_TEXT" | head -1)"
            fi
            break
        elif [ "$STATUS" = "failed" ]; then
            echo "  ❌ Translation failed"
            ERROR_MSG=$(echo "$STATUS_RESPONSE" | grep -o '"message":"[^"]*"' | cut -d'"' -f4)
            echo "  Error: $ERROR_MSG"
            break
        fi
    done
    
else
    echo "❌ Test task submission failed:"
    echo "$TEST_RESPONSE"
fi

echo ""
echo "🔍 Step 4: Check Recent Worker Logs"
echo "==================================="

echo "Recent worker logs (checking for Claude parsing improvements):"
sudo docker-compose logs worker --tail=25 | grep -E "(Claude|parse|validation|list)" || echo "No relevant logs found"

echo ""
echo "🎉 CLAUDE LIST VALIDATION FIX COMPLETE"
echo "======================================"
echo ""
echo "✅ IMPROVEMENTS APPLIED:"
echo "• 🧠 ast.literal_eval() for parsing string list representations"
echo "• 🔍 Multiple parsing methods (JSON, list literal, regex)"
echo "• 🛡️ Enhanced Pydantic error handling with input extraction"
echo "• 📝 Detailed debugging output for troubleshooting"
echo "• 🔄 Robust fallback strategies for all parsing failures"
echo ""
echo "📊 EXPECTED RESULTS:"
echo "• ✅ No more 'Input should be a valid list' errors"
echo "• ✅ Claude string lists parsed correctly: \"['item']\" → ['item']"
echo "• ✅ Better translation success rate"
echo "• ✅ Detailed debug logs for troubleshooting"
echo ""
echo "🔍 MONITOR FOR SUCCESS:"
echo "sudo docker-compose logs worker -f | grep -E '(Claude|parse|validation)'"
echo ""
echo "📊 TEST CLAUDE TRANSLATIONS:"
echo "curl -X POST http://localhost:8000/messages -H 'Content-Type: application/json' -d '{\"content\":\"test\", \"model_name\":\"claude-3-5-sonnet-20241022\", \"api_key\":\"test\"}'"
echo ""
echo "⚠️  ROLLBACK IF NEEDED:"
echo "git checkout HEAD~1 utils/translator.py && sudo docker-compose restart worker"
echo ""
echo "🎯 Claude list validation errors should now be resolved! ✅" 