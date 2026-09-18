"""
VIDEOCU v1 - Centralized Logging System
Tüm modüller için merkezi log yönetimi
"""

import logging
import os
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
import json

# Base directory
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "output" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Log files
MAIN_LOG = LOG_DIR / "videocu.log"
ERROR_LOG = LOG_DIR / "errors.log"
ACTIVITY_LOG = LOG_DIR / "activity.log"


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Modül için logger oluştur

    Args:
        name: Logger adı (genellikle __name__)
        level: Log seviyesi

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Eğer handler zaten varsa ekleme
    if logger.handlers:
        return logger

    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler - Main log (rotating, max 10MB, keep 5 backups)
    file_handler = RotatingFileHandler(
        MAIN_LOG,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Error File Handler - Only errors
    error_handler = RotatingFileHandler(
        ERROR_LOG,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


def log_activity(action: str, details: dict = None, status: str = "info"):
    """
    Kullanıcı aktivitelerini logla

    Args:
        action: Yapılan işlem
        details: Ek detaylar
        status: info, success, warning, error
    """
    activity = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "status": status,
        "details": details or {}
    }

    try:
        # Mevcut logları oku
        activities = []
        if ACTIVITY_LOG.exists():
            with open(ACTIVITY_LOG, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    activities = json.loads(content)

        # Yeni aktiviteyi ekle
        activities.append(activity)

        # Son 1000 aktiviteyi tut
        activities = activities[-1000:]

        # Kaydet
        with open(ACTIVITY_LOG, 'w', encoding='utf-8') as f:
            json.dump(activities, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"Activity log error: {e}")


def get_recent_activities(limit: int = 50) -> list:
    """Son aktiviteleri getir"""
    try:
        if ACTIVITY_LOG.exists():
            with open(ACTIVITY_LOG, 'r', encoding='utf-8') as f:
                activities = json.loads(f.read())
                return activities[-limit:][::-1]  # En son ilk
    except Exception:
        pass
    return []


def get_recent_errors(limit: int = 20) -> list:
    """Son hataları getir"""
    errors = []
    try:
        if ERROR_LOG.exists():
            with open(ERROR_LOG, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-limit*5:]  # Her hata birkaç satır olabilir

            current_error = []
            for line in lines:
                if line.startswith('20'):  # Timestamp ile başlıyorsa yeni hata
                    if current_error:
                        errors.append(''.join(current_error))
                    current_error = [line]
                else:
                    current_error.append(line)

            if current_error:
                errors.append(''.join(current_error))

            return errors[-limit:][::-1]
    except Exception:
        pass
    return []


def clear_old_logs(days: int = 30):
    """Eski log dosyalarını temizle"""
    import glob
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(days=days)

    for pattern in ['*.log.*', '*.log']:
        for log_file in glob.glob(str(LOG_DIR / pattern)):
            try:
                file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
                if file_time < cutoff:
                    os.remove(log_file)
                    print(f"Removed old log: {log_file}")
            except Exception:
                pass


# Global logger for quick access
main_logger = setup_logger("videocu")


# Convenience functions
def info(msg: str):
    main_logger.info(msg)


def warning(msg: str):
    main_logger.warning(msg)


def error(msg: str):
    main_logger.error(msg)


def debug(msg: str):
    main_logger.debug(msg)


# Test
if __name__ == "__main__":
    # Test logging
    logger = setup_logger("test_module")

    logger.info("This is an info message")
    logger.warning("This is a warning")
    logger.error("This is an error")

    # Test activity logging
    log_activity("test_action", {"key": "value"}, "success")
    log_activity("another_action", {"url": "https://example.com"}, "info")

    print("\nRecent activities:")
    for act in get_recent_activities(5):
        print(f"  {act['timestamp']} - {act['action']} ({act['status']})")

    print(f"\nLog files created in: {LOG_DIR}")
