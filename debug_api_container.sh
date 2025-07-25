#!/bin/bash

# 🔍 API Container Debug Script
# Run this on your production server to find why API container isn't starting

echo "🔍 DIAGNOSING API CONTAINER ISSUE"
echo "=================================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "📊 Current container status:"
sudo docker-compose ps

echo ""
echo "🐳 All Docker processes:"
sudo docker ps -a | grep api || echo "No API container found"

echo ""
echo "📋 Docker-compose logs for API:"
echo "==============================="
sudo docker-compose logs api 2>/dev/null || echo "No API logs available"

echo ""
echo "🔍 Docker-compose config validation:"
echo "===================================="
sudo docker-compose config

echo ""
echo "📊 Port 80 status:"
echo "=================="
sudo netstat -tlnp | grep :80 || echo "Port 80 is free"
sudo lsof -i :80 || echo "No process using port 80"

echo ""
echo "🔧 ATTEMPTING TO START API MANUALLY:"
echo "===================================="

echo "Step 1: Try starting just the API service..."
sudo docker-compose up api --no-deps -d 2>&1

echo ""
echo "Step 2: Check API logs again..."
sudo docker-compose logs api --tail=20 2>/dev/null

echo ""
echo "🩺 POTENTIAL ISSUES & FIXES:"
echo "============================"

# Check if it's a port conflict
if sudo netstat -tlnp | grep :80 > /dev/null; then
    echo "⚠️ PORT CONFLICT DETECTED!"
    echo "Something is using port 80:"
    sudo netstat -tlnp | grep :80
    echo ""
    echo "🔧 QUICK FIXES:"
    echo "1. Use port 8080: sed -i 's/\"80:8000\"/\"8080:8000\"/' docker-compose.yml"
    echo "2. Stop conflicting service: sudo systemctl stop nginx"
    echo "3. Kill process: sudo fuser -k 80/tcp"
fi

# Check docker-compose file
if grep -q "80:8000" docker-compose.yml; then
    echo "✅ Docker-compose configured for port 80"
else
    echo "⚠️ Port 80 not found in docker-compose.yml"
    echo "Current API port config:"
    grep -A 2 -B 2 "ports:" docker-compose.yml | grep -A 5 "api:" || echo "API ports not found"
fi

echo ""
echo "🚀 EMERGENCY FIXES:"
echo "==================="
echo "Fix 1 - Use port 8080 instead:"
echo "  sed -i 's/\"80:8000\"/\"8080:8000\"/' docker-compose.yml"
echo "  sudo docker-compose down && sudo docker-compose up -d"
echo ""
echo "Fix 2 - Use internal port 8000 with Nginx proxy:"
echo "  sed -i 's/\"80:8000\"/\"8000:8000\"/' docker-compose.yml" 
echo "  sudo docker-compose down && sudo docker-compose up -d"
echo "  # Then configure Nginx to proxy to localhost:8000"
echo ""
echo "Fix 3 - Remove port binding temporarily:"
echo "  # Comment out ports section in docker-compose.yml for API"
echo "  sudo docker-compose down && sudo docker-compose up -d"
echo ""

echo "🔍 Current docker-compose.yml API section:"
echo "=========================================="
sed -n '/# FastAPI application/,/# Celery worker/p' docker-compose.yml

echo ""
echo "💡 RECOMMENDATION:"
echo "=================="
echo "Run one of the emergency fixes above, then test with:"
echo "curl http://localhost:8080/health  # if using port 8080"
echo "curl http://localhost:8000/health  # if using port 8000" 