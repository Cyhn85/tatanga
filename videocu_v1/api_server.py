"""
VIDEOCU v1 - FastAPI Backend
REST API + WebSocket server for Chef AI system

Features:
- REST API endpoints
- WebSocket real-time updates
- JWT authentication
- CORS support
- API documentation (Swagger)
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import jwt
import uvicorn

# Import VIDEOCU components
from modules.chef_ai import ChefAI
from modules.skill_library import SkillLibrary, initialize_default_skills
from modules.agent_memory import AgentMemory
from modules.agents import (
    VideoProducerAgent,
    SocialMediaManagerAgent,
    MusicComposerAgent,
    ServerAdministratorAgent
)

logger = logging.getLogger(__name__)

# ========== Configuration ==========
SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'videocu_secret_key_change_in_production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# ========== Pydantic Models ==========

class TaskRequest(BaseModel):
    """Request to create a task"""
    prompt: str
    user_id: Optional[str] = "anonymous"

class TaskResponse(BaseModel):
    """Response after task creation"""
    task_id: str
    status: str
    analysis: Optional[Dict] = None
    result: Optional[Dict] = None
    created_at: str
    completed_at: Optional[str] = None

class HealthResponse(BaseModel):
    """System health check response"""
    status: str
    chef_ai: Dict
    agents: List[str]
    skills: int
    timestamp: str

class LoginRequest(BaseModel):
    """Login credentials"""
    username: str
    password: str

class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"

class MetricsRequest(BaseModel):
    """Request to record metrics"""
    task_id: str
    platform: str
    views: int = 0
    likes: int = 0
    ctr: float = 0.0
    avg_watch_time: float = 0.0

# ========== Security ==========

security = HTTPBearer()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Verify JWT token"""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return {"username": username}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

# ========== FastAPI App ==========

