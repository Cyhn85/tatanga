"""
VIDEOCU v1 - Trend Analysis API Endpoints
Google Trends, YouTube Trends, TikTok, Instagram
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import trend analyzers
from modules.trend_analyzer import TrendAnalyzer, YOUTUBE_CATEGORIES_DE
from modules.social_trend_analyzer import SocialTrendAnalyzer

logger = logging.getLogger(__name__)

# ========== Pydantic Models ==========

class TrendItem(BaseModel):
    keyword: str
    rank: int
    region: str
    score: int
    discovered_at: str
    avg_interest: Optional[int] = None

class YouTubeVideo(BaseModel):
    platform: str = "youtube"
    video_id: str
    title: str
    channel: str
    views: int
    likes: int
    comments: int
    url: str
    region: str
    category: Optional[str] = None
    score: int

class SocialVideo(BaseModel):
    platform: str
    video_id: Optional[str] = None
    media_id: Optional[str] = None
    title: str
    author: str
    views: int
    likes: int
    comments: int
    shares: Optional[int] = 0
    url: str
    score: int

class TrendAnalysisResponse(BaseModel):
    status: str
    timestamp: str
    source: str
    count: int
    data: List[Dict]

# ========== FastAPI App ==========

app = FastAPI(
    title="VIDEOCU Trend API",
    description="Google Trends, YouTube, TikTok, Instagram trend analysis",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Global Instances ==========

trend_analyzer: Optional[TrendAnalyzer] = None
social_analyzer: Optional[SocialTrendAnalyzer] = None

@app.on_event("startup")
async def startup():
    global trend_analyzer, social_analyzer

    logger.info("Starting Trend API...")

    # Initialize Google Trends + YouTube
    youtube_key = os.getenv('YOUTUBE_API_KEY')
    trend_analyzer = TrendAnalyzer(youtube_api_key=youtube_key)

    # Initialize TikTok + Instagram
    social_analyzer = SocialTrendAnalyzer(
        tiktok_ms_token=os.getenv('MS_TOKEN'),
        instagram_username=os.getenv('INSTAGRAM_USERNAME'),
        instagram_password=os.getenv('INSTAGRAM_PASSWORD')
    )

    logger.info("Trend API ready!")

# ========== Public Endpoints ==========

@app.get("/")
async def root():
    return {
        "service": "VIDEOCU Trend API",
        "version": "1.0.0",
        "endpoints": [
            "/api/trends/germany",
            "/api/trends/youtube",
            "/api/trends/youtube/category/{category_id}",
            "/api/trends/social",
            "/api/trends/tiktok",
            "/api/trends/combined",
            "/api/trends/analyze/{keyword}"
        ]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ========== Google Trends Endpoints ==========

@app.get("/api/trends/germany", response_model=TrendAnalysisResponse)
async def get_germany_trends(limit: int = Query(10, ge=1, le=50)):
    """
    Get trending searches from Germany (Google Trends)
    """
    if not trend_analyzer:
        raise HTTPException(status_code=503, detail="Trend analyzer not initialized")

    try:
        trends = trend_analyzer.get_trending_searches_germany(limit=limit)

        return TrendAnalysisResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            source="google_trends",
            count=len(trends),
            data=trends
        )
    except Exception as e:
        logger.error(f"Germany trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trends/analyze/{keyword}")
async def analyze_keyword(keyword: str, region: str = Query("DE")):
    """
    Analyze trend potential for a keyword
    """
    if not trend_analyzer:
        raise HTTPException(status_code=503, detail="Trend analyzer not initialized")

    try:
        analysis = trend_analyzer.analyze_trend_potential(keyword, region)
        related = trend_analyzer.get_related_queries(keyword, region)

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis,
            "related_queries": related
        }
    except Exception as e:
        logger.error(f"Keyword analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== YouTube Endpoints ==========

@app.get("/api/trends/youtube", response_model=TrendAnalysisResponse)
async def get_youtube_trends(
    region: str = Query("DE"),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get YouTube trending videos
    """
    if not trend_analyzer:
        raise HTTPException(status_code=503, detail="Trend analyzer not initialized")

    try:
        videos = trend_analyzer.get_youtube_trending_videos(
            region_code=region,
            max_results=limit
        )

        return TrendAnalysisResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            source="youtube",
            count=len(videos),
            data=videos
        )
    except Exception as e:
        logger.error(f"YouTube trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trends/youtube/category/{category_id}")
