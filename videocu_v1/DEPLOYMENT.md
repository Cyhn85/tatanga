# VIDEOCU v1 - Production Deployment Guide

Complete guide for deploying VIDEOCU v1 to production with Docker.

---

## 📋 Prerequisites

### Required
- ✅ Linux VPS (Hetzner Cloud, AWS, DigitalOcean, etc.)
- ✅ Docker & Docker Compose installed
- ✅ Domain name (optional, but recommended for HTTPS)
- ✅ Gemini API key (https://makersuite.google.com/app/apikey)

### Recommended
- YouTube Data API v3 key
- ElevenLabs API key
- Pexels/Unsplash API keys

---

## 🚀 Quick Start

### 1. Server Preparation
```bash
# Connect to your server
ssh root@your_server_ip

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y
```

### 2. Deploy Application
```bash
# Create project directory
mkdir -p /opt/videocu && cd /opt/videocu

# Upload/clone your project
# (via git clone or scp)

# Configure environment
cp .env.example .env
nano .env  # Fill in your API keys

# Start all services
docker compose up -d

# Check status
docker compose ps
```

### 3. Verify Deployment
```bash
# Test API
curl http://localhost:8000/health

# Expected: {"status":"healthy",...}
```

---

## 🔧 Detailed Configuration

### Environment Variables (.env)

**Required:**
```env
POSTGRES_PASSWORD=your_strong_password
GEMINI_API_KEY=your_gemini_key
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

**Optional:**
```env
YOUTUBE_API_KEY=your_youtube_key
ELEVENLABS_API_KEY=your_elevenlabs_key
PEXELS_API_KEY=your_pexels_key
```

### Services Overview

1. **postgres** - Database (Port: 5432)
2. **redis** - Task queue (Port: 6379)
3. **api** - FastAPI server (Port: 8000)
4. **worker** - Celery worker (video production)
5. **beat** - Celery scheduler (analytics collection)

---

## 🌐 SSL/HTTPS Setup (Nginx)

### Install Nginx
```bash
apt install nginx certbot python3-certbot-nginx -y
```

### Configure Nginx
Create `/etc/nginx/sites-available/videocu`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    client_max_body_size 1000M;
}
```

### Enable & Get Certificate
```bash
ln -s /etc/nginx/sites-available/videocu /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
certbot --nginx -d your-domain.com
```

---

## 🔍 Monitoring & Maintenance

### View Logs
```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f beat
```

### Restart Services
```bash
docker compose restart api
```

### Update Application
```bash
git pull
docker compose build
docker compose up -d
```

### Database Backup
```bash
docker compose exec postgres pg_dump -U videocu_user videocu_db > backup.sql
```

---

## 🐛 Troubleshooting

### Check Service Health
```bash
docker compose ps
docker compose logs <service_name>
```

### Common Issues

**Container won't start:**
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

**Database connection error:**
```bash
docker compose logs postgres
docker compose restart postgres
```

**Out of disk space:**
```bash
docker system prune -a --volumes
rm -rf /opt/videocu/output/videos/*
```

---

## 🔐 Security

1. **Strong passwords** - Use complex POSTGRES_PASSWORD
2. **Firewall** - Only open ports 80, 443, 22
3. **Regular updates** - `apt update && apt upgrade`
4. **API key rotation** - Change keys every 90 days
5. **Disable root SSH** - Use sudo user instead

---

## 📚 Resources

- API Docs: https://your-domain.com/docs
- ReDoc: https://your-domain.com/redoc
- Docker Docs: https://docs.docker.com/
- FastAPI Docs: https://fastapi.tiangolo.com/

---

**Version**: 1.0.0
**Last Updated**: 2025-11-26