app = FastAPI(
    title="VIDEOCU v1 API",
    description="AI-powered video production system with multi-agent architecture",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Global State ==========

chef_ai: Optional[ChefAI] = None
skill_library: Optional[SkillLibrary] = None
agent_memory: Optional[AgentMemory] = None
active_connections: List[WebSocket] = []

# ========== WebSocket Manager ==========

class ConnectionManager:
    """Manage WebSocket connections"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept new connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove connection"""
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict):
        """Broadcast message to all connections"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

manager = ConnectionManager()

# ========== Startup/Shutdown ==========

@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    global chef_ai, skill_library, agent_memory

    logger.info("🚀 Starting VIDEOCU v1 API Server...")

    # Initialize Chef AI
    gemini_key = os.getenv('GEMINI_API_KEY', 'test_key')
    chef_ai = ChefAI(gemini_api_key=gemini_key)

    # Initialize Skill Library
    skill_library = SkillLibrary()
    initialize_default_skills(skill_library)

    # Initialize Agent Memory
    agent_memory = AgentMemory()

    # Register agents (using mocks for now to avoid heavy dependencies)
    class MockVideoProducer:
        def produce_video(self, *args, **kwargs):
            return {'status': 'completed', 'files': {'video': 'test_video.mp4'}, 'production_id': 'test_001'}
        def produce_long_form_video(self, *args, **kwargs):
            return {'status': 'completed', 'files': {'video': 'test_long_video.mp4'}, 'segments_created': 5}
        def produce_from_photos(self, *args, **kwargs):
            return {'status': 'completed', 'files': {'video': 'test_photo_video.mp4'}}

    video_agent = VideoProducerAgent(
        orchestrator=MockVideoProducer(),
        skill_library=skill_library
    )
    chef_ai.register_agent('video_producer', video_agent)

    social_agent = SocialMediaManagerAgent(
        youtube_uploader=None,
        skill_library=skill_library
    )
    chef_ai.register_agent('social_media_manager', social_agent)

    music_agent = MusicComposerAgent(skill_library=skill_library)
    chef_ai.register_agent('music_composer', music_agent)

    server_agent = ServerAdministratorAgent(skill_library=skill_library)
    chef_ai.register_agent('server_administrator', server_agent)

    logger.info("✅ VIDEOCU v1 API Server ready!")
    logger.info(f"   Chef AI: {len(chef_ai.get_status()['registered_agents'])} agents")
    logger.info(f"   Skill Library: {skill_library.get_stats()['total_skills']} skills")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("👋 Shutting down VIDEOCU v1 API Server...")
    if agent_memory:
        agent_memory.close()

# ========== Public Endpoints (No Auth) ==========

@app.get("/", tags=["General"])
async def root():
    """API root endpoint"""
    return {
        "name": "VIDEOCU v1 API",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "websocket": "/ws"
    }

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(credentials: LoginRequest):
    """
    Login endpoint - Returns JWT token

    Demo credentials:
    - username: admin
    - password: videocu2025
    """
    # Simple authentication (replace with database in production)
    DEMO_USERS = {
        "admin": "videocu2025",
        "demo": "demo123"
    }

    if credentials.username not in DEMO_USERS:
        raise HTTPException(status_code=401, detail="Invalid username")

    if DEMO_USERS[credentials.username] != credentials.password:
        raise HTTPException(status_code=401, detail="Invalid password")

    access_token = create_access_token(
        data={"sub": credentials.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return TokenResponse(access_token=access_token)

@app.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check():
    """System health check"""
    if not chef_ai:
        raise HTTPException(status_code=503, detail="System not initialized")

    status_data = chef_ai.get_status()

    return HealthResponse(
        status="healthy",
        chef_ai=status_data,
        agents=status_data['registered_agents'],
        skills=skill_library.get_stats()['total_skills'],
        timestamp=datetime.now().isoformat()
    )

# ========== Protected Endpoints (Require Auth) ==========

@app.post("/api/tasks", response_model=TaskResponse, tags=["Tasks"])
async def create_task(
    request: TaskRequest,
    user: Dict = Depends(verify_token)
):
    """
    Create a new task

    Accepts natural language prompts and returns task results
    """
    if not chef_ai:
        raise HTTPException(status_code=503, detail="Chef AI not initialized")

    try:
        # Execute task through Chef AI
        result = chef_ai.execute_order(
            raw_prompt=request.prompt,
            user_id=request.user_id or user['username']
        )

        # Record in agent memory
        agent_memory.record_task(result)

        # Broadcast to WebSocket clients
        await manager.broadcast({
            "type": "task_created",
            "task_id": result['task_id'],
            "status": result['status'],
            "timestamp": datetime.now().isoformat()
        })

        return TaskResponse(**result)

    except Exception as e:
        logger.error(f"Task creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
async def get_task(
    task_id: str,
    user: Dict = Depends(verify_token)
):
    """Get task by ID"""
    # In production, query from agent_memory database
    raise HTTPException(status_code=404, detail="Task not found")

@app.get("/api/tasks", tags=["Tasks"])
async def list_tasks(
    limit: int = 10,
    offset: int = 0,
    user: Dict = Depends(verify_token)
):
    """List all tasks"""
    if not agent_memory:
        raise HTTPException(status_code=503, detail="Agent memory not initialized")

    stats = agent_memory.get_stats()

    return {
        "total": stats['total_tasks'],
        "completed": stats['completed_tasks'],
        "limit": limit,
        "offset": offset,
        "tasks": []  # TODO: Query from database
    }

@app.post("/api/metrics", tags=["Metrics"])
async def record_metrics(
    request: MetricsRequest,
    user: Dict = Depends(verify_token)
):
    """Record performance metrics for a task"""
    if not agent_memory:
        raise HTTPException(status_code=503, detail="Agent memory not initialized")

    try:
        agent_memory.record_metrics(
            task_id=request.task_id,
            platform=request.platform,
            metrics={
                'views': request.views,
                'likes': request.likes,
                'ctr': request.ctr,
                'avg_watch_time': request.avg_watch_time
            }
        )

        return {"status": "success", "message": "Metrics recorded"}

    except Exception as e:
        logger.error(f"Metrics recording failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/skills", tags=["Skills"])
async def list_skills(
    category: Optional[str] = None,
    user: Dict = Depends(verify_token)
):
    """List available skills"""
    if not skill_library:
        raise HTTPException(status_code=503, detail="Skill library not initialized")

    if category:
        skills = skill_library.list_skills(category)
    else:
        skills = skill_library.list_skills()

    return {
        "skills": skills,
        "stats": skill_library.get_stats()
    }

@app.get("/api/skills/search", tags=["Skills"])
async def search_skills(
    keyword: str,
    user: Dict = Depends(verify_token)
):
    """Search skills by keyword"""
    if not skill_library:
        raise HTTPException(status_code=503, detail="Skill library not initialized")

    results = skill_library.query_skills_by_keyword(keyword)

    return {"results": results, "count": len(results)}

@app.get("/api/agents", tags=["Agents"])
async def list_agents(user: Dict = Depends(verify_token)):
    """List registered agents"""
    if not chef_ai:
        raise HTTPException(status_code=503, detail="Chef AI not initialized")

    status = chef_ai.get_status()

    return {
        "agents": status['registered_agents'],
        "count": len(status['registered_agents']),
        "supported_tasks": status['supported_tasks']
    }

@app.get("/api/memory/stats", tags=["Memory"])
async def memory_stats(user: Dict = Depends(verify_token)):
    """Get agent memory statistics"""
    if not agent_memory:
        raise HTTPException(status_code=503, detail="Agent memory not initialized")

    return agent_memory.get_stats()

@app.get("/api/memory/best-practices", tags=["Memory"])
async def best_practices(
    task_type: str,
    platform: Optional[str] = None,
    user: Dict = Depends(verify_token)
):
    """Get best practices for task type"""
    if not agent_memory:
        raise HTTPException(status_code=503, detail="Agent memory not initialized")

    practices = agent_memory.query_best_practices(task_type, platform)

    return {
        "task_type": task_type,
        "platform": platform,
        "practices": practices,
        "count": len(practices)
    }

@app.get("/api/system/health", tags=["System"])
async def system_health(user: Dict = Depends(verify_token)):
    """Detailed system health check"""
    # Use server administrator agent
    if not chef_ai or 'server_administrator' not in chef_ai.agents:
        raise HTTPException(status_code=503, detail="Server agent not available")

    server_agent = chef_ai.agents['server_administrator']

    health_task = {
        'task_id': f'health_{datetime.now().timestamp()}',
        'analysis': {
            'task_type': 'server_administration',
            'parameters': {'admin_task': 'health_check'}
        }
    }

    result = server_agent.execute_task(health_task)

    return result

@app.get("/api/files/{filename}", tags=["Files"])
async def download_file(
    filename: str,
    user: Dict = Depends(verify_token)
):
    """Download produced file"""
    file_path = Path("output") / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path)

# ========== Celery Async Task Endpoints ==========

class AsyncTaskRequest(BaseModel):
    """Request for async task"""
    prompt: str
    user_id: Optional[str] = "api"
    options: Optional[Dict] = None

class AsyncTaskResponse(BaseModel):
    """Response for async task submission"""
    celery_task_id: str
    status: str
    message: str

class BatchTaskRequest(BaseModel):
    """Request for batch video production"""
    prompts: List[str]
    user_id: Optional[str] = "api"

@app.post("/api/async/video", response_model=AsyncTaskResponse, tags=["Async Tasks"])
async def create_video_async(
    request: AsyncTaskRequest,
    user: Dict = Depends(verify_token)
):
    """
    Create video asynchronously via Celery

    Returns immediately with a task ID for status checking
    """
    try:
        from celery_tasks.video_tasks import produce_video_async

        task = produce_video_async.delay(
            prompt=request.prompt,
            user_id=request.user_id or user['username'],
            options=request.options
        )

        # Broadcast to WebSocket
        await manager.broadcast({
            "type": "async_task_started",
            "celery_task_id": task.id,
            "timestamp": datetime.now().isoformat()
        })

        return AsyncTaskResponse(
            celery_task_id=task.id,
            status="queued",
            message="Video production task queued"
        )

    except Exception as e:
        logger.error(f"Async task creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/async/batch", tags=["Async Tasks"])
async def create_batch_videos(
    request: BatchTaskRequest,
    user: Dict = Depends(verify_token)
):
    """
    Create multiple videos in batch

    Queues all videos for parallel production
    """
    try:
        from celery_tasks.video_tasks import produce_video_batch

        task = produce_video_batch.delay(
            prompts=request.prompts,
            user_id=request.user_id or user['username']
        )

        return {
            "celery_task_id": task.id,
            "status": "queued",
            "batch_size": len(request.prompts),
            "message": f"Batch of {len(request.prompts)} videos queued"
        }

    except Exception as e:
        logger.error(f"Batch task creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/async/status/{task_id}", tags=["Async Tasks"])
async def get_async_task_status(
    task_id: str,
    user: Dict = Depends(verify_token)
):
    """
    Get status of an async Celery task

    States: PENDING, PROCESSING, UPLOADING, SUCCESS, FAILURE
    """
    try:
        from celery_app import celery_app

        task = celery_app.AsyncResult(task_id)

        response = {
            "task_id": task_id,
            "status": task.status,
            "ready": task.ready()
        }

        if task.ready():
            if task.successful():
                response["result"] = task.result
            else:
                response["error"] = str(task.result)
        elif task.info:
            response["progress"] = task.info

        return response

    except Exception as e:
        logger.error(f"Task status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/async/cancel/{task_id}", tags=["Async Tasks"])
async def cancel_async_task(
    task_id: str,
    user: Dict = Depends(verify_token)
):
    """Cancel a pending Celery task"""
    try:
        from celery_app import celery_app

        celery_app.control.revoke(task_id, terminate=True)

        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Task cancellation requested"
        }

    except Exception as e:
        logger.error(f"Task cancellation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== Scheduled Task Triggers ==========

@app.post("/api/triggers/analytics", tags=["Triggers"])
async def trigger_analytics_collection(
    platform: Optional[str] = None,
    user: Dict = Depends(verify_token)
):
    """Manually trigger analytics collection"""
    try:
        from celery_tasks.analytics_tasks import collect_all_analytics, collect_platform_analytics

        if platform:
            task = collect_platform_analytics.delay(platform=platform)
        else:
            task = collect_all_analytics.delay()

        return {
            "celery_task_id": task.id,
            "status": "triggered",
            "message": f"Analytics collection started for {platform or 'all platforms'}"
        }

    except Exception as e:
        logger.error(f"Analytics trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/triggers/learning", tags=["Triggers"])
async def trigger_learning_cycle(
    user: Dict = Depends(verify_token)
):
    """Manually trigger a learning cycle"""
    try:
        from celery_tasks.learning_tasks import run_learning_cycle

        task = run_learning_cycle.delay()

        return {
            "celery_task_id": task.id,
            "status": "triggered",
            "message": "Learning cycle started"
        }

    except Exception as e:
        logger.error(f"Learning cycle trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/triggers/cleanup", tags=["Triggers"])
async def trigger_cleanup(
    max_age_days: int = 7,
    dry_run: bool = True,
    user: Dict = Depends(verify_token)
):
    """Manually trigger file cleanup"""
    try:
        from celery_tasks.analytics_tasks import cleanup_old_files

        task = cleanup_old_files.delay(
            max_age_days=max_age_days,
            dry_run=dry_run
        )

        return {
            "celery_task_id": task.id,
            "status": "triggered",
            "dry_run": dry_run,
            "message": f"Cleanup started (files older than {max_age_days} days)"
        }

    except Exception as e:
        logger.error(f"Cleanup trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/celery/stats", tags=["Celery"])
async def get_celery_stats(user: Dict = Depends(verify_token)):
    """Get Celery worker statistics"""
    try:
        from celery_app import celery_app

        inspect = celery_app.control.inspect()

        stats = {
            "active_tasks": inspect.active() or {},
            "scheduled_tasks": inspect.scheduled() or {},
            "reserved_tasks": inspect.reserved() or {},
            "registered_tasks": inspect.registered() or {},
            "stats": inspect.stats() or {}
        }

        return stats

    except Exception as e:
        logger.error(f"Celery stats failed: {e}")
        return {
            "status": "unavailable",
            "error": str(e),
            "message": "Celery workers may not be running"
        }

# ========== WebSocket Endpoint ==========

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates

    Messages sent:
    - task_created: When new task is created
    - task_progress: Progress updates
    - task_completed: When task finishes
    """
    await manager.connect(websocket)

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_json()

            # Echo back (or process commands)
            await websocket.send_json({
                "type": "echo",
                "data": data,
                "timestamp": datetime.now().isoformat()
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# ========== Run Server ==========

if __name__ == "__main__":
    import sys

    # UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('output/api_server.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    print("\n" + "="*70)
    print("🚀 VIDEOCU v1 - FastAPI Server")
    print("="*70)
    print(f"📡 API Docs: http://localhost:8000/docs")
    print(f"📡 ReDoc: http://localhost:8000/redoc")
    print(f"🔌 WebSocket: ws://localhost:8000/ws")
    print("="*70 + "\n")

    # Run server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
