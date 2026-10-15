import psycopg
from psycopg.rows import dict_row

from app.config import Settings


def connect(settings: Settings) -> psycopg.Connection:
    return psycopg.connect(
        settings.database_url.get_secret_value(),
        autocommit=True,
        row_factory=dict_row,
        connect_timeout=settings.database_timeout,
    )
