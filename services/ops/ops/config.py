import os
from pathlib import Path


def _load_dotenv() -> None:
    """Переменные из .env рядом с сервисом; уже заданные в окружении не перетираются."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

DATABASE_URL = os.environ.get("OPS_DATABASE_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
OPS_API_KEY = os.environ.get("OPS_API_KEY", "")
EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", "exports"))
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "")
SITE_URL = os.environ.get("SITE_URL", "https://tmgoods.ru").rstrip("/")
KAFKA_BROKERS = os.environ.get("KAFKA_BROKERS", "")
CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "")
