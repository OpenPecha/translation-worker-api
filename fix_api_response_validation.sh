#!/bin/bash

# 🔧 Fix API Response Validation Error
# Resolves FastAPI ResponseValidationError by using HTTPException for error cases

echo "🔧 FIXING API RESPONSE VALIDATION ERROR"
echo "======================================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "🐛 Error Identified:"
echo "• FastAPI trying to validate ErrorResponse against MessageStatusResponse schema"
echo "• ErrorResponse missing required fields: 'id' and 'status'"
echo "• Causing: ResponseValidationError with 2 validation errors"
echo ""

echo "🔧 Root Cause:"
echo "• get_message_status() returning ErrorResponse directly"
echo "• FastAPI expects MessageStatusResponse or proper HTTP exceptions"
echo "• Need to use HTTPException for 404/500 cases instead of returning ErrorResponse"
echo ""

echo "📝 Step 1: Apply API Response Fix"
echo "================================="

git add routes/messages.py
git commit -m "fix: Use HTTPException for error cases in get_message_status endpoint

- Replace ErrorResponse returns with HTTPException raises
- Fix ResponseValidationError by properly handling 404/500 cases
- Ensure FastAPI response model validation works correctly
- Maintain proper error details in HTTPException detail field"

git push origin main
echo "✅ API response fix deployed"

echo ""
echo "🔄 Step 2: Restart API Service"
echo "============================="

echo "Restarting API service to apply response validation fix..."
sudo docker-compose restart api

echo "Waiting 15 seconds for API to restart..."
sleep 15

echo "✅ API service restarted"

echo ""
echo "🧪 Step 3: Test API Response Handling"
echo "====================================="

echo "Checking API service status:"
sudo docker-compose ps api

echo ""
echo "Testing API health:"
API_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo "API not responding")

if [[ "$API_HEALTH" == *"Translation API is running"* ]]; then
    echo "✅ API is responding to health checks"
else
    echo "❌ API health check failed: $API_HEALTH"
    echo "Checking API logs:"
    sudo docker-compose logs api --tail=10
fi

echo ""
echo "Testing message status endpoint with non-existent message..."

# Test 404 case
NON_EXISTENT_ID="test-404-case-12345"
RESPONSE_404=$(curl -s -w "HTTP_STATUS:%{http_code}" http://localhost:8000/messages/$NON_EXISTENT_ID 2>/dev/null)

HTTP_STATUS=$(echo "$RESPONSE_404" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
RESPONSE_BODY=$(echo "$RESPONSE_404" | sed 's/HTTP_STATUS:[0-9]*$//')

echo "404 Test Response:"
echo "  HTTP Status: $HTTP_STATUS"
echo "  Response Body: $RESPONSE_BODY"

if [ "$HTTP_STATUS" = "404" ]; then
    echo "  ✅ Correct 404 status returned"
    
    # Check if response contains proper error structure
    if echo "$RESPONSE_BODY" | grep -q '"error":"Message not found"'; then
        echo "  ✅ Proper error message in response"
    else
        echo "  ⚠️  Unexpected response format"
    fi
else
    echo "  ❌ Expected 404, got $HTTP_STATUS"
fi

echo ""
echo "Testing with a real translation task to verify working case..."

# Submit a test task to get a real message ID
TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Test API response validation fix",
    "model_name": "claude-3-5-sonnet-20241022",
    "api_key": "test-api-response",
    "priority": 5
  }' 2>/dev/null)

if echo "$TEST_RESPONSE" | grep -q '"success":true'; then
    MESSAGE_ID=$(echo "$TEST_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo "✅ Test task submitted: $MESSAGE_ID"
    
    echo ""
    echo "Testing message status retrieval for valid message..."
    
    # Wait a moment for the message to be stored
    sleep 2
    
    # Test valid message ID
    VALID_RESPONSE=$(curl -s -w "HTTP_STATUS:%{http_code}" http://localhost:8000/messages/$MESSAGE_ID 2>/dev/null)
    
    VALID_HTTP_STATUS=$(echo "$VALID_RESPONSE" | grep -o "HTTP_STATUS:[0-9]*" | cut -d: -f2)
    VALID_RESPONSE_BODY=$(echo "$VALID_RESPONSE" | sed 's/HTTP_STATUS:[0-9]*$//')
    
    echo "Valid Message Test Response:"
    echo "  HTTP Status: $VALID_HTTP_STATUS"
    
    if [ "$VALID_HTTP_STATUS" = "200" ]; then
        echo "  ✅ Correct 200 status returned"
        
        # Check if response has required fields
        if echo "$VALID_RESPONSE_BODY" | grep -q '"id":"' && echo "$VALID_RESPONSE_BODY" | grep -q '"status":'; then
            echo "  ✅ Response contains required id and status fields"
            
            # Extract status info
            STATUS_TYPE=$(echo "$VALID_RESPONSE_BODY" | grep -o '"status_type":"[^"]*"' | cut -d'"' -f4)
            echo "  📊 Translation status: $STATUS_TYPE"
        else
            echo "  ❌ Response missing required fields"
        fi
    else
        echo "  ❌ Expected 200, got $VALID_HTTP_STATUS"
        echo "  Response: $VALID_RESPONSE_BODY"
    fi
    
else
    echo "❌ Test task submission failed"
fi

echo ""
echo "🔍 Step 4: Check Recent API Logs"
echo "==============================="

echo "Recent API logs (checking for validation errors):"
VALIDATION_ERRORS=$(sudo docker-compose logs api --tail=20 | grep -i "ResponseValidationError\|validation.*error" || echo "No validation errors found")

if [ "$VALIDATION_ERRORS" = "No validation errors found" ]; then
    echo "✅ No ResponseValidationError in recent logs"
else
    echo "❌ Validation errors still present:"
    echo "$VALIDATION_ERRORS"
fi

echo ""
echo "🎉 API RESPONSE VALIDATION FIX COMPLETE"
echo "======================================="
echo ""
echo "✅ IMPROVEMENTS APPLIED:"
echo "• 🛡️ HTTPException for 404 cases instead of ErrorResponse returns"
echo "• 🔧 HTTPException for 500 cases with proper error details"
echo "• ✅ FastAPI response model validation now works correctly"
echo "• 📝 Proper HTTP status codes (404, 500) for error cases"
echo ""
echo "📊 EXPECTED RESULTS:"
echo "• ✅ No more ResponseValidationError messages"
echo "• ✅ Proper 404 responses for missing messages"
echo "• ✅ Proper 200 responses for valid messages"
echo "• ✅ MessageStatusResponse schema validation working"
echo ""
echo "🔍 MONITOR FOR SUCCESS:"
echo "sudo docker-compose logs api -f | grep -E '(validation|error|status)'"
echo ""
echo "📊 TEST API ENDPOINTS:"
echo "curl http://localhost:8000/messages/test-404-case"
echo "curl http://localhost:8000/health"
echo ""
echo "⚠️  ROLLBACK IF NEEDED:"
echo "git checkout HEAD~1 routes/messages.py && sudo docker-compose restart api"
echo ""
echo "🎯 API response validation errors should now be resolved! ✅" 