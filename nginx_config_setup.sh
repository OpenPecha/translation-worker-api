#!/bin/bash

# 🔧 Nginx Reverse Proxy Setup for translation-api.pecha.tools
# Run this on your production server to configure domain to FastAPI

echo "🌐 SETTING UP NGINX REVERSE PROXY"
echo "=================================="
echo "Domain: https://translation-api.pecha.tools"
echo "Target: FastAPI container on localhost:8000"
echo ""

# Check if Nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "❌ Nginx not found. Installing..."
    sudo apt update
    sudo apt install nginx -y
fi

# Create Nginx configuration for the domain
echo "📝 Creating Nginx configuration..."

cat > /tmp/translation-api.pecha.tools << 'EOF'
server {
    listen 80;
    server_name translation-api.pecha.tools;

    # Large file upload support (for large text requests)
    client_max_body_size 100M;
    client_body_timeout 300s;
    client_header_timeout 300s;

    # Proxy to FastAPI container
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for large requests
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;

        # Disable buffering for real-time updates
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
    }
}
EOF

# Copy configuration to Nginx
sudo cp /tmp/translation-api.pecha.tools /etc/nginx/sites-available/translation-api.pecha.tools

# Enable the site
sudo ln -sf /etc/nginx/sites-available/translation-api.pecha.tools /etc/nginx/sites-enabled/

# Remove default site if it exists
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
echo "🧪 Testing Nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration is valid"
    
    # Restart Nginx
    echo "🔄 Restarting Nginx..."
    sudo systemctl restart nginx
    sudo systemctl enable nginx
    
    echo "✅ Nginx configured and running!"
else
    echo "❌ Nginx configuration has errors. Please check the config."
    exit 1
fi

# Set up SSL with Let's Encrypt (optional but recommended)
echo ""
echo "🔒 SETTING UP SSL (HTTPS)..."
echo "============================"

if ! command -v certbot &> /dev/null; then
    echo "📦 Installing Certbot..."
    sudo apt update
    sudo apt install certbot python3-certbot-nginx -y
fi

echo "🔐 Obtaining SSL certificate..."
sudo certbot --nginx -d translation-api.pecha.tools --non-interactive --agree-tos --email admin@pecha.tools

if [ $? -eq 0 ]; then
    echo "✅ SSL certificate installed successfully!"
    echo "🌐 Your API is now available at: https://translation-api.pecha.tools"
else
    echo "⚠️ SSL setup failed. Your API is available at: http://translation-api.pecha.tools"
fi

# Test the setup
echo ""
echo "🧪 TESTING THE SETUP..."
echo "======================="

echo "Testing local FastAPI..."
LOCAL_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null)
if [ "$LOCAL_TEST" = "200" ]; then
    echo "✅ FastAPI responding locally (HTTP $LOCAL_TEST)"
else
    echo "❌ FastAPI not responding locally (HTTP $LOCAL_TEST)"
    echo "🔍 Check: sudo docker-compose ps"
    echo "🔍 Check: sudo docker-compose logs api"
fi

echo "Testing domain..."
DOMAIN_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://translation-api.pecha.tools/health 2>/dev/null)
if [ "$DOMAIN_TEST" = "200" ]; then
    echo "✅ Domain responding (HTTP $DOMAIN_TEST)"
else
    echo "❌ Domain not responding (HTTP $DOMAIN_TEST)"
    echo "🔍 Check DNS: nslookup translation-api.pecha.tools"
    echo "🔍 Check Nginx: sudo systemctl status nginx"
fi

echo ""
echo "📋 FINAL STATUS:"
echo "================"
echo "✅ Nginx reverse proxy configured"
echo "✅ Domain: translation-api.pecha.tools → localhost:8000"
echo "✅ Large file uploads supported (100MB)"
echo "✅ SSL/HTTPS configured (if successful)"
echo ""
echo "🔗 Test your API:"
echo "curl https://translation-api.pecha.tools/health"
echo "curl -X POST https://translation-api.pecha.tools/messages -H 'Content-Type: application/json' -d '{\"content\":\"test\",\"model_name\":\"claude-3-haiku-20240307\",\"api_key\":\"your-key\"}'"
echo ""
echo "�� Setup complete!" 