"""Process-local job dispatch using the same Redis list operations in both modes."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import fakeredis
import redis

from docagent.config import Settings


def create_redis_client(config: Settings):
    if config.redis_backend == "fake":
        # Explicit server isolates application lifetimes and never contacts REDIS_URL.
        return fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    return redis.Redis.from_url(
        config.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


class LocalJobQueue:
    """One API process owns the queue and threads. Durable workers use Celery."""

    def __init__(self, config: Settings, handler):
        self.client = create_redis_client(config)
        try:
            self.client.ping()
        except Exception:
            self.client.close()
            raise RuntimeError("Local queue unavailable; check Redis configuration") from None
        self.key = f"docagent:local:{uuid.uuid4()}"
        self.handler = handler
        self.executor = ThreadPoolExecutor(
            max_workers=config.max_concurrent_jobs, thread_name_prefix="docagent"
        )
        self.lock = threading.Lock()
        self.closed = False

    def enqueue(self, job_id):
        with self.lock:
            if self.closed:
                raise RuntimeError("Local queue is closed")
            self.client.rpush(self.key, job_id)
            return self.executor.submit(self._consume_one)

    def _consume_one(self):
        try:
            job_id = self.client.lpop(self.key)
            if job_id is not None:
                self.handler(job_id)
        except Exception:
            # Never log connection URLs, credentials or repository content.
            logging.getLogger(__name__).error("Local job dispatch failed; inspect job status before retrying")
            raise

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        # Finish accepted work before closing the shared client.
        self.executor.shutdown(wait=True)
        try:
            self.client.delete(self.key)
        finally:
            self.client.close()