async def get_youtube_category_trends(
    category_id: str,
    region: str = Query("DE"),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get YouTube trending by category

    Categories: 1=Film, 10=Music, 17=Sports, 20=Gaming, 24=Entertainment, etc.
    """
    if not trend_analyzer:
        raise HTTPException(status_code=503, detail="Trend analyzer not initialized")

    try:
        videos = trend_analyzer.get_youtube_trending_by_category(
            category_id=category_id,
            region_code=region,
            max_results=limit
        )

        category_name = YOUTUBE_CATEGORIES_DE.get(category_id, f"Category {category_id}")

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "source": "youtube",
            "category": category_name,
            "category_id": category_id,
            "count": len(videos),
            "data": videos
        }
    except Exception as e:
        logger.error(f"YouTube category trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trends/youtube/categories")
async def list_youtube_categories():
    """List all YouTube categories"""
    return {
        "categories": YOUTUBE_CATEGORIES_DE
    }

# ========== TikTok Endpoints ==========

@app.get("/api/trends/tiktok", response_model=TrendAnalysisResponse)
async def get_tiktok_trends(count: int = Query(30, ge=1, le=100)):
    """
    Get TikTok trending videos
    """
    if not social_analyzer:
        raise HTTPException(status_code=503, detail="Social analyzer not initialized")

    try:
        videos = await social_analyzer.get_tiktok_trending(count=count)

        return TrendAnalysisResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            source="tiktok",
            count=len(videos),
            data=videos
        )
    except Exception as e:
        logger.error(f"TikTok trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== Instagram Endpoints ==========

@app.get("/api/trends/instagram")
async def get_instagram_trends(
    hashtags: str = Query("reelsdeutschland,deutschland,viral,trending"),
    per_tag: int = Query(10, ge=1, le=30)
):
    """
    Get Instagram Reels by hashtags

    Pass hashtags as comma-separated string
    """
    if not social_analyzer:
        raise HTTPException(status_code=503, detail="Social analyzer not initialized")

    try:
        hashtag_list = [h.strip() for h in hashtags.split(",")]
        reels = social_analyzer.get_instagram_trending_by_hashtags(
            hashtags=hashtag_list,
            amount_per_tag=per_tag
        )

        return TrendAnalysisResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            source="instagram",
            count=len(reels),
            data=reels
        )
    except Exception as e:
        logger.error(f"Instagram trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== Combined Endpoints ==========

@app.get("/api/trends/social", response_model=TrendAnalysisResponse)
async def get_social_trends(
    tiktok_count: int = Query(30),
    instagram_hashtags: str = Query("reelsdeutschland,deutschland,viral"),
    top_n: int = Query(50)
):
    """
    Get combined TikTok + Instagram trends
    """
    if not social_analyzer:
        raise HTTPException(status_code=503, detail="Social analyzer not initialized")

    try:
        hashtag_list = [h.strip() for h in instagram_hashtags.split(",")]
        combined = await social_analyzer.get_combined_trending(
            tiktok_count=tiktok_count,
            instagram_hashtags=hashtag_list,
            top_n=top_n
        )

        return TrendAnalysisResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            source="tiktok+instagram",
            count=len(combined),
            data=combined
        )
    except Exception as e:
        logger.error(f"Social trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trends/combined")
async def get_all_trends(
    google_limit: int = Query(10),
    youtube_limit: int = Query(10),
    tiktok_count: int = Query(20),
    region: str = Query("DE")
):
    """
    Get all trends from all sources
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "region": region,
        "google_trends": [],
        "youtube": [],
        "tiktok": [],
        "instagram": []
    }

    # Google Trends
    try:
        if trend_analyzer:
            results["google_trends"] = trend_analyzer.get_trending_searches_germany(limit=google_limit)
    except Exception as e:
        logger.error(f"Google Trends error: {e}")

    # YouTube
    try:
        if trend_analyzer:
            results["youtube"] = trend_analyzer.get_youtube_trending_videos(
                region_code=region, max_results=youtube_limit
            )
    except Exception as e:
        logger.error(f"YouTube error: {e}")

    # TikTok
    try:
        if social_analyzer:
            results["tiktok"] = await social_analyzer.get_tiktok_trending(count=tiktok_count)
    except Exception as e:
        logger.error(f"TikTok error: {e}")

    return results

# ========== Keywords Extraction ==========

@app.post("/api/trends/keywords")
async def extract_keywords(content_list: List[Dict]):
    """
    Extract trending keywords from content list
    """
    if not social_analyzer:
        raise HTTPException(status_code=503, detail="Social analyzer not initialized")

    keywords = social_analyzer.get_trending_keywords_from_content(content_list)

    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "keywords": keywords
    }

# ========== Run Server ==========

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*60)
    print("VIDEOCU Trend API")
    print("="*60)
    print("Endpoints:")
    print("   /api/trends/germany    - Google Trends")
    print("   /api/trends/youtube    - YouTube Trending")
    print("   /api/trends/tiktok     - TikTok Trending")
    print("   /api/trends/instagram  - Instagram Reels")
    print("   /api/trends/social     - Combined Social")
    print("   /api/trends/combined   - All Sources")
    print("="*60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")
