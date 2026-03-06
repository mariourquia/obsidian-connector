#!/usr/bin/env python3
"""Validate the CLICache module and cache-related config."""

from __future__ import annotations

import os
import sys
import threading
import time

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.cache import CLICache
from obsidian_connector.config import load_config

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}")
        FAIL += 1


def main() -> int:
    # -- Test 1: CLICache disabled by default ----------------------------------
    print("\n--- CLICache disabled by default ---")
    c = CLICache()
    check("enabled is False", c.enabled is False)
    check("ttl is 0", c.ttl == 0)

    # -- Test 2: CLICache enabled when ttl > 0 ---------------------------------
    print("\n--- CLICache enabled when ttl > 0 ---")
    c2 = CLICache(ttl=10)
    check("enabled is True", c2.enabled is True)

    # -- Test 3: CLICache stores and retrieves ---------------------------------
    print("\n--- CLICache stores and retrieves ---")
    c3 = CLICache(ttl=60)
    c3.put(["search:context", "query=hello"], "TestVault", '{"results": []}')
    got = c3.get(["search:context", "query=hello"], "TestVault")
    check("get returns stored value", got == '{"results": []}')

    # -- Test 4: CLICache TTL expiry -------------------------------------------
    print("\n--- CLICache TTL expiry ---")
    c4 = CLICache(ttl=1)
    c4.put(["search:context", "query=expire"], "TestVault", "data")
    time.sleep(1.1)
    got4 = c4.get(["search:context", "query=expire"], "TestVault")
    check("get returns None after TTL", got4 is None)

    # -- Test 5: CLICache mutation detection -----------------------------------
    print("\n--- CLICache mutation detection ---")
    c5 = CLICache()
    check("daily:append is mutation", c5.is_mutation(["daily:append", "content=x"]) is True)
    check("search:context is not mutation", c5.is_mutation(["search:context", "query=x"]) is False)
    check("create is mutation", c5.is_mutation(["create", "name=x"]) is True)
    check("read is not mutation", c5.is_mutation(["read", "file=x"]) is False)

    # -- Test 6: CLICache clear ------------------------------------------------
    print("\n--- CLICache clear ---")
    c6 = CLICache(ttl=60)
    c6.put(["search:context", "query=a"], "V", "a")
    c6.put(["search:context", "query=b"], "V", "b")
    c6.put(["search:context", "query=c"], "V", "c")
    c6.clear()
    check("len is 0 after clear", len(c6) == 0)

    # -- Test 7: CLICache thread safety ----------------------------------------
    print("\n--- CLICache thread safety ---")
    c7 = CLICache(ttl=60)
    errors: list[Exception] = []

    def writer(thread_id: int) -> None:
        try:
            for i in range(100):
                c7.put([f"search:context", f"query=t{thread_id}_i{i}"], "V", f"v{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("no errors from threads", len(errors) == 0)
    check("cache has entries after threaded puts", len(c7) > 0)

    # -- Test 8: Config loads cache_ttl from env -------------------------------
    print("\n--- Config loads cache_ttl from env ---")
    os.environ["OBSIDIAN_CACHE_TTL"] = "15"
    try:
        cfg8 = load_config()
        check("cache_ttl is 15", cfg8.cache_ttl == 15)
    finally:
        del os.environ["OBSIDIAN_CACHE_TTL"]

    # -- Test 9: Config defaults cache_ttl to 0 --------------------------------
    print("\n--- Config defaults cache_ttl to 0 ---")
    os.environ.pop("OBSIDIAN_CACHE_TTL", None)
    cfg9 = load_config()
    check("cache_ttl is 0", cfg9.cache_ttl == 0)

    # -- Test 10: Integration -- cached search is identical --------------------
    print("\n--- Integration: cached search is identical ---")
    from obsidian_connector.client import log_to_daily, search_notes

    os.environ["OBSIDIAN_CACHE_TTL"] = "30"
    try:
        r1 = search_notes("learning")
        r2 = search_notes("learning")
        check("two searches return equal results", r1 == r2)

        log_to_daily("[cache_test] invalidation probe")
        # After mutation the cache should be cleared; subsequent search is fresh.
        r3 = search_notes("learning")
        check("post-invalidation search still equal", r3 == r1)
    finally:
        os.environ.pop("OBSIDIAN_CACHE_TTL", None)

    # -- Summary ---------------------------------------------------------------
    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
