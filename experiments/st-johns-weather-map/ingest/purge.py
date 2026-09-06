"""Drain retention work without acknowledging failed object deletes."""
from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


def queue_objects(cursor: Any, keys: list[str]) -> None:
    """Queue keys in the transaction that removes their metadata."""
    for key in keys:
        cursor.execute(
            "INSERT INTO weather_experiment.purged_objects (object_key, reason) "
            "VALUES (%s, 'object_delete_retry') ON CONFLICT (object_key) DO NOTHING",
            (key,),
        )


def drain_objects(store: Any, *, batch: int = 1000) -> tuple[int, int]:
    """Keep the claim transaction open until deletes finish or failures requeue.

    A crash rolls the claim back. Successful deletes replay safely if committing
    fails: deleting an absent S3 key is idempotent. Network failures never prove
    that bytes are absent.
    """
    deleted = failed = 0
    with store.connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT weather_experiment.claim_purged_objects(%s)", (batch,))
        keys = [row[0] for row in cursor.fetchall()]
        for key in keys:
            try:
                store.s3.delete_object(Bucket=store.config.bucket, Key=key)
            except Exception:
                queue_objects(cursor, [key])
                LOGGER.warning("object deletion failed; retained retry for %s", key)
                failed += 1
            else:
                deleted += 1
    return deleted, failed
