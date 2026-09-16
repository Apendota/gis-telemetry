import os
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

_pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)


@contextmanager
def get_connection():
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
