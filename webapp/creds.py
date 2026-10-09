"""Short-lived, in-memory store for per-browser-session Akamai credentials.

Credentials are never written to disk. The browser only ever holds a random
reference id (`cred_id`), kept in Flask's own session cookie -- which Flask
signs with HMAC (via itsdangerous) using SECRET_KEY, so it cannot be forged
or tampered with client-side. The actual credential values live only in this
process's memory, expire after a bounded TTL, and are dropped on restart.
"""
from __future__ import annotations

import threading
import time
import uuid

_TTL_SECONDS = 3600


class CredentialStore:
    def __init__(self, ttl_seconds: int = _TTL_SECONDS):
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[dict, float]] = {}

    def put(self, creds: dict) -> str:
        cred_id = uuid.uuid4().hex
        with self._lock:
            self._purge_expired_locked()
            self._entries[cred_id] = (creds, time.time() + self._ttl_seconds)
        return cred_id

    def get(self, cred_id: str | None) -> dict | None:
        if not cred_id:
            return None
        with self._lock:
            entry = self._entries.get(cred_id)
            if not entry:
                return None
            creds, expires_at = entry
            if time.time() > expires_at:
                del self._entries[cred_id]
                return None
            return creds

    def has(self, cred_id: str | None) -> bool:
        return self.get(cred_id) is not None

    def update(self, cred_id: str | None, updates: dict) -> bool:
        if not cred_id:
            return False
        with self._lock:
            entry = self._entries.get(cred_id)
            if not entry:
                return False
            creds, expires_at = entry
            if time.time() > expires_at:
                del self._entries[cred_id]
                return False
            self._entries[cred_id] = ({**creds, **updates}, time.time() + self._ttl_seconds)
            return True

    def clear(self, cred_id: str | None) -> None:
        if not cred_id:
            return
        with self._lock:
            self._entries.pop(cred_id, None)

    def _purge_expired_locked(self):
        now = time.time()
        expired = [cid for cid, (_, exp) in self._entries.items() if exp < now]
        for cid in expired:
            del self._entries[cid]
