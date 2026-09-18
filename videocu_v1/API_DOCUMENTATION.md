# VIDEOCU v1 - API Documentation

## Overview

The VIDEOCU v1 FastAPI backend provides a RESTful API with WebSocket support for real-time updates, enabling integration with web applications, mobile apps, and automation workflows.

**Base URL**: `http://localhost:8000`
**WebSocket URL**: `ws://localhost:8000/ws`

---

## Quick Start

### 1. Start the API Server

```bash
python api_server.py
```

Expected output:
```
🚀 VIDEOCU v1 - FastAPI Server
======================================================================
📡 API Docs: http://localhost:8000/docs
📡 ReDoc: http://localhost:8000/redoc
🔌 WebSocket: ws://localhost:8000/ws
======================================================================
```

### 2. Access Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 3. Test the API

```bash
python test_api_client.py
```

---

## Authentication

The API uses JWT (JSON Web Token) authentication for protected endpoints.

### Login

**Endpoint**: `POST /auth/login`
**Authentication**: None (public endpoint)

**Request**:
```json
{
  "username": "admin",
  "password": "videocu2025"
}
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Demo Credentials**:
| Username | Password |
|----------|----------|
| admin    | videocu2025 |
| demo     | demo123  |

### Using the Token

Include the token in the Authorization header for all protected endpoints:

```bash
Authorization: Bearer {access_token}
```

**Token Expiration**: 24 hours

---

## Endpoints

### General

#### Root
**Endpoint**: `GET /`
**Authentication**: None

**Response**:
```json
{
  "name": "VIDEOCU v1 API",
  "version": "1.0.0",
  "status": "online",
  "docs": "/docs",
  "websocket": "/ws"
}
```

#### Health Check
**Endpoint**: `GET /health`
**Authentication**: None

**Response**:
```json
{
  "status": "healthy",
  "chef_ai": {
    "ai_enabled": true,
    "registered_agents": ["video_producer", "social_media_manager", "music_composer", "server_administrator"],
    "supported_tasks": ["video_creation", "music_creation", "social_media_management", "server_administration"]
  },
  "agents": ["video_producer", "social_media_manager", "music_composer", "server_administrator"],
  "skills": 8,
  "timestamp": "2025-11-26T12:00:00"
}
```

---

### Tasks

#### Create Task
**Endpoint**: `POST /api/tasks`
**Authentication**: Required

Creates a new task using natural language prompts.

**Request**:
```json
{
  "prompt": "60 saniyelik Mars hakkında YouTube videosu yap",
  "user_id": "user_123"
}
```

**Response**:
```json
{
  "task_id": "20251126_120000_abc123",
  "status": "completed",
  "analysis": {
    "task_type": "video_creation",
    "platform": "youtube",
    "parameters": {
      "topic": "Mars hakkında",
      "duration": 60,
      "language": "de"
    },
    "assigned_agents": ["video_producer", "social_media_manager"]
  },
  "result": {
    "success": true,
    "agent_results": {
      "video_producer": {
        "success": true,
        "video_path": "output/test_video.mp4",
        "production_id": "test_001"
      },
      "social_media_manager": {
        "success": true,
        "metadata": {
          "title": "Mars hakkında | Tutorial 2025",
          "description": "...",
          "tags": ["mars", "guide", "2025"]
        }
      }
    }
  },
  "created_at": "2025-11-26T12:00:00",
  "completed_at": "2025-11-26T12:02:30"
}
```

**Natural Language Examples**:
- `"60 saniyelik Mars kolonizasyonu hakkında YouTube videosu yap"`
- `"TikTok için viral kedi videosu oluştur"`
- `"Fotoğraflarımdan 30 saniyelik anı videosu yap"`
- `"Mırıldandığım melodiden jazz müzik yap"`
- `"Instagram Reels için 15 saniyelik motivasyon videosu"`

#### Get Task
**Endpoint**: `GET /api/tasks/{task_id}`
**Authentication**: Required

Retrieves task details by ID.

**Response**: Same as Create Task response

#### List Tasks
**Endpoint**: `GET /api/tasks`
**Authentication**: Required

**Query Parameters**:
- `limit` (int, default: 10) - Number of tasks to return
- `offset` (int, default: 0) - Pagination offset

**Response**:
```json
{
  "total": 42,
  "completed": 38,
  "limit": 10,
  "offset": 0,
  "tasks": []
}
```

---

### Metrics

#### Record Metrics
**Endpoint**: `POST /api/metrics`
**Authentication**: Required

Records performance metrics for a completed task.

**Request**:
```json
{
  "task_id": "20251126_120000_abc123",
  "platform": "youtube",
  "views": 5000,
  "likes": 250,
  "ctr": 8.5,
  "avg_watch_time": 52.3
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Metrics recorded"
}
```

---

### Skills

#### List Skills
**Endpoint**: `GET /api/skills`
**Authentication**: Required

**Query Parameters**:
- `category` (string, optional) - Filter by category

**Response**:
```json
{
  "skills": {
    "video_production": {
      "create_standard_video": {
        "name": "create_standard_video",
        "description": "Create standard YouTube video (60s, 16:9)",
        "parameters": {
          "topic": "string",
          "duration": "int (seconds)",
          "language": "string (de/en/tr)"
        },
        "category": "video_production",
        "has_implementation": false
      }
    }
  },
  "stats": {
    "total_skills": 8,
    "categories": 3,
    "category_breakdown": {
      "video_production": 4,
      "music_creation": 2,
      "social_media": 2
    }
  }
}
```

#### Search Skills
**Endpoint**: `GET /api/skills/search`
**Authentication**: Required

**Query Parameters**:
- `keyword` (string, required) - Search term

**Response**:
```json
{
  "results": [
    {
      "category": "video_production",
      "skill": "create_standard_video",
      "description": "Create standard YouTube video (60s, 16:9)"
    }
  ],
  "count": 1
}
```

---

### Agents

#### List Agents
**Endpoint**: `GET /api/agents`
**Authentication**: Required

**Response**:
```json
{
  "agents": [
    "video_producer",
    "social_media_manager",
    "music_composer",
    "server_administrator"
  ],
  "count": 4,
  "supported_tasks": [
    "video_creation",
    "music_creation",
    "social_media_management",
    "server_administration"
  ]
}
```

---

### Memory

#### Memory Statistics
**Endpoint**: `GET /api/memory/stats`
**Authentication**: Required

**Response**:
```json
{
  "total_tasks": 42,
  "completed_tasks": 38,
  "total_metrics": 38,
  "best_practices_count": 5
}
```

#### Best Practices
**Endpoint**: `GET /api/memory/best-practices`
**Authentication**: Required

**Query Parameters**:
- `task_type` (string, required) - Task type (e.g., "video_creation")
- `platform` (string, optional) - Platform filter (e.g., "youtube")

**Response**:
```json
{
  "task_type": "video_creation",
  "platform": "youtube",
  "practices": [
    {
      "parameters": {
        "duration": 60,
        "style": "informativ"
      },
      "avg_views": 15000,
      "sample_size": 10
    }
  ],
  "count": 1
}
```

---

### System

#### System Health
**Endpoint**: `GET /api/system/health`
**Authentication**: Required

Detailed system health check using Server Administrator Agent.

**Response**:
```json
{
  "success": true,
  "timestamp": "2025-11-26T12:00:00",
  "overall_status": "healthy",
  "cpu": {
    "usage_percent": 25.4,
    "count": 8,
    "status": "healthy"
  },
  "memory": {
    "total_gb": 16.0,
    "used_gb": 7.2,
    "available_gb": 8.8,
    "percent": 45.0,
    "status": "healthy"
  },
  "disk": {
    "total_gb": 1000.0,
    "used_gb": 217.0,
    "free_gb": 783.0,
    "percent": 21.7,
    "status": "healthy"
  },
  "processes": {
    "count": 342
  }
}
```

---

### Files

#### Download File
**Endpoint**: `GET /api/files/{filename}`
**Authentication**: Required

Downloads a produced file (video, audio, etc.)

**Response**: File download

---

## WebSocket

### Connection

**URL**: `ws://localhost:8000/ws`

