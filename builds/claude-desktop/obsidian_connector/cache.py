"""In-memory TTL cache for Obsidian CLI responses."""

from __future__ import annotations

import threading
import time

# Commands whose first arg starts with one of these prefixes are mutations.
# They bypass the cache and invalidate all entries.
_MUTATION_PREFIXES = ("daily:append", "create")


class CLICache:
    """Thread-safe in-memory TTL cache keyed by CLI invocation."""

    def __init__(self, ttl: int = 0) -> None:
        self.ttl = ttl
        self._store: dict[tuple, tuple[str, float]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.ttl > 0

    def is_mutation(self, args: list[str]) -> bool:
        if not args:
            return False
        return args[0].startswith(_MUTATION_PREFIXES)

    def get(self, args: list[str], vault: str | None) -> str | None:
        if not self.enabled:
            return None
        key = (tuple(args), vault)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            stdout, ts = entry
            if (time.monotonic() - ts) > self.ttl:
                del self._store[key]
                return None
            return stdout

    def put(self, args: list[str], vault: str | None, stdout: str) -> None:
        if not self.enabled:
            return
        key = (tuple(args), vault)
        with self._lock:
            self._store[key] = (stdout, time.monotonic())

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
