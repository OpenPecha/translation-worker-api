#!/bin/bash

# 🔍 Deployment Debug Script
# Run this on your production server to diagnose deployment issues

echo "🔍 DEPLOYMENT DIAGNOSTIC REPORT"
echo "==============================="
echo "Generated: $(date)"
echo ""

# Check current directory and git status
echo "📍 CURRENT LOCATION:"
echo "==================="
echo "Directory: $(pwd)"
echo "User: $(whoami)"
echo ""

# Navigate to project directory
cd /home/ubuntu/translation-worker-api 2>/dev/null || {
    echo "❌ ERROR: Cannot access /home/ubuntu/translation-worker-api"
    echo "🔍 Checking alternative locations..."
    find /home -name "translation-worker-api" -type d 2>/dev/null || echo "No project directory found"
    exit 1
}

echo "📊 GIT STATUS:"
echo "=============="
echo "Repository status:"
git status --porcelain
echo ""
echo "Current branch:"
git branch --show-current
echo ""
echo "Last 5 commits:"
git log --oneline -5
echo ""
echo "Remote status:"
git fetch origin 2>/dev/null
git status -uno
echo ""

# Check if there are uncommitted changes blocking pull
UNCOMMITTED=$(git status --porcelain)
if [ -n "$UNCOMMITTED" ]; then
    echo "⚠️ WARNING: Uncommitted changes detected:"
    echo "$UNCOMMITTED"
    echo ""
fi

# Check docker status
echo "🐳 DOCKER STATUS:"
echo "=================="
echo "Docker service status:"
sudo systemctl status docker | head -3
echo ""
echo "Docker-compose version:"
docker-compose --version
echo ""
echo "Current containers:"
sudo docker-compose ps
echo ""

# Check if containers are using old images
echo "🔍 DOCKER IMAGE INFO:"
echo "====================="
echo "Current images:"
sudo docker images | grep -E "(pecha|translation|api)" || echo "No matching images found"
echo ""

# Check recent container logs for errors
echo "📋 RECENT LOGS:"
echo "==============="
echo "API logs (last 10 lines):"
sudo docker-compose logs api --tail=10 2>/dev/null || echo "No API logs available"
echo ""
echo "Worker logs (last 10 lines):"
sudo docker-compose logs worker --tail=10 2>/dev/null || echo "No worker logs available"
echo ""

# Check file timestamps to see if code was actually updated
echo "📅 FILE TIMESTAMPS:"
echo "==================="
echo "docker-compose.yml:"
ls -la docker-compose.yml 2>/dev/null || echo "File not found"
echo ""
echo "Key source files:"
ls -la app.py celery_app.py utils/text_segmentation.py routes/messages.py 2>/dev/null || echo "Some files not found"
echo ""

# Check current docker-compose command
echo "🔧 CURRENT CONFIGURATION:"
echo "========================="
echo "Docker-compose.yml API command:"
grep -A 5 -B 2 "command:" docker-compose.yml | grep -A 7 "api:" || echo "Command not found"
echo ""

# Test if the fix is present
echo "🧪 CHECKING FOR REQUEST SIZE FIX:"
echo "=================================="
if grep -q "limit-max-request-size" docker-compose.yml; then
    echo "✅ Request size limit found in docker-compose.yml"
    grep "limit-max-request-size" docker-compose.yml
else
    echo "❌ Request size limit NOT found in docker-compose.yml"
    echo "This explains why large requests are failing!"
fi
echo ""

# Check if the API is actually responding
echo "🌐 API CONNECTIVITY TEST:"
echo "========================="
echo "Testing local API connection..."
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
if [ "$API_STATUS" = "200" ]; then
    echo "✅ API is responding (HTTP $API_STATUS)"
else
    echo "❌ API is not responding (HTTP $API_STATUS)"
fi
echo ""

# Check system resources
echo "💻 SYSTEM RESOURCES:"
echo "===================="
echo "Memory usage:"
free -h
echo ""
echo "Disk usage:"
df -h / /home 2>/dev/null || df -h /
echo ""

# Check if GitHub webhook/deployment is working
echo "🔗 GITHUB INTEGRATION:"
echo "======================"
echo "Last git fetch/pull time:"
stat .git/FETCH_HEAD 2>/dev/null | grep Modify || echo "Git fetch info not available"
echo ""

# Suggest next steps
echo "🎯 RECOMMENDED ACTIONS:"
echo "======================="

if grep -q "limit-max-request-size" docker-compose.yml; then
    echo "1. ✅ Configuration looks correct"
    echo "2. 🔄 Try force restart: sudo docker-compose down && sudo docker-compose up -d --build"
else
    echo "1. ❌ URGENT: docker-compose.yml missing request size fix"
    echo "   Run: git pull origin main"
    echo "2. 🔄 After pull: sudo docker-compose down && sudo docker-compose up -d --build"
fi

if [ "$API_STATUS" != "200" ]; then
    echo "3. 🔍 Check API logs: sudo docker-compose logs api"
    echo "4. 🔍 Check worker logs: sudo docker-compose logs worker"
fi

if [ -n "$UNCOMMITTED" ]; then
    echo "5. 🧹 Clean uncommitted changes: git reset --hard origin/main"
fi

echo ""
echo "🚀 QUICK FIX COMMAND:"
echo "git pull origin main && sudo docker-compose down && sudo docker-compose up -d --build --force-recreate"
echo ""
echo "�� Debug complete!" 