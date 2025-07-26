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

# Test FastAPI directly
echo "Testing FastAPI container:"
if curl -f http://localhost:8000/health >/dev/null 2>&1; then
    echo "✅ FastAPI container is running"
else
    echo "❌ FastAPI container not responding"
    echo "📋 Checking logs..."
    sudo docker-compose logs api --tail=10
    exit 1
fi

# Test Swagger UI at root
echo "Testing Swagger UI at root:"
SWAGGER_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null)
echo "Swagger UI status: HTTP $SWAGGER_TEST"

if [ "$SWAGGER_TEST" = "200" ]; then
    echo "✅ Swagger UI is accessible at root!"
else
    echo "❌ Swagger UI not accessible. Checking logs..."
    sudo docker-compose logs api --tail=5
fi

# Test through domain (if Nginx is configured)
echo "Testing through domain:"
DOMAIN_TEST=$(curl -s -o /dev/null -w "%{http_code}" https://translation-api.pecha.tools/ 2>/dev/null)
echo "Domain status: HTTPS $DOMAIN_TEST"

if [ "$DOMAIN_TEST" = "200" ]; then
    echo "🎉 SUCCESS! Swagger UI is now accessible at https://translation-api.pecha.tools/"
elif [ "$DOMAIN_TEST" = "000" ]; then
    echo "⚠️  HTTPS not configured yet. Try HTTP:"
    HTTP_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://translation-api.pecha.tools/ 2>/dev/null)
    echo "Domain HTTP status: HTTP $HTTP_TEST"
    if [ "$HTTP_TEST" = "200" ]; then
        echo "✅ Swagger UI accessible at http://translation-api.pecha.tools/"
        echo "💡 Consider setting up HTTPS with: sudo certbot --nginx"
    fi
else
    echo "⚠️  Domain test failed. Check Nginx configuration."
fi

echo ""
echo "📊 DEPLOYMENT SUMMARY:"
echo "====================="
echo "🐳 Docker services: $(sudo docker-compose ps --services --filter 'status=running' | wc -l) running"
echo "🔗 FastAPI: http://localhost:8000/health"
echo "📚 Swagger UI: http://localhost:8000/ (root)"
echo "📖 ReDoc: http://localhost:8000/redoc"
echo "🌍 Public Domain: https://translation-api.pecha.tools/"
echo ""
echo "🎯 What's accessible now:"
echo "  • Swagger UI (API Documentation): https://translation-api.pecha.tools/"
echo "  • All API endpoints: https://translation-api.pecha.tools/messages, etc."
echo "  • Flower dashboard: Internal only (not public)"
echo ""
echo "✅ Deployment completed!" 