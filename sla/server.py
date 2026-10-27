"""Сборка веб-сервиса: настройки, подключение к MySQL на каждый запрос, приложение.
Запуск: uvicorn sla.server:app --host 0.0.0.0 --port 8000"""
import logging

from .api import create_app
from .repository import MysqlRepository, connect_mysql
from .settings import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
settings = Settings.from_env()


def get_repo():
    conn = connect_mysql(settings, attempts=5, pause=1.0)
    try:
        yield MysqlRepository(conn)
    finally:
        conn.close()


app = create_app(get_repo, settings)
