"""
VIDEOCU v1 - Database Management
SQLite veritabanı yönetimi
"""

import sqlite3
from datetime import datetime
from pathlib import Path
import json
from typing import Optional, List, Dict, Any
import config


class Database:
    """SQLite database manager"""

    def __init__(self, db_path: Path = config.DATABASE_PATH):
        self.db_path = db_path
        self.conn = None
        self.init_database()

    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def init_database(self):
        """Initialize database schema"""
        conn = self.connect()
        cursor = conn.cursor()

        # Trends table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            region TEXT DEFAULT 'DE',
            score REAL DEFAULT 0.0,
            views INTEGER DEFAULT 0,
            category TEXT,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
        """)

        # Videos table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trend_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            script_path TEXT,
            voice_path TEXT,
            video_path TEXT,
            youtube_url TEXT,
            youtube_video_id TEXT,
            status TEXT DEFAULT 'draft',
            duration_seconds INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP,
            metadata TEXT,
            FOREIGN KEY (trend_id) REFERENCES trends(id)
        )
        """)

        # Jobs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            input_data TEXT,
            output_data TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
        """)

        # Settings table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()
        self.close()

    # Trends methods
    def insert_trend(self, keyword: str, region: str = "DE", score: float = 0.0,
                     views: int = 0, category: str = None, metadata: dict = None):
        """Insert new trend"""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO trends (keyword, region, score, views, category, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (keyword, region, score, views, category, json.dumps(metadata) if metadata else None))

        trend_id = cursor.lastrowid
        conn.commit()
        self.close()
        return trend_id

    def get_trends(self, region: str = "DE", limit: int = 10) -> List[Dict]:
        """Get recent trends"""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT * FROM trends
        WHERE region = ?
        ORDER BY discovered_at DESC
        LIMIT ?
        """, (region, limit))

        trends = [dict(row) for row in cursor.fetchall()]
        self.close()
        return trends

    # Videos methods
    def insert_video(self, trend_id: int, title: str, description: str = None,
                     script_path: str = None, voice_path: str = None,
                     video_path: str = None, metadata: dict = None):
        """Insert new video"""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO videos (trend_id, title, description, script_path,
                          voice_path, video_path, metadata, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
        """, (trend_id, title, description, script_path, voice_path,
              video_path, json.dumps(metadata) if metadata else None))

        video_id = cursor.lastrowid
        conn.commit()
        self.close()
        return video_id

    def update_video(self, video_id: int, **kwargs):
        """Update video fields"""
        conn = self.connect()
        cursor = conn.cursor()

        # Build UPDATE query dynamically
        fields = []
        values = []
        for key, value in kwargs.items():
            if value is not None:
                fields.append(f"{key} = ?")
                values.append(value)

        if fields:
            values.append(video_id)
            query = f"UPDATE videos SET {', '.join(fields)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()

        self.close()

    def get_videos(self, limit: int = 10) -> List[Dict]:
        """Get recent videos"""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT v.*, t.keyword as trend_keyword
        FROM videos v
        LEFT JOIN trends t ON v.trend_id = t.id
        ORDER BY v.created_at DESC
        LIMIT ?
        """, (limit,))

        videos = [dict(row) for row in cursor.fetchall()]
        self.close()
        return videos

    # Jobs methods
    def insert_job(self, job_type: str, input_data: dict = None):
        """Insert new job"""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO jobs (job_type, input_data, status)
        VALUES (?, ?, 'pending')
        """, (job_type, json.dumps(input_data) if input_data else None))

        job_id = cursor.lastrowid
        conn.commit()
        self.close()
        return job_id

    def update_job(self, job_id: int, status: str, output_data: dict = None,
                   error_message: str = None):
        """Update job status"""
        conn = self.connect()
        cursor = conn.cursor()

        timestamp_field = "started_at" if status == "in_progress" else "completed_at"

        cursor.execute(f"""
        UPDATE jobs
        SET status = ?, output_data = ?, error_message = ?, {timestamp_field} = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (status, json.dumps(output_data) if output_data else None,
              error_message, job_id))

        conn.commit()
        self.close()

    # Settings methods
    def set_setting(self, key: str, value: str):
        """Set or update setting"""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, value))

        conn.commit()
        self.close()

    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Get setting value"""
        conn = self.connect()
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        self.close()

        return row['value'] if row else default

    # Statistics
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        conn = self.connect()
        cursor = conn.cursor()

        stats = {}

        # Total trends
        cursor.execute("SELECT COUNT(*) as count FROM trends")
        stats['total_trends'] = cursor.fetchone()['count']

        # Total videos
        cursor.execute("SELECT COUNT(*) as count FROM videos")
        stats['total_videos'] = cursor.fetchone()['count']

        # Published videos
        cursor.execute("SELECT COUNT(*) as count FROM videos WHERE youtube_video_id IS NOT NULL")
        stats['published_videos'] = cursor.fetchone()['count']

        # Jobs by status
        cursor.execute("SELECT status, COUNT(*) as count FROM jobs GROUP BY status")
        stats['jobs'] = {row['status']: row['count'] for row in cursor.fetchall()}

        self.close()
        return stats


if __name__ == "__main__":
    # Test database
    db = Database()
    print("✅ Database initialized")
    print(f"📊 Statistics: {db.get_statistics()}")