Connect to receive real-time updates about task progress and system events.

### Message Types

#### Server → Client

**Task Created**:
```json
{
  "type": "task_created",
  "task_id": "20251126_120000_abc123",
  "status": "in_progress",
  "timestamp": "2025-11-26T12:00:00"
}
```

**Task Progress**:
```json
{
  "type": "task_progress",
  "task_id": "20251126_120000_abc123",
  "progress": 45,
  "message": "Generating images...",
  "timestamp": "2025-11-26T12:01:00"
}
```

**Task Completed**:
```json
{
  "type": "task_completed",
  "task_id": "20251126_120000_abc123",
  "status": "completed",
  "timestamp": "2025-11-26T12:02:30"
}
```

#### Client → Server

**Echo Test**:
```json
{
  "type": "ping",
  "timestamp": "2025-11-26T12:00:00"
}
```

**Response**:
```json
{
  "type": "echo",
  "data": {...},
  "timestamp": "2025-11-26T12:00:00"
}
```

---

## Python Client Example

```python
import requests

# 1. Login
response = requests.post("http://localhost:8000/auth/login", json={
    "username": "admin",
    "password": "videocu2025"
})
token = response.json()['access_token']

# 2. Create headers
headers = {
    'Authorization': f'Bearer {token}'
}

# 3. Create task
task_response = requests.post(
    "http://localhost:8000/api/tasks",
    headers=headers,
    json={
        "prompt": "60 saniyelik Mars hakkında YouTube videosu yap",
        "user_id": "user_123"
    }
)
task = task_response.json()
print(f"Task ID: {task['task_id']}")
print(f"Status: {task['status']}")

# 4. Record metrics
requests.post(
    "http://localhost:8000/api/metrics",
    headers=headers,
    json={
        "task_id": task['task_id'],
        "platform": "youtube",
        "views": 5000,
        "likes": 250,
        "ctr": 8.5,
        "avg_watch_time": 52.3
    }
)
```

