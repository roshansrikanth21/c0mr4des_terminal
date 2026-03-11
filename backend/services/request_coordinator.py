from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Awaitable, Callable, Dict, Optional


class RequestCoordinator:
    """
    Shared async coordinator for expensive backend workloads.
    - Deduplicates identical in-flight requests by key
    - Applies bounded concurrency per workload class
    - Optionally caches successful results for short TTL windows
    """

    def __init__(self) -> None:
        self._inflight: Dict[str, asyncio.Task] = {}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._limits = {
            "default": int(os.getenv("COORD_DEFAULT_CONCURRENCY", "12")),
            "dashboard": int(os.getenv("COORD_DASHBOARD_CONCURRENCY", "4")),
            "intel": int(os.getenv("COORD_INTEL_CONCURRENCY", "4")),
            "fusion": int(os.getenv("COORD_FUSION_CONCURRENCY", "4")),
            "chart": int(os.getenv("COORD_CHART_CONCURRENCY", "2")),
            "chat": int(os.getenv("COORD_CHAT_CONCURRENCY", "3")),
            "research": int(os.getenv("COORD_RESEARCH_CONCURRENCY", "1")),
        }

    def _get_semaphore(self, workload: str) -> asyncio.Semaphore:
        workload = workload or "default"
        if workload not in self._semaphores:
            self._semaphores[workload] = asyncio.Semaphore(self._limits.get(workload, self._limits["default"]))
        return self._semaphores[workload]

    def _cache_valid(self, key: str) -> bool:
        entry = self._cache.get(key)
        if not entry:
            return False
        return float(entry.get("expires_at", 0.0) or 0.0) > time.time()

    def _prune_cache(self) -> None:
        if not self._cache:
            return
        now = time.time()
        expired = [key for key, value in self._cache.items() if float(value.get("expires_at", 0.0) or 0.0) <= now]
        for key in expired:
            self._cache.pop(key, None)

    async def run(
        self,
        *,
        key: str,
        workload: str,
        work_fn: Callable[[], Awaitable[Any]],
        ttl_sec: float = 0.0,
        cache_success_predicate: Optional[Callable[[Any], bool]] = None,
    ) -> Any:
        self._prune_cache()
        if ttl_sec > 0 and self._cache_valid(key):
            return self._cache[key]["data"]

        async with self._lock:
            if ttl_sec > 0 and self._cache_valid(key):
                return self._cache[key]["data"]

            existing = self._inflight.get(key)
            if existing is not None:
                task = existing
            else:
                semaphore = self._get_semaphore(workload)

                async def _runner():
                    async with semaphore:
                        result = await work_fn()
                        if ttl_sec > 0:
                            should_cache = cache_success_predicate(result) if cache_success_predicate else True
                            if should_cache:
                                self._cache[key] = {
                                    "data": result,
                                    "expires_at": time.time() + float(ttl_sec),
                                }
                        return result

                task = asyncio.create_task(_runner())
                self._inflight[key] = task

        try:
            return await task
        finally:
            async with self._lock:
                current = self._inflight.get(key)
                if current is task:
                    self._inflight.pop(key, None)

    def get_status(self) -> Dict[str, Any]:
        self._prune_cache()
        return {
            "status": "success",
            "inflight": len(self._inflight),
            "cached": len(self._cache),
            "workloads": {
                key: {
                    "limit": limit,
                    "available": self._semaphores[key]._value if key in self._semaphores else limit,
                }
                for key, limit in self._limits.items()
            },
        }


request_coordinator = RequestCoordinator()
