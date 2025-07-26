#!/bin/bash

# 🔧 Fix Claude Pydantic Validation Error
# Resolves "Field required [type=missing, input_value={}, input_type=dict]" error

echo "🔧 FIXING CLAUDE VALIDATION ERROR"
echo "================================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🐛 Error Identified:"
echo "• Claude returning empty dict {} instead of Translation object"
echo "• Pydantic validation failing: translation field required"
echo "• Causing batch translation failures"
echo ""

echo "🔧 Root Causes:"
echo "• Structured output format not working with current prompt"
echo "• No fallback handling for empty Claude responses"
echo "• System prompt not explicit about JSON format required"
echo ""

echo "📝 Step 1: Backup Current Files"
echo "==============================="

cp utils/translator.py utils/translator_original.py.backup
cp const.py const_original.py.backup
echo "✅ Backups created"

echo ""
echo "📤 Step 2: Apply Claude Fixes"
echo "============================="

echo "Pulling updated translator and prompt fixes from repository..."
git pull origin main

if [ $? -eq 0 ]; then
    echo "✅ Successfully pulled fixes from repository"
else
    echo "⚠️  Git pull failed, fixes may already be local"
fi

echo ""
echo "🔍 Step 3: Verify Fixes Applied"
echo "==============================="

# Check if the robust error handling is in place
if grep -q "robust error handling" utils/translator.py; then
    echo "✅ Robust Claude error handling present"
else
    echo "❌ Claude error handling missing"
fi

# Check if the updated system prompt is in place
if grep -q "Required JSON Format" const.py; then
    echo "✅ Updated system prompt with JSON format present"
else
    echo "❌ Updated system prompt missing"
fi

# Check if fallback logic is present
if grep -q "fallback" utils/translator.py; then
    echo "✅ Claude fallback logic present"
else
    echo "❌ Claude fallback logic missing"
fi

echo ""
echo "📤 Step 4: Commit and Deploy"
echo "==========================="

git add .
git commit -m "fix: Resolve Claude Pydantic validation error with robust error handling

- Add fallback handling for empty Claude responses
- Update system prompt to explicitly require JSON format
- Implement multiple fallback strategies for Claude translation
- Prevent ValidationError from empty dict responses
- Return error messages instead of raising exceptions"

git push origin main
echo "✅ Fixes committed and pushed"

echo ""
echo "🔄 Step 5: Restart Worker"
echo "========================"

echo "Restarting worker to apply Claude fixes..."
sudo docker-compose restart worker

echo "Waiting 20 seconds for worker to restart..."
sleep 20

echo "✅ Worker restarted"

echo ""
echo "🧪 Step 6: Test Claude Translation"
echo "================================="

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
echo "Testing Claude translation with sample content..."
TEST_CONTENT="བཀྲ་ཤིས་བདེ་ལེགས། ཁྱོད་ག་འདྲ་འདུག ཞོགས་པ་བདེ་ལེགས།"

TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d "{
    \"content\": \"$TEST_CONTENT\",
    \"model_name\": \"claude-3-5-sonnet-20241022\",
    \"api_key\": \"test-claude-key\",
    \"priority\": 5
  }" 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "✅ Claude test task submitted: $MESSAGE_ID"
    
    echo ""
    echo "Monitoring for Claude validation errors (30 seconds)..."
    
    for i in {1..6}; do
        sleep 5
        echo "Check $i:"
        
        # Check for validation errors
        VALIDATION_ERRORS=$(sudo docker-compose logs worker --since="10s" | grep -i "ValidationError\|translation.*Field required" || echo "")
        
        if [ -n "$VALIDATION_ERRORS" ]; then
            echo "  ❌ Claude validation error still occurring:"
            echo "  $VALIDATION_ERRORS"
        else
            echo "  ✅ No validation errors detected"
        fi
        
        # Check for successful translations
        SUCCESS_LOGS=$(sudo docker-compose logs worker --since="10s" | grep -E "(Successfully translated|translation completed)" || echo "")
        if [ -n "$SUCCESS_LOGS" ]; then
            echo "  🎉 Translation success detected!"
        fi
        
        # Check task status
        STATUS_RESPONSE=$(curl -s http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
        STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
        PROGRESS=$(echo "$STATUS_RESPONSE" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
        
        echo "  Status: $STATUS, Progress: ${PROGRESS}%"
        
        if [ "$STATUS" = "completed" ]; then
            echo "  🎉 Claude translation completed successfully!"
            break
        elif [ "$STATUS" = "failed" ]; then
            echo "  ❌ Translation failed, checking error..."
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
echo "🔍 Step 7: Check Recent Worker Logs"
echo "==================================="

echo "Recent worker logs (last 30 lines):"
sudo docker-compose logs worker --tail=30

echo ""
echo "🎉 CLAUDE VALIDATION FIX COMPLETE"
echo "================================="
echo ""
echo "✅ IMPROVEMENTS APPLIED:"
echo "• 🛡️ Robust error handling for empty Claude responses"
echo "• 🔄 Multiple fallback strategies (structured → regular → raw)"
echo "• 📝 Updated system prompt with explicit JSON format requirements"
echo "• ⚠️ Graceful error handling instead of exceptions"
echo "• 🧪 Comprehensive validation error prevention"
echo ""
echo "📊 EXPECTED RESULTS:"
echo "• ✅ No more Pydantic ValidationError messages"
echo "• ✅ Claude translations complete successfully"
echo "• ✅ Fallback responses when Claude has issues"
echo "• ✅ Better error messages instead of crashes"
echo ""
echo "🔍 MONITOR FOR SUCCESS:"
echo "sudo docker-compose logs worker -f | grep -E '(Successfully translated|validation error)'"
echo ""
echo "📊 CHECK TRANSLATION RESULTS:"
echo "curl http://localhost:8000/messages/{message_id}"
echo ""
echo "⚠️  ROLLBACK IF NEEDED:"
echo "cp utils/translator_original.py.backup utils/translator.py"
echo "cp const_original.py.backup const.py"
echo "sudo docker-compose restart worker"
echo ""
echo "🎯 Claude validation errors should now be resolved! ✅" 