---

## JavaScript Client Example

```javascript
// 1. Login
const loginResponse = await fetch('http://localhost:8000/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        username: 'admin',
        password: 'videocu2025'
    })
});
const {access_token} = await loginResponse.json();

// 2. Create task
const taskResponse = await fetch('http://localhost:8000/api/tasks', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${access_token}`
    },
    body: JSON.stringify({
        prompt: '60 saniyelik Mars hakkında YouTube videosu yap',
        user_id: 'user_123'
    })
});
const task = await taskResponse.json();
console.log('Task ID:', task.task_id);
console.log('Status:', task.status);

// 3. WebSocket connection
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
    console.log('WebSocket connected');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Message:', data.type);
};
```

---

## Error Responses

All endpoints return standardized error responses:

**401 Unauthorized**:
```json
{
  "detail": "Invalid authentication credentials"
}
```

**404 Not Found**:
```json
{
  "detail": "Task not found"
}
```

**500 Internal Server Error**:
```json
{
  "detail": "Internal server error message"
}
```

**503 Service Unavailable**:
```json
{
  "detail": "Chef AI not initialized"
}
```

---

## Rate Limiting

**Not implemented yet**. In production, consider:
- Rate limiting per user/IP
- Request throttling
- API quotas

---

## Deployment

### Development

```bash
python api_server.py
```

### Production (with Gunicorn)

```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker api_server:app
```

### Docker

```bash
docker build -t videocu-api .
docker run -p 8000:8000 videocu-api
```

---

## Security Considerations

### Production Checklist

✅ **Change SECRET_KEY**: Use cryptographically secure key
✅ **HTTPS Only**: Use SSL/TLS certificates
✅ **Database Auth**: Use real database instead of demo credentials
✅ **CORS**: Configure allowed origins properly
✅ **Rate Limiting**: Implement request rate limiting
✅ **Input Validation**: Validate all user inputs
✅ **Logging**: Log all API requests and errors
✅ **Monitoring**: Set up health monitoring

---

## Support

**Issues**: Report at GitHub repository
**Documentation**: http://localhost:8000/docs
**Test Client**: `python test_api_client.py`

---

**Version**: 1.0.0
**Last Updated**: 2025-11-26
