#!/bin/bash

# 🔧 Port 80 Conflict Fix Script
# Run this on your production server if port 80 conflicts persist

echo "🔍 DIAGNOSING PORT 80 CONFLICT"
echo "=============================="

# Check what's using port 80
echo "📊 Current port 80 usage:"
sudo netstat -tlnp | grep :80 || echo "No process found on port 80"
sudo lsof -i :80 || echo "No files open on port 80"

echo ""
echo "🐳 Current Docker containers:"
sudo docker ps | grep 80 || echo "No Docker containers using port 80"

echo ""
echo "🔧 SOLUTION OPTIONS:"
echo "==================="

# Option 1: Use different port
echo "Option 1: Use port 8080 instead of 80"
echo "   - Edit docker-compose.yml: change '80:8000' to '8080:8000'"
echo "   - Access API at: http://your-domain:8080"

# Option 2: Stop conflicting services
echo ""
echo "Option 2: Stop services using port 80"
echo "   sudo systemctl stop nginx"
echo "   sudo systemctl stop apache2"
echo "   sudo docker-compose up -d"

# Option 3: Use Nginx as reverse proxy
echo ""
echo "Option 3: Use Nginx as reverse proxy (recommended)"
echo "   - Change docker-compose.yml: '8000:8000' (internal port)"
echo "   - Configure Nginx to proxy to localhost:8000"
echo "   - Keep Nginx on port 80, Docker API on 8000"

echo ""
echo "🚀 QUICK FIXES:"
echo "==============="

read -p "Which solution do you want? (1=port 8080, 2=stop nginx, 3=nginx proxy, q=quit): " choice

case $choice in
    1)
        echo "🔧 Changing to port 8080..."
        sed -i 's/"80:8000"/"8080:8000"/' docker-compose.yml
        sudo docker-compose down
        sudo docker-compose up -d --build
        echo "✅ API now running on port 8080"
        echo "🔗 Test: curl http://localhost:8080/health"
        ;;
    2)
        echo "🛑 Stopping web services..."
        sudo systemctl stop nginx || echo "Nginx not running"
        sudo systemctl stop apache2 || echo "Apache not running"
        sudo docker-compose down
        sudo docker-compose up -d --build
        echo "✅ Docker API now running on port 80"
        echo "🔗 Test: curl http://localhost/health"
        ;;
    3)
        echo "🔧 Setting up Nginx proxy..."
        sed -i 's/"80:8000"/"8000:8000"/' docker-compose.yml
        sudo docker-compose down
        sudo docker-compose up -d --build
        echo "✅ Docker API running on port 8000"
        echo "📝 Now configure Nginx to proxy to localhost:8000"
        echo "🔗 Example Nginx config:"
        echo "   location / {"
        echo "       proxy_pass http://localhost:8000;"
        echo "       proxy_set_header Host \$host;"
        echo "   }"
        ;;
    *)
        echo "ℹ️ No changes made. Choose a solution and run again."
        ;;
esac

echo ""
echo "🏁 Done!" 