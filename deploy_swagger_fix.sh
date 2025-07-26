#!/bin/bash

# 🚀 Deploy Swagger UI at Root Domain
# This script applies the configuration changes to serve Swagger UI at the root of your domain

echo "🚀 DEPLOYING SWAGGER UI TO ROOT DOMAIN"
echo "======================================"

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "📝 Current status:"
echo "Before: Flower at https://translation-api.pecha.tools/"
echo "After:  Swagger UI at https://translation-api.pecha.tools/"
echo ""

echo "🔄 Step 1: Pull latest changes from Git..."
git fetch origin
git reset --hard origin/main
git pull origin main

echo "✅ Latest code pulled"

echo "🛑 Step 2: Stop current services..."
sudo docker-compose down --remove-orphans

echo "🔨 Step 3: Rebuild and start services..."
sudo docker-compose up -d --build

echo "⏳ Step 4: Wait for services to start..."
sleep 20

echo "🧪 Step 5: Test services..."

# Test FastAPI directly (internal container port)
echo "Testing FastAPI container:"
CONTAINER_TEST=$(sudo docker exec translation-worker-api-api-1 curl -f http://localhost:8000/health 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "✅ FastAPI container is running internally"
else
    echo "❌ FastAPI container not responding internally"
    echo "📋 Checking logs..."
    sudo docker-compose logs api --tail=10
    exit 1
fi

# Test Swagger UI via public port 80
echo "Testing Swagger UI on port 80:"
SWAGGER_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:80/ 2>/dev/null)
echo "Swagger UI status: HTTP $SWAGGER_TEST"

if [ "$SWAGGER_TEST" = "200" ]; then
    echo "✅ Swagger UI is accessible on port 80!"
    echo "🎉 SUCCESS! Swagger UI is accessible at: http://your-server-ip/"
    echo "🌍 Your domain should now work: https://translation-api.pecha.tools/"
else
    echo "❌ Swagger UI not accessible on port 80. Checking logs..."
    sudo docker-compose logs api --tail=5
fi

echo ""
echo "📊 DEPLOYMENT SUMMARY:"
echo "====================="
echo "🐳 Docker services: $(sudo docker-compose ps --services --filter 'status=running' | wc -l) running"
echo "🔗 FastAPI: http://your-server-ip/health"
echo "📚 Swagger UI: http://your-server-ip/ (root)"
echo "📖 ReDoc: http://your-server-ip/redoc"
echo "🌍 Domain: https://translation-api.pecha.tools/"
echo ""
echo "🎯 What's accessible now:"
echo "  • Swagger UI (API Documentation): https://translation-api.pecha.tools/"
echo "  • All API endpoints: https://translation-api.pecha.tools/messages, etc."
echo "  • Flower dashboard: Internal only (not public)"
echo ""
echo "✅ Deployment completed!" 