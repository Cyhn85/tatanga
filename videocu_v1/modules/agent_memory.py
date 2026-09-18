"""
VIDEOCU v1 - Agent Memory System
Learning from production metrics for continuous improvement

Supports both SQLite (development) and PostgreSQL (production)
"""

import logging
import sqlite3
import os
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Long-term learning system for AI agents

    Stores:
    - Task execution history
    - Performance metrics (views, CTR, engagement)
    - Performance logs (publication → analytics pipeline)
    - Master prompt rules (learned strategies)
    - Success/failure patterns
    - Best practices discovered

    Database Support:
    - SQLite: Development/testing (default)
    - PostgreSQL: Production (set POSTGRES_URL env var)
    """

    def __init__(self, db_path: str = "output/agent_memory.db", use_postgres: bool = None):
        """
        Initialize memory system

        Args:
            db_path: SQLite database path (used if not using PostgreSQL)
            use_postgres: Force PostgreSQL usage (auto-detects from env if None)
        """
        # Auto-detect database type
        postgres_url = os.getenv('POSTGRES_URL')
        self.use_postgres = use_postgres if use_postgres is not None else bool(postgres_url)

        if self.use_postgres:
            try:
                import psycopg2
                self.conn = psycopg2.connect(postgres_url)
                logger.info("🧠 Agent Memory initialized (PostgreSQL)")
            except ImportError:
                logger.warning("⚠️ psycopg2 not installed, falling back to SQLite")
                self.use_postgres = False
            except Exception as e:
                logger.error(f"❌ PostgreSQL connection failed: {e}, using SQLite")
                self.use_postgres = False

        if not self.use_postgres:
            self.db_path = db_path
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(db_path)
            logger.info("🧠 Agent Memory initialized (SQLite)")

        self._init_database()

    def _init_database(self):
        """Create database schema"""
        cursor = self.conn.cursor()

        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT,
                platform TEXT,
                created_at TEXT,
                status TEXT,
                parameters TEXT
            )
        """)

        # Metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                platform TEXT,
                views INTEGER,
                likes INTEGER,
                ctr REAL,
                avg_watch_time REAL,
                engagement_rate REAL,
                collected_at TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        """)

        # Migration: Add engagement_rate column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE metrics ADD COLUMN engagement_rate REAL DEFAULT 0.0")
            logger.info("   ✅ Added engagement_rate column to metrics table")
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # Best practices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS best_practices (
                practice_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                platform TEXT,
                pattern TEXT,
                success_rate REAL,
                sample_size INTEGER,
                discovered_at TEXT
            )
        """)

        # Performance logs table (for Self-Improvement Engine)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE NOT NULL,
                platform TEXT NOT NULL,
                topic TEXT,
                status TEXT DEFAULT 'AWAITING_ANALYTICS',
                publish_time REAL,
                initial_data TEXT,
                analytics TEXT,
                last_updated REAL,
                UNIQUE(video_id, platform)
            )
        """)

        # Master prompt rules table (learned strategies)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_prompt_rules (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                rules_content TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                performance_data TEXT,
                created_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)

        # Music projects table (for Composer Agent)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS music_projects (
                project_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                project_name TEXT,
                status TEXT DEFAULT 'draft',
                style TEXT DEFAULT 'pop',
                bpm INTEGER,
                key_signature TEXT,
                created_at TEXT,
                updated_at TEXT,
                final_audio_path TEXT
            )
        """)

        # Audio inputs table (multiple inputs per project)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_inputs (
                input_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                input_type TEXT DEFAULT 'melody',
                audio_path TEXT,
                midi_path TEXT,
                start_time REAL DEFAULT 0.0,
                end_time REAL,
                layer_name TEXT,
                loop_enabled INTEGER DEFAULT 0,
                volume REAL DEFAULT 1.0,
                added_at TEXT,
                processed INTEGER DEFAULT 0,
                FOREIGN KEY (project_id) REFERENCES music_projects(project_id)
            )
        """)

        self.conn.commit()

    def record_task(self, task: Dict):
        """Record task execution"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?, ?, ?)
        """, (
            task['task_id'],
            task['analysis']['task_type'],
            task['analysis'].get('platform', 'unknown'),
            task['created_at'],
            task['status'],
            json.dumps(task['analysis'].get('parameters', {}))
        ))
        self.conn.commit()
        logger.info(f"   💾 Recorded task: {task['task_id']}")

    def record_metrics(self, task_id: str, platform: str, metrics: Dict):
        """Record performance metrics"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO metrics (task_id, platform, views, likes, ctr, avg_watch_time, engagement_rate, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            platform,
            metrics.get('views', 0),
            metrics.get('likes', 0),
            metrics.get('ctr', 0.0),
            metrics.get('avg_watch_time', 0.0),
            metrics.get('engagement_rate', 0.0),
            datetime.now().isoformat()
        ))
        self.conn.commit()
        logger.info(f"   📊 Recorded metrics for: {task_id}")

    def query_best_practices(self, task_type: str, platform: Optional[str] = None) -> List[Dict]:
        """Query top-performing strategies"""
        cursor = self.conn.cursor()

        if platform:
            cursor.execute("""
                SELECT t.parameters, AVG(m.views) as avg_views, COUNT(*) as count
                FROM tasks t
                JOIN metrics m ON t.task_id = m.task_id
                WHERE t.task_type = ? AND t.platform = ?
                GROUP BY t.parameters
                ORDER BY avg_views DESC
                LIMIT 5
            """, (task_type, platform))
        else:
            cursor.execute("""
                SELECT t.parameters, AVG(m.views) as avg_views, COUNT(*) as count
                FROM tasks t
                JOIN metrics m ON t.task_id = m.task_id
                WHERE t.task_type = ?
                GROUP BY t.parameters
                ORDER BY avg_views DESC
                LIMIT 5
            """, (task_type,))

        results = []
        for row in cursor.fetchall():
            results.append({
                'parameters': json.loads(row[0]),
                'avg_views': row[1],
                'sample_size': row[2]
            })

        return results

    def get_stats(self) -> Dict:
        """Get memory statistics"""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
        completed_tasks = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM metrics")
        total_metrics = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM best_practices")
        best_practices_count = cursor.fetchone()[0]

        return {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'total_metrics': total_metrics,
            'best_practices_count': best_practices_count
        }

    def add_performance_log(self, log_entry: Dict) -> bool:
        """
        Add a performance log entry (called after video publication)

        Args:
            log_entry: Dictionary containing video_id, platform, topic, initial_data, etc.

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO performance_logs
                (video_id, platform, topic, status, publish_time, initial_data, analytics)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                log_entry['video_id'],
                log_entry['platform'],
                log_entry.get('topic', ''),
                log_entry.get('status', 'AWAITING_ANALYTICS'),
                log_entry.get('publish_time', datetime.now().timestamp()),
                json.dumps(log_entry.get('initial_data', {})),
                json.dumps(log_entry.get('analytics', {}))
            ))
            self.conn.commit()
            logger.info(f"   📝 Performance log added: {log_entry['video_id']}")
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to add performance log: {e}")
            return False

    def update_performance_log(self, video_id: str, platform: str, update_data: Dict) -> bool:
        """
        Update a performance log with analytics data

        Args:
            video_id: Video identifier
            platform: Platform name
            update_data: Dictionary with analytics, status, last_update fields

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()

            # Build UPDATE query dynamically based on provided fields
            update_fields = []
            values = []

            if 'analytics' in update_data:
                update_fields.append("analytics = ?")
                values.append(json.dumps(update_data['analytics']))

            if 'status' in update_data:
                update_fields.append("status = ?")
                values.append(update_data['status'])

            if 'last_update' in update_data:
                update_fields.append("last_updated = ?")
                values.append(update_data['last_update'])
            else:
                update_fields.append("last_updated = ?")
                values.append(datetime.now().timestamp())

            # Add WHERE clause values
            values.extend([video_id, platform])

            query = f"""
                UPDATE performance_logs
                SET {', '.join(update_fields)}
                WHERE video_id = ? AND platform = ?
            """

            cursor.execute(query, values)
            self.conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"   ✅ Performance log updated: {video_id}")
                return True
            else:
                logger.warning(f"   ⚠️ No log found to update: {video_id}")
                return False

        except Exception as e:
            logger.error(f"   ❌ Failed to update performance log: {e}")
            return False

    def get_performance_logs(self, platform: Optional[str] = None,
                            status: Optional[str] = None,
                            limit: Optional[int] = None) -> List[Dict]:
        """
        Query performance logs

        Args:
            platform: Filter by platform (None = all platforms)
            status: Filter by status (e.g., 'AWAITING_ANALYTICS', 'ANALYSIS_COMPLETE')
            limit: Maximum number of results

        Returns:
            List of performance log dictionaries
        """
        try:
            cursor = self.conn.cursor()

            query = "SELECT * FROM performance_logs WHERE 1=1"
            params = []

            if platform:
                query += " AND platform = ?"
                params.append(platform)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY publish_time DESC"

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, params)

            logs = []
            columns = [desc[0] for desc in cursor.description]

            for row in cursor.fetchall():
                log = dict(zip(columns, row))
                # Parse JSON fields
                if log.get('initial_data'):
                    log['initial_data'] = json.loads(log['initial_data'])
                if log.get('analytics'):
                    log['analytics'] = json.loads(log['analytics'])
                logs.append(log)

            return logs

        except Exception as e:
            logger.error(f"   ❌ Failed to get performance logs: {e}")
            return []

    def update_master_prompt_rules(self, platform: str, new_rules: str,
                                   performance_data: Optional[Dict] = None) -> bool:
        """
        Update master prompt rules for a platform (called by Self-Improvement Engine)

        Args:
            platform: Target platform
            new_rules: New rule set content (text or JSON)
            performance_data: Optional performance metrics that led to this update

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()

            # Deactivate old rules
            cursor.execute("""
                UPDATE master_prompt_rules
                SET is_active = 0
                WHERE platform = ? AND is_active = 1
            """, (platform,))

            # Get current version number
            cursor.execute("""
                SELECT MAX(version) FROM master_prompt_rules WHERE platform = ?
            """, (platform,))
            result = cursor.fetchone()
            next_version = (result[0] or 0) + 1

            # Insert new rules
            cursor.execute("""
                INSERT INTO master_prompt_rules
                (platform, rules_content, version, performance_data, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                platform,
                new_rules,
                next_version,
                json.dumps(performance_data) if performance_data else None,
                datetime.now().isoformat()
            ))

            self.conn.commit()
            logger.info(f"   ✅ Master prompt rules updated: {platform} (v{next_version})")
            return True

        except Exception as e:
            logger.error(f"   ❌ Failed to update master prompt rules: {e}")
            return False

    def get_master_prompt_rules(self, platform: str) -> Optional[Dict]:
        """
        Get active master prompt rules for a platform

        Args:
            platform: Platform name

        Returns:
            Dictionary with rules_content, version, created_at or None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT rules_content, version, created_at, performance_data
                FROM master_prompt_rules
                WHERE platform = ? AND is_active = 1
                ORDER BY version DESC
                LIMIT 1
            """, (platform,))

            row = cursor.fetchone()
            if row:
                return {
                    'rules_content': row[0],
                    'version': row[1],
                    'created_at': row[2],
                    'performance_data': json.loads(row[3]) if row[3] else None
                }
            return None

        except Exception as e:
            logger.error(f"   ❌ Failed to get master prompt rules: {e}")
            return None

    # ========== Music Project Methods ==========

    def create_music_project(self, user_id: str, project_name: str,
                            style: str = 'pop', bpm: int = None,
                            key_signature: str = None) -> Optional[str]:
        """
        Create a new music project

        Args:
            user_id: Telegram user ID
            project_name: Project name
            style: Music style (jazz, pop, club, classical, ambient)
            bpm: Beats per minute (optional)
            key_signature: Musical key (optional)

        Returns:
            project_id if successful, None otherwise
        """
        try:
            import uuid
            project_id = f"MUS_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO music_projects
                (project_id, user_id, project_name, status, style, bpm, key_signature, created_at, updated_at)
                VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?)
            """, (
                project_id,
                user_id,
                project_name,
                style,
                bpm,
                key_signature,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            self.conn.commit()
            logger.info(f"   🎵 Music project created: {project_id} ({project_name})")
            return project_id

        except Exception as e:
            logger.error(f"   ❌ Failed to create music project: {e}")
            return None

    def add_audio_input(self, project_id: str, input_type: str, audio_path: str,
                       start_time: float = 0.0, end_time: float = None,
                       layer_name: str = None, loop_enabled: bool = False,
                       volume: float = 1.0) -> Optional[str]:
        """
        Add an audio input to a music project

        Args:
            project_id: Project ID
            input_type: Type of input (melody, rhythm, sample, background)
            audio_path: Path to audio file
            start_time: Start time in seconds
            end_time: End time in seconds (None = until end)
            layer_name: Optional layer name
            loop_enabled: Whether to loop this input
            volume: Volume multiplier (0.0 - 1.0)

        Returns:
            input_id if successful, None otherwise
        """
        try:
            import uuid
            input_id = f"INP_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"

            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO audio_inputs
                (input_id, project_id, input_type, audio_path, start_time, end_time,
                 layer_name, loop_enabled, volume, added_at, processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                input_id,
                project_id,
                input_type,
                audio_path,
                start_time,
                end_time,
                layer_name or input_type,
                1 if loop_enabled else 0,
                volume,
                datetime.now().isoformat()
            ))

            # Update project updated_at
            cursor.execute("""
                UPDATE music_projects SET updated_at = ? WHERE project_id = ?
            """, (datetime.now().isoformat(), project_id))

            self.conn.commit()
            logger.info(f"   🎤 Audio input added: {input_id} ({input_type})")
            return input_id

        except Exception as e:
            logger.error(f"   ❌ Failed to add audio input: {e}")
            return None

    def get_project_inputs(self, project_id: str) -> List[Dict]:
        """
        Get all audio inputs for a project

        Args:
            project_id: Project ID

        Returns:
            List of input dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT input_id, input_type, audio_path, midi_path, start_time, end_time,
                       layer_name, loop_enabled, volume, added_at, processed
                FROM audio_inputs
                WHERE project_id = ?
                ORDER BY start_time ASC
            """, (project_id,))

            inputs = []
            for row in cursor.fetchall():
                inputs.append({
                    'input_id': row[0],
                    'input_type': row[1],
                    'audio_path': row[2],
                    'midi_path': row[3],
                    'start_time': row[4],
                    'end_time': row[5],
                    'layer_name': row[6],
                    'loop_enabled': bool(row[7]),
                    'volume': row[8],
                    'added_at': row[9],
                    'processed': bool(row[10])
                })
            return inputs

        except Exception as e:
            logger.error(f"   ❌ Failed to get project inputs: {e}")
            return []

    def get_active_project(self, user_id: str) -> Optional[Dict]:
        """
        Get user's most recent active (draft/composing) project

        Args:
            user_id: Telegram user ID

        Returns:
            Project dictionary or None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT project_id, project_name, status, style, bpm, key_signature,
                       created_at, updated_at, final_audio_path
                FROM music_projects
                WHERE user_id = ? AND status IN ('draft', 'composing')
                ORDER BY updated_at DESC
                LIMIT 1
            """, (user_id,))

            row = cursor.fetchone()
            if row:
                return {
                    'project_id': row[0],
                    'project_name': row[1],
                    'status': row[2],
                    'style': row[3],
                    'bpm': row[4],
                    'key_signature': row[5],
                    'created_at': row[6],
                    'updated_at': row[7],
                    'final_audio_path': row[8]
                }
            return None

        except Exception as e:
            logger.error(f"   ❌ Failed to get active project: {e}")
            return None

    def get_music_project(self, project_id: str) -> Optional[Dict]:
        """
        Get a specific music project by ID

        Args:
            project_id: Project ID

        Returns:
            Project dictionary or None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT project_id, user_id, project_name, status, style, bpm, key_signature,
                       created_at, updated_at, final_audio_path
                FROM music_projects
                WHERE project_id = ?
            """, (project_id,))

            row = cursor.fetchone()
            if row:
                return {
                    'project_id': row[0],
                    'user_id': row[1],
                    'project_name': row[2],
                    'status': row[3],
                    'style': row[4],
                    'bpm': row[5],
                    'key_signature': row[6],
                    'created_at': row[7],
                    'updated_at': row[8],
                    'final_audio_path': row[9]
                }
            return None

        except Exception as e:
            logger.error(f"   ❌ Failed to get music project: {e}")
            return None

    def update_music_project(self, project_id: str, updates: Dict) -> bool:
        """
        Update a music project

        Args:
            project_id: Project ID
            updates: Dictionary with fields to update (status, style, final_audio_path, etc.)

        Returns:
            True if successful, False otherwise
        """
        try:
            allowed_fields = ['status', 'style', 'bpm', 'key_signature', 'final_audio_path', 'project_name']
            update_fields = []
            values = []

            for field, value in updates.items():
                if field in allowed_fields:
                    update_fields.append(f"{field} = ?")
                    values.append(value)

            if not update_fields:
                return False

            # Always update updated_at
            update_fields.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            values.append(project_id)

            cursor = self.conn.cursor()
            cursor.execute(f"""
                UPDATE music_projects
                SET {', '.join(update_fields)}
                WHERE project_id = ?
            """, values)

            self.conn.commit()
            logger.info(f"   ✅ Music project updated: {project_id}")
            return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"   ❌ Failed to update music project: {e}")
            return False

    def update_audio_input(self, input_id: str, updates: Dict) -> bool:
        """
        Update an audio input

        Args:
            input_id: Input ID
            updates: Dictionary with fields to update (midi_path, processed, etc.)

        Returns:
            True if successful, False otherwise
        """
        try:
            allowed_fields = ['midi_path', 'processed', 'start_time', 'end_time', 'volume', 'loop_enabled']
            update_fields = []
            values = []

            for field, value in updates.items():
                if field in allowed_fields:
                    update_fields.append(f"{field} = ?")
                    if field == 'loop_enabled':
                        values.append(1 if value else 0)
                    elif field == 'processed':
                        values.append(1 if value else 0)
                    else:
                        values.append(value)

            if not update_fields:
                return False

            values.append(input_id)

            cursor = self.conn.cursor()
            cursor.execute(f"""
                UPDATE audio_inputs
                SET {', '.join(update_fields)}
                WHERE input_id = ?
            """, values)

            self.conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"   ❌ Failed to update audio input: {e}")
            return False

    def get_user_projects(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Get all projects for a user

        Args:
            user_id: Telegram user ID
            limit: Maximum number of projects to return

        Returns:
            List of project dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT project_id, project_name, status, style, created_at, updated_at, final_audio_path
                FROM music_projects
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (user_id, limit))

            projects = []
            for row in cursor.fetchall():
                projects.append({
                    'project_id': row[0],
                    'project_name': row[1],
                    'status': row[2],
                    'style': row[3],
                    'created_at': row[4],
                    'updated_at': row[5],
                    'final_audio_path': row[6]
                })
            return projects

        except Exception as e:
            logger.error(f"   ❌ Failed to get user projects: {e}")
            return []

    def close(self):
        """Close database connection"""
        self.conn.close()
