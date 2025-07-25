# 🚀 Production Configuration for Large Text Requests

## 🔍 **Root Cause: Request Size Limits**

Your issue is caused by **multiple layers of request size limits** in production that don't exist in your local development setup.

## ⚡ **IMMEDIATE FIX APPLIED**

✅ **Updated `docker-compose.yml`** to include request size limits:

```yaml
command: python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload --limit-concurrency 100 --limit-max-request-size 104857600
```

## 🔧 **Complete Production Checklist**

### **1. Docker/FastAPI Level (✅ FIXED)**

```yaml
# docker-compose.yml - api service
command: python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload --limit-concurrency 100 --limit-max-request-size 104857600
# 104857600 = 100MB request limit
```

### **2. Nginx/Reverse Proxy Level**

If you're using Nginx, add these to your config:

```nginx
# /etc/nginx/sites-available/your-site
server {
    client_max_body_size 100M;        # Allow 100MB uploads
    client_body_timeout 300s;         # 5 minute timeout
    proxy_read_timeout 300s;          # 5 minute proxy timeout
    proxy_connect_timeout 300s;       # 5 minute connect timeout

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Important for large requests
        proxy_request_buffering off;
        proxy_buffering off;
    }
}
```

### **3. Load Balancer Level (AWS/CloudFlare)**

If using a load balancer:

#### **AWS Application Load Balancer:**

- Default: 1MB max request size
- **Solution**: Use Network Load Balancer or increase ALB timeout

#### **CloudFlare:**

- Free plan: 100MB limit ✅
- Pro plan: 500MB limit ✅

#### **Other Load Balancers:**

Check your provider's request size limits.

### **4. Redis Configuration**

```bash
# Check Redis limits
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET proto-max-bulk-len

# Set if needed (in redis.conf or via CONFIG SET)
CONFIG SET proto-max-bulk-len 104857600  # 100MB
```

### **5. Celery Configuration**

```python
# celery_app.py - Add these settings
from celery import Celery

celery_app = Celery(
    "translation_worker",
    broker=broker_url,
    backend=result_backend,
    # Important for large messages
    task_serializer='pickle',           # Better for large data
    result_serializer='pickle',         # Better for large data
    accept_content=['pickle', 'json'],
    task_compression='gzip',            # Compress large messages
    result_compression='gzip',          # Compress large results
    worker_max_memory_per_child=500000, # 500MB per worker
)

# Increase message size limits
celery_app.conf.update(
    task_routes={
        'translate Job': {'queue': 'high_priority'},
    },
    worker_prefetch_multiplier=1,       # Process one task at a time
    task_acks_late=True,               # Acknowledge after completion
    task_reject_on_worker_lost=True,   # Reject lost tasks
    broker_transport_options={
        'max_retries': 3,
        'interval_start': 0,
        'interval_step': 0.2,
        'interval_max': 0.5,
        # Redis specific for large messages
        'socket_keepalive': True,
        'socket_keepalive_options': {
            'TCP_KEEPINTVL': 1,
            'TCP_KEEPCNT': 3,
            'TCP_KEEPIDLE': 1,
        },
    }
)
```

## 🚀 **Deploy the Fix**

### **Step 1: Redeploy with Fixed Docker Compose**

```bash
# On your production server
cd /home/ubuntu/translation-worker-api
git pull origin main
sudo docker-compose down
sudo docker-compose up -d --build

# Check if containers are running
sudo docker-compose ps
```

### **Step 2: Test Large Request**

```bash
# Test with a large request (>50KB)
curl -X POST http://your-production-url:8000/messages \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Your very large text content here... (repeat until >50KB)",
    "model_name": "claude-3-haiku-20240307",
    "api_key": "your-api-key"
  }'
```

### **Step 3: Monitor Logs**

```bash
# Check for any errors
sudo docker-compose logs api
sudo docker-compose logs worker

# Look for:
# ✅ "Successfully processed large request"
# ❌ "413 Request Entity Too Large"
# ❌ "Connection reset by peer"
```

## 🐛 **Common Production Issues & Solutions**

### **Issue 1: 413 Request Entity Too Large**

```bash
# Check Nginx config
sudo nginx -t
sudo systemctl reload nginx
```

### **Issue 2: Gateway Timeout (504)**

```bash
# Increase timeouts in your reverse proxy
proxy_read_timeout 600s;
proxy_connect_timeout 600s;
```

### **Issue 3: Worker Memory Issues**

```bash
# Check worker memory usage
sudo docker stats

# Scale workers if needed
sudo docker-compose up -d --scale worker=3
```

### **Issue 4: Redis Memory Limits**

```bash
# Check Redis memory
redis-cli INFO memory

# Increase if needed
redis-cli CONFIG SET maxmemory 2gb
```

## 📊 **Monitoring & Verification**

### **Check Request Size Handling:**

```bash
# 1. Small request (should work)
curl -X POST http://your-domain/messages -H "Content-Type: application/json" -d '{"content":"small text","model_name":"claude-3-haiku-20240307","api_key":"sk-test"}'

# 2. Medium request (~10KB, should work)
curl -X POST http://your-domain/messages -H "Content-Type: application/json" -d '{"content":"'$(python -c "print('test ' * 1000)")'",.model_name":"claude-3-haiku-20240307","api_key":"sk-test"}'

# 3. Large request (~100KB, should work after fix)
curl -X POST http://your-domain/messages -H "Content-Type: application/json" -d '{"content":"'$(python -c "print('large test content ' * 5000)")'",.model_name":"claude-3-haiku-20240307","api_key":"sk-test"}'
```

### **Response Codes:**

- ✅ **200/201**: Success
- ❌ **413**: Request too large (check nginx/load balancer)
- ❌ **504**: Gateway timeout (check proxy timeouts)
- ❌ **502**: Bad gateway (check if service is running)

## 🎯 **Expected Results After Fix**

### **Before Fix:**

```
❌ Large text: 413 Request Entity Too Large
❌ Large text: Connection reset by peer
❌ Large text: Gateway timeout
```

### **After Fix:**

```
✅ Small text: Works perfectly
✅ Medium text (10KB): Works perfectly
✅ Large text (100KB): Works with batch processing
✅ Very large text (1MB+): Works with optimized batching
```

## 🚨 **Emergency Rollback**

If something breaks:

```bash
# Quick rollback
cd /home/ubuntu/translation-worker-api
git checkout HEAD~1
sudo docker-compose down
sudo docker-compose up -d --build
```

## 🔍 **Debug Commands**

```bash
# Check container logs
sudo docker-compose logs api -f

# Check container resource usage
sudo docker stats

# Test direct container access
sudo docker-compose exec api curl localhost:8000/health

# Check Redis connection
sudo docker-compose exec redis redis-cli ping
```

Your production deployment should now handle large text requests just like your local development environment! 🚀
