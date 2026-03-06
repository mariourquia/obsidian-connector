---
title: "Cache Layer Implementation Plan"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-05"
review_cycle_days: 90
sources_of_truth:
  - "obsidian_connector/cache.py"
  - "obsidian_connector/config.py"
---

# Cache Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an in-memory TTL cache at the `run_obsidian()` level to eliminate redundant subprocess calls for read-only CLI operations.

**Architecture:** A `CLICache` class holds `{(args_tuple, vault): (stdout, timestamp)}` entries with configurable TTL. `run_obsidian()` checks the cache before spawning a subprocess and stores results after. Mutation commands (`daily:append`, `create`) bypass the cache and call `clear()`. Cache is disabled by default (`cache_ttl=0`).

**Tech Stack:** Python stdlib only (`threading.Lock`, `time.monotonic`). No new dependencies.

---

### Task 1: Create `cache.py` with `CLICache`

**Files:**
- Create: `obsidian_connector/cache.py`

**Step 1: Write `cache.py`**

```python
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
```

**Step 2: Verify it compiles**

Run: `python -m py_compile obsidian_connector/cache.py`
Expected: no output, exit 0

---

### Task 2: Add `cache_ttl` to `ConnectorConfig`

**Files:**
- Modify: `obsidian_connector/config.py:42-49` (ConnectorConfig dataclass)
- Modify: `obsidian_connector/config.py:52-62` (load_config function)

**Step 1: Add `cache_ttl` field to `ConnectorConfig`**

Add after `default_folders` field (line 49):

```python
    cache_ttl: int = 0
```

**Step 2: Add env var loading in `load_config()`**

Add to the `ConnectorConfig(...)` constructor call:

```python
        cache_ttl=int(os.getenv("OBSIDIAN_CACHE_TTL") or file_cfg.get("cache_ttl", 0)),
```

**Step 3: Verify it compiles**

Run: `python -m py_compile obsidian_connector/config.py`
Expected: no output, exit 0

---

### Task 3: Integrate cache into `run_obsidian()`

**Files:**
- Modify: `obsidian_connector/client.py:1-10` (imports)
- Modify: `obsidian_connector/client.py:39-116` (run_obsidian function)

**Step 1: Add module-level cache instance**

After the existing imports (line 8), add:

```python
from obsidian_connector.cache import CLICache

_cache = CLICache()
```

**Step 2: Add cache logic to `run_obsidian()`**

After `cfg = load_config()` (line 62), sync the cache TTL:

```python
    _cache.ttl = cfg.cache_ttl
```

After building `cmd` and before the subprocess call (after line 67), add cache-hit check:

```python
    # Cache: return cached result for read-only commands.
    if _cache.enabled and not _cache.is_mutation(args):
        cached = _cache.get(args, effective_vault)
        if cached is not None:
            return cached
```

After the successful return (replace the bare `return result.stdout` at line 116), add cache-store logic:

```python
    stdout = result.stdout

    # Cache: store read results, invalidate on mutations.
    if _cache.enabled:
        if _cache.is_mutation(args):
            _cache.clear()
        else:
            _cache.put(args, effective_vault, stdout)

    return stdout
```

**Step 3: Verify it compiles**

Run: `python -m py_compile obsidian_connector/client.py`
Expected: no output, exit 0

---

### Task 4: Export from `__init__.py`

**Files:**
- Modify: `obsidian_connector/__init__.py`

**Step 1: Add CLICache import and export**

Add import line:

```python
from obsidian_connector.cache import CLICache
```

Add `"CLICache"` to the `__all__` list (alphabetical order, after `"CommandTimeout"`).

**Step 2: Verify it compiles**

Run: `python -m py_compile obsidian_connector/__init__.py`
Expected: no output, exit 0

---

### Task 5: Write `scripts/cache_test.py`

**Files:**
- Create: `scripts/cache_test.py`

**Step 1: Write the test script**

Tests to include (following existing test script patterns):

1. **CLICache disabled by default** -- `CLICache()` has `enabled == False`
2. **CLICache stores and retrieves** -- `put()` then `get()` returns same value
3. **CLICache TTL expiry** -- entry expires after TTL (use `ttl=1`, sleep 1.1s)
4. **CLICache mutation detection** -- `is_mutation(["daily:append", ...])` returns True, `is_mutation(["search:context", ...])` returns False
5. **CLICache clear on mutation** -- put entry, clear, get returns None
6. **CLICache thread safety** -- concurrent puts from multiple threads don't crash
7. **Config loads cache_ttl from env** -- set `OBSIDIAN_CACHE_TTL=10`, verify config
8. **Config defaults cache_ttl to 0** -- unset env, verify config
9. **Integration: search cached** -- set `OBSIDIAN_CACHE_TTL=30`, call `search_notes()` twice, second call should be faster (subprocess not invoked)
10. **Integration: mutation invalidates** -- search, then log_to_daily, then search again should re-invoke subprocess

**Step 2: Run the tests**

Run: `python scripts/cache_test.py`
Expected: 10/10 pass

---

### Task 6: Update docs

**Files:**
- Modify: `TOOLS_CONTRACT.md` (add cache section)
- Modify: `README.md` (add cache_ttl env var to table)

**Step 1: Add cache section to TOOLS_CONTRACT.md**

After the "Content escaping limitation" section, add:

```markdown
### In-memory cache

Read-only commands (`search`, `read`, `tasks`) can be cached in-memory to
avoid redundant subprocess calls.  The cache is **disabled by default**.

Enable via environment variable:

    export OBSIDIAN_CACHE_TTL=30   # seconds

Or in `config.json`:

    { "cache_ttl": 30 }

Mutations (`log-daily`, `create-research-note`) bypass the cache and
invalidate all entries.  The cache is per-process and not persisted to disk.
```

**Step 2: Add `OBSIDIAN_CACHE_TTL` to README env var table**

Add row:

```
| `OBSIDIAN_CACHE_TTL` | `0` (disabled) | In-memory cache TTL in seconds for read ops |
```

**Step 3: Update file layout in TOOLS_CONTRACT.md**

Add `cache.py` line:

```
    cache.py                       In-memory TTL cache
```

And add `cache_test.py` to scripts section.

---

### Task 7: Final verification

**Step 1: Compile all files**

Run: `python -m compileall obsidian_connector/ main.py scripts/`
Expected: all files compile, exit 0

**Step 2: Run all test suites**

Run: `python scripts/cache_test.py`
Expected: 10/10 pass

Run: `python scripts/smoke_test.py`
Expected: 8/8 pass (existing tests unaffected, cache disabled by default)

**Step 3: Integration smoke test with cache enabled**

Run: `OBSIDIAN_CACHE_TTL=30 python -c "from obsidian_connector import search_notes; r1=search_notes('test'); r2=search_notes('test'); print('ok' if r1==r2 else 'MISMATCH')"`
Expected: prints "ok"
