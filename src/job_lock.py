"""
Cross-process job locks backed by Postgres advisory locks.

The API (POST /sync, POST /analyze) and the scheduler container can both start
the same job. An advisory lock makes sure only one instance runs at a time,
whichever process it is in. The lock is tied to a dedicated connection, so
Postgres releases it automatically if the holder crashes or is killed.
"""

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg2

logger = logging.getLogger(__name__)

# Arbitrary, fixed keys identifying each job
SYNC_LOCK_KEY = 7_204_001
ANALYSIS_LOCK_KEY = 7_204_002


@contextmanager
def job_lock(database_url: str, key: int) -> Iterator[bool]:
    """
    Try to take the advisory lock `key` for the duration of the block.

    Yields True if the lock was acquired, False if another process holds it.
    Never blocks.
    """
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (key,))
            acquired = cur.fetchone()[0]
        yield acquired
    finally:
        # Closing the session releases the lock
        conn.close()
