"""
VIDEOCU v1 - Server Administrator Agent
System management and monitoring specialist

Features:
- System health monitoring
- Resource usage tracking
- Log management
- Backup/restore operations
- Performance optimization
"""

import logging
import os
import psutil
import shutil
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ServerAdministratorAgent:
    """
    Server administration specialist agent

    Responsibilities:
    - Monitor system health (CPU, RAM, disk)
    - Track resource usage
    - Manage logs and cleanup
    - Perform backups
    - Optimize performance
    """

    def __init__(self, skill_library=None, output_dir: str = "output"):
        """
        Initialize Server Administrator Agent

        Args:
            skill_library: SkillLibrary instance
            output_dir: Output directory path
        """
        self.skill_library = skill_library
        self.output_dir = Path(output_dir)
        self.agent_type = "server_administrator"

        # Thresholds
        self.cpu_warning_threshold = 80.0  # %
        self.memory_warning_threshold = 80.0  # %
        self.disk_warning_threshold = 90.0  # %

        logger.info("🖥️ Server Administrator Agent initialized")

    def execute_task(self, task: Dict) -> Dict:
        """
        Execute server administration task

        Args:
            task: Task from Chef AI

        Returns:
            Execution result
        """
        try:
            analysis = task['analysis']
            parameters = analysis.get('parameters', {})
            task_type = parameters.get('admin_task', 'health_check')

            logger.info(f"🖥️ Server Admin Agent executing: {task_type}")

            # Route to appropriate handler
            if task_type == 'health_check':
                return self._health_check()
            elif task_type == 'resource_monitor':
                return self._monitor_resources()
            elif task_type == 'cleanup':
                return self._cleanup_old_files(parameters)
            elif task_type == 'backup':
                return self._create_backup(parameters)
            elif task_type == 'log_analysis':
                return self._analyze_logs(parameters)
            else:
                return self._health_check()  # Default

        except Exception as e:
            logger.error(f"❌ Server Admin Agent failed: {e}")
            return {'success': False, 'error': str(e)}

    def _health_check(self) -> Dict:
        """
        Comprehensive system health check

        Returns:
            Health status dict
        """
        logger.info("   🏥 Running health check...")

        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_status = 'healthy' if cpu_percent < self.cpu_warning_threshold else 'warning'

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_status = 'healthy' if memory_percent < self.memory_warning_threshold else 'warning'

            # Disk usage
            disk = psutil.disk_usage(str(self.output_dir.parent))
            disk_percent = disk.percent
            disk_status = 'healthy' if disk_percent < self.disk_warning_threshold else 'warning'

            # Process count
            process_count = len(psutil.pids())

            # Overall status
            overall_status = 'healthy'
            if any(status == 'warning' for status in [cpu_status, memory_status, disk_status]):
                overall_status = 'warning'

            health_report = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'overall_status': overall_status,
                'cpu': {
                    'usage_percent': cpu_percent,
                    'count': cpu_count,
                    'status': cpu_status
                },
                'memory': {
                    'total_gb': round(memory.total / (1024**3), 2),
                    'used_gb': round(memory.used / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2),
                    'percent': memory_percent,
                    'status': memory_status
                },
                'disk': {
                    'total_gb': round(disk.total / (1024**3), 2),
                    'used_gb': round(disk.used / (1024**3), 2),
                    'free_gb': round(disk.free / (1024**3), 2),
                    'percent': disk_percent,
                    'status': disk_status
                },
                'processes': {
                    'count': process_count
                }
            }

            logger.info(f"      ✅ Overall: {overall_status}")
            logger.info(f"      CPU: {cpu_percent}% ({cpu_status})")
            logger.info(f"      Memory: {memory_percent}% ({memory_status})")
            logger.info(f"      Disk: {disk_percent}% ({disk_status})")

            return health_report

        except Exception as e:
            logger.error(f"      ❌ Health check failed: {e}")
            return {'success': False, 'error': str(e)}

    def _monitor_resources(self) -> Dict:
        """
        Monitor resource usage over time

        Returns:
            Resource monitoring data
        """
        logger.info("   📊 Monitoring resources...")

        try:
            # Sample multiple times for better accuracy
            samples = 5
            interval = 0.5

            cpu_samples = []
            for _ in range(samples):
                cpu_samples.append(psutil.cpu_percent(interval=interval))

            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            max_cpu = max(cpu_samples)
            min_cpu = min(cpu_samples)

            # Memory
            memory = psutil.virtual_memory()

            # Disk I/O
            disk_io = psutil.disk_io_counters()

            # Network I/O
            net_io = psutil.net_io_counters()

            monitoring_data = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'average': round(avg_cpu, 2),
                    'max': round(max_cpu, 2),
                    'min': round(min_cpu, 2),
                    'samples': samples
                },
                'memory': {
                    'percent': memory.percent,
                    'used_gb': round(memory.used / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2)
                },
                'disk_io': {
                    'read_mb': round(disk_io.read_bytes / (1024**2), 2),
                    'write_mb': round(disk_io.write_bytes / (1024**2), 2),
                    'read_count': disk_io.read_count,
                    'write_count': disk_io.write_count
                },
                'network_io': {
                    'sent_mb': round(net_io.bytes_sent / (1024**2), 2),
                    'recv_mb': round(net_io.bytes_recv / (1024**2), 2),
                    'packets_sent': net_io.packets_sent,
                    'packets_recv': net_io.packets_recv
                }
            }

            logger.info(f"      ✅ CPU avg: {avg_cpu:.1f}%")
            logger.info(f"      Memory: {memory.percent:.1f}%")
            logger.info(f"      Disk I/O: {monitoring_data['disk_io']['read_mb']:.1f}MB read, "
                       f"{monitoring_data['disk_io']['write_mb']:.1f}MB write")

            return monitoring_data

        except Exception as e:
            logger.error(f"      ❌ Resource monitoring failed: {e}")
            return {'success': False, 'error': str(e)}

    def _cleanup_old_files(self, params: Dict) -> Dict:
        """
        Clean up old files to free disk space

        Args:
            params: Cleanup parameters (days_old, file_types)

        Returns:
            Cleanup result
        """
        logger.info("   🧹 Cleaning up old files...")

        try:
            days_old = params.get('days_old', 7)
            file_types = params.get('file_types', ['*.tmp', '*.log', '*.cache'])

            cutoff_time = datetime.now().timestamp() - (days_old * 86400)

            deleted_files = []
            freed_space = 0

            for pattern in file_types:
                for file_path in self.output_dir.rglob(pattern):
                    try:
                        if file_path.is_file():
                            # Check file age
                            file_time = file_path.stat().st_mtime
                            if file_time < cutoff_time:
                                file_size = file_path.stat().st_size
                                file_path.unlink()
                                deleted_files.append(str(file_path))
                                freed_space += file_size
                    except Exception as e:
                        logger.warning(f"      ⚠️ Failed to delete {file_path}: {e}")

            cleanup_result = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'deleted_count': len(deleted_files),
                'freed_space_mb': round(freed_space / (1024**2), 2),
                'days_old': days_old,
                'file_types': file_types
            }

            logger.info(f"      ✅ Deleted {len(deleted_files)} files")
            logger.info(f"      Freed {cleanup_result['freed_space_mb']} MB")

            return cleanup_result

        except Exception as e:
            logger.error(f"      ❌ Cleanup failed: {e}")
            return {'success': False, 'error': str(e)}

    def _create_backup(self, params: Dict) -> Dict:
        """
        Create backup of important files

        Args:
            params: Backup parameters (backup_dir, include_db)

        Returns:
            Backup result
        """
        logger.info("   💾 Creating backup...")

        try:
            backup_dir = Path(params.get('backup_dir', 'backups'))
            backup_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"videocu_backup_{timestamp}"
            backup_path = backup_dir / backup_name

            # Create backup directory
            backup_path.mkdir(parents=True, exist_ok=True)

            backed_up_items = []
            total_size = 0

            # Backup agent memory database
            if params.get('include_db', True):
                db_path = Path('output/agent_memory.db')
                if db_path.exists():
                    dest = backup_path / 'agent_memory.db'
                    shutil.copy2(db_path, dest)
                    backed_up_items.append('agent_memory.db')
                    total_size += dest.stat().st_size

            # Backup skill library
            skill_lib_path = Path('output/skill_library.json')
            if skill_lib_path.exists():
                dest = backup_path / 'skill_library.json'
                shutil.copy2(skill_lib_path, dest)
                backed_up_items.append('skill_library.json')
                total_size += dest.stat().st_size

            # Backup configuration
            config_files = ['.env', 'config.json']
            for config_file in config_files:
                config_path = Path(config_file)
                if config_path.exists():
                    dest = backup_path / config_file
                    shutil.copy2(config_path, dest)
                    backed_up_items.append(config_file)
                    total_size += dest.stat().st_size

            backup_result = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'backup_path': str(backup_path),
                'backup_name': backup_name,
                'backed_up_items': backed_up_items,
                'total_size_mb': round(total_size / (1024**2), 2)
            }

            logger.info(f"      ✅ Backup created: {backup_name}")
            logger.info(f"      Items: {len(backed_up_items)}")
            logger.info(f"      Size: {backup_result['total_size_mb']} MB")

            return backup_result

        except Exception as e:
            logger.error(f"      ❌ Backup failed: {e}")
            return {'success': False, 'error': str(e)}

    def _analyze_logs(self, params: Dict) -> Dict:
        """
        Analyze log files for errors and warnings

        Args:
            params: Log analysis parameters (log_dir, log_level)

        Returns:
            Log analysis result
        """
        logger.info("   📋 Analyzing logs...")

        try:
            log_dir = Path(params.get('log_dir', 'output'))
            log_pattern = params.get('log_pattern', '*.log')

            error_count = 0
            warning_count = 0
            info_count = 0

            error_samples = []
            warning_samples = []

            for log_file in log_dir.rglob(log_pattern):
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            line_lower = line.lower()

                            if 'error' in line_lower or 'failed' in line_lower:
                                error_count += 1
                                if len(error_samples) < 5:
                                    error_samples.append(line.strip()[:200])

                            elif 'warning' in line_lower or 'warn' in line_lower:
                                warning_count += 1
                                if len(warning_samples) < 5:
                                    warning_samples.append(line.strip()[:200])

                            elif 'info' in line_lower:
                                info_count += 1

                except Exception as e:
                    logger.warning(f"      ⚠️ Failed to read {log_file}: {e}")

            analysis_result = {
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'error_count': error_count,
                'warning_count': warning_count,
                'info_count': info_count,
                'error_samples': error_samples,
                'warning_samples': warning_samples,
                'status': 'healthy' if error_count == 0 else 'needs_attention'
            }

            logger.info(f"      ✅ Errors: {error_count}")
            logger.info(f"      Warnings: {warning_count}")
            logger.info(f"      Info: {info_count}")

            return analysis_result

        except Exception as e:
            logger.error(f"      ❌ Log analysis failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_system_info(self) -> Dict:
        """Get comprehensive system information"""
        try:
            return {
                'platform': os.name,
                'cpu_count': psutil.cpu_count(),
                'memory_total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
                'disk_total_gb': round(psutil.disk_usage('/').total / (1024**3), 2),
                'python_version': os.sys.version.split()[0],
                'output_dir': str(self.output_dir)
            }
        except Exception as e:
            return {'error': str(e)}


# Test
if __name__ == "__main__":
    import sys

    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🖥️ SERVER ADMINISTRATOR AGENT TEST")
    print("="*70)

    agent = ServerAdministratorAgent()

    # Test 1: System Info
    print(f"\n💻 System Information:")
    sys_info = agent.get_system_info()
    for key, value in sys_info.items():
        print(f"   {key}: {value}")

    # Test 2: Health Check
    print(f"\n🏥 Health Check:")
    health = agent._health_check()
    if health['success']:
        print(f"   Overall: {health['overall_status']}")
        print(f"   CPU: {health['cpu']['usage_percent']}% ({health['cpu']['status']})")
        print(f"   Memory: {health['memory']['percent']}% ({health['memory']['status']})")
        print(f"   Disk: {health['disk']['percent']}% ({health['disk']['status']})")

    # Test 3: Resource Monitoring
    print(f"\n📊 Resource Monitoring:")
    resources = agent._monitor_resources()
    if resources['success']:
        print(f"   CPU: avg={resources['cpu']['average']}%, "
              f"max={resources['cpu']['max']}%, "
              f"min={resources['cpu']['min']}%")
        print(f"   Memory: {resources['memory']['percent']}%")
        print(f"   Network: {resources['network_io']['sent_mb']:.1f}MB sent, "
              f"{resources['network_io']['recv_mb']:.1f}MB received")

    print("\n" + "="*70)
    print("✅ SERVER ADMINISTRATOR AGENT TEST COMPLETE")
    print("="*70 + "\n")
