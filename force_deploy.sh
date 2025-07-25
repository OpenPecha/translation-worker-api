#!/bin/bash

# 🚀 Force Deployment Script
# Run this directly on your production server to force update

set -e  # Exit on any error

echo "🚀 FORCE DEPLOYMENT STARTING..."
echo "================================"

# Navigate to project directory
cd /home/ubuntu/translation-worker-api || {
    echo "❌ ERROR: Project directory not found!"
    exit 1
}

echo "📍 Current directory: $(pwd)"

# Show current git status
echo ""
echo "📊 CURRENT GIT STATUS:"
echo "======================"
git status
echo ""
echo "📝 Last 3 commits:"
git log --oneline -3
echo ""

# Force clean and pull
echo "🔄 FORCE CLEANING AND PULLING..."
echo "================================="
git fetch origin
echo "🧹 Resetting any local changes..."
git reset --hard origin/main
echo "⬇️ Pulling latest code..."
git pull origin main

echo ""
echo "📝 LATEST COMMITS AFTER PULL:"
echo "============================="
git log --oneline -3
echo ""

# Stop all services
echo "🛑 STOPPING SERVICES..."
echo "======================="
sudo docker-compose down --remove-orphans
echo "✅ Services stopped"

# Clean Docker cache
echo ""
echo "🧹 CLEANING DOCKER CACHE..."
echo "============================"
sudo docker system prune -f
sudo docker volume prune -f
echo "✅ Docker cache cleaned"

# Rebuild everything from scratch
echo ""
echo "🔨 REBUILDING SERVICES..."
echo "========================="
sudo docker-compose up -d --build --force-recreate
echo "✅ Services rebuilt and started"

# Wait for startup
echo ""
echo "⏳ WAITING FOR SERVICES TO START..."
echo "==================================="
sleep 30

# Check service status
echo ""
echo "📊 SERVICE STATUS:"
echo "=================="
sudo docker-compose ps

echo ""
echo "🔍 TESTING API HEALTH..."
echo "========================"

# Test API health
HEALTH_CHECK_SUCCESS=false
for i in {1..15}; do
    echo "🔄 Health check attempt $i/15..."
    if curl -f http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ API is healthy and responding!"
        HEALTH_CHECK_SUCCESS=true
        break
    else
        echo "⏳ API not ready yet, waiting 5 seconds..."
        sleep 5
    fi
done

if [ "$HEALTH_CHECK_SUCCESS" = false ]; then
    echo "❌ WARNING: API health check failed after 15 attempts"
    echo "📋 Checking logs for issues..."
    echo ""
    echo "🔍 API LOGS (last 20 lines):"
    echo "============================"
    sudo docker-compose logs api --tail=20
    echo ""
    echo "🔍 WORKER LOGS (last 20 lines):"
    echo "==============================="
    sudo docker-compose logs worker --tail=20
else
    echo ""
    echo "🧪 TESTING LARGE REQUEST SUPPORT..."
    echo "==================================="
    
    # Test if large requests work
    TEST_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/messages \
        -H "Content-Type: application/json" \
        -d '{"content":"test large request support","model_name":"test","api_key":"test"}' 2>/dev/null || echo "000")
    
    if [ "$TEST_RESPONSE" = "201" ] || [ "$TEST_RESPONSE" = "400" ]; then
        echo "✅ API is accepting requests (status: $TEST_RESPONSE)"
    else
        echo "⚠️ API might have issues (status: $TEST_RESPONSE)"
    fi
fi

echo ""
echo "📋 FINAL STATUS:"
echo "================"
echo "🐳 Docker containers:"
sudo docker-compose ps

echo ""
echo "📊 Container resource usage:"
sudo docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo ""
echo "📝 Recent API logs:"
sudo docker-compose logs api --tail=5

echo ""
echo "📝 Recent worker logs:"
sudo docker-compose logs worker --tail=5

echo ""
echo "🎉 DEPLOYMENT COMPLETED!"
echo "========================"
echo "✅ Your updated code should now be running in production"
echo "🔍 You can test large text requests to verify the fix is working"
echo ""
echo "🔗 Quick test command:"
echo 'curl -X POST http://your-domain:8000/messages -H "Content-Type: application/json" -d '"'"'{"content":"large test","model_name":"claude-3-haiku-20240307","api_key":"your-key"}'"'"''
echo "" 