#!/bin/bash

# 🔍 502 Bad Gateway Diagnostic & Fix Script
# Run this on your production server to fix the Nginx → FastAPI connection

echo "🔍 DIAGNOSING 502 BAD GATEWAY ERROR"
echo "===================================="

cd /home/ubuntu/translation-worker-api || {
    echo "❌ Cannot access project directory"
    exit 1
}

echo "📊 STEP 1: CHECK DOCKER CONTAINERS"
echo "=================================="
echo "Docker container status:"
sudo docker-compose ps

echo ""
echo "All Docker containers:"
sudo docker ps -a

echo ""
echo "📋 STEP 2: CHECK FASTAPI CONTAINER LOGS"
echo "======================================="
sudo docker-compose logs api --tail=30

echo ""
echo "🌐 STEP 3: CHECK NGINX STATUS & CONFIG"
echo "======================================"
echo "Nginx status:"
sudo systemctl status nginx --no-pager

echo ""
echo "Nginx configuration test:"
sudo nginx -t

echo ""
echo "Active Nginx sites:"
sudo ls -la /etc/nginx/sites-enabled/

echo ""
echo "🔍 STEP 4: CHECK CONNECTIVITY"
echo "============================="

echo "Testing if FastAPI container is reachable:"
echo "Local container test (127.0.0.1:8000):"
curl -v http://127.0.0.1:8000/health 2>&1 || echo "❌ Cannot reach FastAPI container"

echo ""
echo "Docker network test:"
CONTAINER_IP=$(sudo docker inspect translation-worker-api-api-1 --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
if [ -n "$CONTAINER_IP" ]; then
    echo "API Container IP: $CONTAINER_IP"
    curl -v http://$CONTAINER_IP:8000/health 2>&1 || echo "❌ Cannot reach container by IP"
else
    echo "❌ Cannot get API container IP"
fi

echo ""
echo "🔧 STEP 5: POTENTIAL ISSUES & FIXES"
echo "==================================="

# Check if API container is running
if ! sudo docker ps | grep -q "translation-worker-api-api"; then
    echo "❌ ISSUE 1: API container is not running!"
    echo "🔧 FIX: Starting API container..."
    sudo docker-compose up api -d
    sleep 10
    echo "✅ API container started"
fi

# Check if container is accessible on port 8000
if ! curl -f http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "❌ ISSUE 2: API not responding on localhost:8000"
    echo "🔧 POSSIBLE CAUSES:"
    echo "   - Container not binding to correct port"
    echo "   - Container crashed during startup"
    echo "   - Port conflict inside container"
    
    echo ""
    echo "🔧 FIX ATTEMPTS:"
    echo "1. Restart containers with port binding fix..."
    
    # Try binding to all interfaces instead of just 127.0.0.1
    sed -i 's/127.0.0.1:8000:8000/8000:8000/' docker-compose.yml
    sudo docker-compose down
    sudo docker-compose up -d
    
    echo "   Waiting for container to start..."
    sleep 15
    
    if curl -f http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ Fixed! API now responding on localhost:8000"
        
        # Update Nginx config to use localhost instead of 127.0.0.1
        sudo sed -i 's/127.0.0.1:8000/localhost:8000/g' /etc/nginx/sites-available/translation-api.pecha.tools
        sudo nginx -t && sudo systemctl reload nginx
        echo "✅ Updated Nginx configuration"
    else
        echo "❌ Still not working. Checking logs..."
        sudo docker-compose logs api --tail=10
    fi
fi

echo ""
echo "🧪 STEP 6: TEST FIXES"
echo "===================="

echo "Testing local API connection:"
LOCAL_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
echo "Local API status: HTTP $LOCAL_TEST"

if [ "$LOCAL_TEST" = "200" ]; then
    echo "✅ FastAPI is working locally!"
    
    echo "Testing through Nginx:"
    NGINX_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://translation-api.pecha.tools/health 2>/dev/null)
    echo "Nginx proxy status: HTTP $NGINX_TEST"
    
    if [ "$NGINX_TEST" = "200" ]; then
        echo "🎉 SUCCESS! Both FastAPI and Nginx are working!"
    else
        echo "❌ Nginx still having issues. Checking Nginx error logs..."
        sudo tail -20 /var/log/nginx/error.log
        
        echo ""
        echo "🔧 NGINX QUICK FIX:"
        cat > /tmp/nginx-fix.conf << 'EOF'
server {
    listen 80;
    server_name translation-api.pecha.tools;

    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
        sudo cp /tmp/nginx-fix.conf /etc/nginx/sites-available/translation-api.pecha.tools
        sudo nginx -t && sudo systemctl reload nginx
        echo "✅ Applied simplified Nginx config"
    fi
else
    echo "❌ FastAPI still not responding. Manual intervention needed."
    echo ""
    echo "🆘 EMERGENCY FIXES TO TRY:"
    echo "=========================="
    echo "1. Check if container is actually running:"
    echo "   sudo docker-compose ps"
    echo ""
    echo "2. Restart everything from scratch:"
    echo "   sudo docker-compose down"
    echo "   sudo docker-compose up -d --build"
    echo ""
    echo "3. Check container logs for errors:"
    echo "   sudo docker-compose logs api"
    echo ""
    echo "4. Try different port binding:"
    echo "   # Edit docker-compose.yml, change ports to:"
    echo "   # ports: ['8000:8000']  # No IP binding"
    echo ""
    echo "5. Test container health:"
    echo "   sudo docker exec translation-worker-api-api-1 curl localhost:8000/health"
fi

echo ""
echo "📋 CURRENT STATUS SUMMARY:"
echo "=========================="
echo "🐳 Docker containers: $(sudo docker-compose ps --services --filter 'status=running' | wc -l)/$(sudo docker-compose ps --services | wc -l) running"
echo "🌐 Nginx status: $(sudo systemctl is-active nginx)"
echo "🔗 Local API: HTTP $LOCAL_TEST"
echo "🌍 Domain: HTTP ${NGINX_TEST:-'Not tested'}"
echo ""
echo "🔍 Next steps: Check the output above for specific fixes applied." 