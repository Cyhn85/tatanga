"""
VIDEOCU v1 - YouTube Uploader Module
OAuth2 + YouTube Data API v3 ile video yükleme
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import pickle

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class YouTubeUploader:
    """YouTube Data API v3 ile video yükleme ve yönetim"""

    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    API_SERVICE_NAME = 'youtube'
    API_VERSION = 'v3'

    def __init__(self,
                 client_secrets_file: str = "client_secrets.json",
                 credentials_file: str = "youtube_credentials.pickle"):
        """
        Args:
            client_secrets_file: OAuth2 client secrets JSON dosyası
            credentials_file: Kaydedilmiş credentials (pickle)
        """
        self.client_secrets_file = Path(client_secrets_file)
        self.credentials_file = Path(credentials_file)
        self.youtube = None
        self._authenticate()

    def _authenticate(self):
        """YouTube API OAuth2 authentication"""
        try:
            credentials = None

            # Load saved credentials if exist
            if self.credentials_file.exists():
                logger.info("🔑 Loading saved credentials...")
                with open(self.credentials_file, 'rb') as f:
                    credentials = pickle.load(f)

            # Refresh or create new credentials
            if not credentials or not credentials.valid:
                if credentials and credentials.expired and credentials.refresh_token:
                    logger.info("🔄 Refreshing credentials...")
                    credentials.refresh(Request())
                else:
                    if not self.client_secrets_file.exists():
                        logger.error(f"❌ Client secrets file not found: {self.client_secrets_file}")
                        logger.info("💡 Get client_secrets.json from:")
                        logger.info("   https://console.cloud.google.com/apis/credentials")
                        self.youtube = None
                        return

                    logger.info("🔐 Starting OAuth2 flow...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.client_secrets_file),
                        self.SCOPES
                    )
                    credentials = flow.run_local_server(port=8080)

                # Save credentials
                with open(self.credentials_file, 'wb') as f:
                    pickle.dump(credentials, f)
                logger.info(f"💾 Credentials saved: {self.credentials_file}")

            # Build YouTube service
            self.youtube = build(
                self.API_SERVICE_NAME,
                self.API_VERSION,
                credentials=credentials
            )

            logger.info("✅ YouTube API authenticated successfully")

        except Exception as e:
            logger.error(f"❌ Authentication failed: {e}")
            self.youtube = None

    def upload_video(self,
                    video_path: str,
                    title: str,
                    description: str,
                    tags: List[str] = None,
                    category_id: str = "28",  # Science & Technology
                    privacy_status: str = "public",
                    thumbnail_path: Optional[str] = None,
                    publish_at: Optional[datetime] = None) -> Optional[Dict]:
        """
        Video yükle ve yayınla

        Args:
            video_path: Video dosyası
            title: Video başlığı (max 100 chars)
            description: Video açıklaması (max 5000 chars)
            tags: Etiketler (max 500 chars total)
            category_id: YouTube category ID (28=Science & Tech, 24=Entertainment)
            privacy_status: public, private, unlisted
            thumbnail_path: Thumbnail görseli (opsiyonel)
            publish_at: Zamanlanmış yayın (opsiyonel, UTC timezone)

        Returns:
            Upload response dict veya None
        """
        if not self.youtube:
            logger.error("❌ YouTube API not authenticated")
            return None

        if not Path(video_path).exists():
            logger.error(f"❌ Video file not found: {video_path}")
            return None

        try:
            logger.info(f"📤 Uploading video: {Path(video_path).name}")
            logger.info(f"   Title: {title}")
            logger.info(f"   Privacy: {privacy_status}")

            # Truncate title/description to YouTube limits
            title = title[:100]
            description = description[:5000]

            # Truncate tags
            if tags:
                tags = tags[:500]  # YouTube max 500 chars total

            # Build request body
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags or [],
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'selfDeclaredMadeForKids': False
                }
            }

            # Add scheduled publish time if specified
            if publish_at:
                body['status']['publishAt'] = publish_at.isoformat() + 'Z'
                body['status']['privacyStatus'] = 'private'  # Must be private for scheduling

            # Create media upload
            media = MediaFileUpload(
                video_path,
                mimetype='video/*',
                resumable=True,
                chunksize=1024*1024  # 1MB chunks
            )

            # Execute upload
            logger.info("⬆️ Uploading video (this may take a while)...")

            request = self.youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"   Upload progress: {progress}%")

            video_id = response['id']
            logger.info(f"✅ Video uploaded! ID: {video_id}")

            # Upload thumbnail if provided
            if thumbnail_path and Path(thumbnail_path).exists():
                logger.info(f"🖼️ Uploading thumbnail...")
                self.set_thumbnail(video_id, thumbnail_path)

            # Return upload info
            upload_info = {
                'video_id': video_id,
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'title': title,
                'privacy_status': privacy_status,
                'uploaded_at': datetime.now().isoformat()
            }

            logger.info(f"✅ Upload complete!")
            logger.info(f"   URL: {upload_info['url']}")

            return upload_info

        except HttpError as e:
            logger.error(f"❌ YouTube API error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Upload failed: {e}")
            return None

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """
        Video thumbnail'ini ayarla

        Args:
            video_id: YouTube video ID
            thumbnail_path: Thumbnail görsel dosyası

        Returns:
            Başarılı ise True
        """
        if not self.youtube:
            logger.error("❌ YouTube API not authenticated")
            return False

        try:
            logger.info(f"🖼️ Setting thumbnail for video: {video_id}")

            self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()

            logger.info("✅ Thumbnail set successfully")
            return True

        except HttpError as e:
            logger.error(f"❌ Thumbnail upload failed: {e}")
            return False

    def update_video(self,
                    video_id: str,
                    title: Optional[str] = None,
                    description: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    privacy_status: Optional[str] = None) -> bool:
        """
        Yüklenmiş video bilgilerini güncelle

        Args:
            video_id: YouTube video ID
            title: Yeni başlık
            description: Yeni açıklama
            tags: Yeni etiketler
            privacy_status: Yeni privacy durumu

        Returns:
            Başarılı ise True
        """
        if not self.youtube:
            logger.error("❌ YouTube API not authenticated")
            return False

        try:
            logger.info(f"📝 Updating video: {video_id}")

            # Get current video data
            video = self.youtube.videos().list(
                part='snippet,status',
                id=video_id
            ).execute()

            if not video['items']:
                logger.error(f"❌ Video not found: {video_id}")
                return False

            current = video['items'][0]

            # Update fields
            if title:
                current['snippet']['title'] = title[:100]
            if description:
                current['snippet']['description'] = description[:5000]
            if tags:
                current['snippet']['tags'] = tags[:500]
            if privacy_status:
                current['status']['privacyStatus'] = privacy_status

            # Execute update
            self.youtube.videos().update(
                part='snippet,status',
                body=current
            ).execute()

            logger.info("✅ Video updated successfully")
            return True

        except HttpError as e:
            logger.error(f"❌ Update failed: {e}")
            return False

    def delete_video(self, video_id: str) -> bool:
        """
        Video'yu sil

        Args:
            video_id: YouTube video ID

        Returns:
            Başarılı ise True
        """
        if not self.youtube:
            logger.error("❌ YouTube API not authenticated")
            return False

        try:
            logger.info(f"🗑️ Deleting video: {video_id}")

            self.youtube.videos().delete(id=video_id).execute()

            logger.info("✅ Video deleted successfully")
            return True

        except HttpError as e:
            logger.error(f"❌ Delete failed: {e}")
            return False

    def get_my_videos(self, max_results: int = 10) -> List[Dict]:
        """
        Kanalımdaki videoları listele

        Args:
            max_results: Maksimum sonuç sayısı

        Returns:
            Video listesi
        """
        if not self.youtube:
            logger.error("❌ YouTube API not authenticated")
            return []

        try:
            logger.info(f"📋 Fetching my videos (max {max_results})...")

            # Get channel ID
            channels_response = self.youtube.channels().list(
                part='contentDetails',
                mine=True
            ).execute()

            if not channels_response['items']:
                logger.warning("⚠️ No channel found")
                return []

            channel_id = channels_response['items'][0]['id']
            uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

            # Get videos from uploads playlist
            playlist_response = self.youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=max_results
            ).execute()

            videos = []
            for item in playlist_response.get('items', []):
                video_info = {
                    'video_id': item['snippet']['resourceId']['videoId'],
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description'],
                    'published_at': item['snippet']['publishedAt'],
                    'thumbnail_url': item['snippet']['thumbnails']['default']['url']
                }
                videos.append(video_info)

            logger.info(f"✅ Found {len(videos)} videos")
            return videos

        except HttpError as e:
            logger.error(f"❌ Failed to fetch videos: {e}")
            return []

    def get_upload_quota_usage(self) -> Dict:
        """
        YouTube API quota kullanımı bilgisi

        Returns:
            Quota bilgileri
        """
        return {
            'daily_limit': 10000,  # YouTube default daily quota
            'upload_cost': 1600,   # Video upload cost in quota
            'max_daily_uploads': 6,  # 10000 / 1600 = 6.25
            'note': 'Check actual usage at: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas'
        }


# Test
if __name__ == "__main__":
    import sys

    # Set UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*60)
    print("📺 YOUTUBE UPLOADER TEST")
    print("="*60)

    # Check if client_secrets.json exists
    client_secrets = Path("client_secrets.json")

    if not client_secrets.exists():
        print("\n❌ client_secrets.json NOT FOUND")
        print("\n📋 Setup Instructions:")
        print("   1. Go to: https://console.cloud.google.com/")
        print("   2. Select project: kozmik oda")
        print("   3. APIs & Services > Credentials")
        print("   4. Create OAuth 2.0 Client ID")
        print("      - Application type: Desktop app")
        print("      - Name: VIDEOCU v1")
        print("   5. Download JSON and save as 'client_secrets.json'")
        print("\n⚠️ Cannot test upload without credentials")
        sys.exit(1)

    print("✅ client_secrets.json found")

    # Initialize uploader (will trigger OAuth flow if needed)
    print("\n🔐 Initializing YouTube uploader...")
    print("   A browser window will open for OAuth authorization")
    print("   Authorize the app to upload videos to your channel")

    uploader = YouTubeUploader()

    if not uploader.youtube:
        print("❌ YouTube API initialization failed")
        sys.exit(1)

    print("✅ YouTube API ready")

    # Show quota info
    print("\n📊 YouTube API Quota Info:")
    quota = uploader.get_upload_quota_usage()
    print(f"   Daily Limit: {quota['daily_limit']:,} units")
    print(f"   Upload Cost: {quota['upload_cost']:,} units")
    print(f"   Max Daily Uploads: ~{quota['max_daily_uploads']} videos")

    # List my videos
    print("\n📋 Your Recent Videos:")
    videos = uploader.get_my_videos(max_results=5)

    if videos:
        for i, video in enumerate(videos, 1):
            print(f"\n   {i}. {video['title'][:60]}")
            print(f"      ID: {video['video_id']}")
            print(f"      Published: {video['published_at']}")
    else:
        print("   No videos found (or first time using this account)")

    print("\n" + "="*60)
    print("✅ YOUTUBE UPLOADER TEST COMPLETE")
    print("="*60)

    print("\n💡 Ready to upload videos!")
    print("   Use: uploader.upload_video()")
    print("   Example:")
    print('   uploader.upload_video(')
    print('       video_path="video.mp4",')
    print('       title="My Video Title",')
    print('       description="Description...",')
    print('       tags=["ai", "tech"],')
    print('       privacy_status="public"')
    print('   )')
