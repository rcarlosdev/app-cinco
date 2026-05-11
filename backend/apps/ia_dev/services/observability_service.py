import logging
import os
import time
from contextlib import contextmanager

from .sql_store import IADevSqlStore


logger = logging.getLogger(__name__)


class ObservabilityService:
    def __init__(self):
        self.enabled = (
            os.getenv("IA_DEV_OBSERVABILITY_ENABLED", "1").strip().lower()
            in ("1", "true", "yes", "on")
        )
        self.store = IADevSqlStore()

    def record_event(
        self,
        *,
        event_type: str,
        source: str,
        duration_ms: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
        meta: dict | None = None,
    ):
        if not self.enabled:
            return
        payload = {
            "event_type": event_type,
            "source": source,
            "duration_ms": duration_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "meta": meta or {},
        }
        logger.info("ia_dev_observability_event %s", payload)
        try:
            self.store.insert_observability_event(**payload)
        except Exception:
            logger.exception("No se pudo persistir evento de observabilidad")

    def summary(self, *, window_seconds: int = 3600, limit: int = 2000) -> dict:
        return self.summary_filtered(
            window_seconds=window_seconds,
            limit=limit,
            domain_code=None,
            generator=None,
            fallback_reason=None,
        )

    def summary_filtered(
        self,
        *,
        window_seconds: int = 3600,
        limit: int = 2000,
        domain_code: str | None = None,
        generator: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict:
        normalized_filters = {
            "domain_code": str(domain_code or "").strip().lower() or None,
            "generator": str(generator or "").strip().lower() or None,
            "fallback_reason": str(fallback_reason or "").strip().lower() or None,
        }
        if not self.enabled:
            return {
                "enabled": False,
                "window_seconds": int(window_seconds),
                "sample_size": 0,
                "applied_filters": normalized_filters,
                "event_types": {},
                "totals": {
                    "events": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": 0.0,
                    "latency": {"count": 0, "avg_ms": 0, "p95_ms": 0, "max_ms": 0},
                },
                "sources": {},
            }
        data = self.store.get_observability_summary(
            window_seconds=window_seconds,
            limit=limit,
            domain_code=normalized_filters["domain_code"],
            generator=normalized_filters["generator"],
            fallback_reason=normalized_filters["fallback_reason"],
        )
        data["applied_filters"] = normalized_filters
        data["enabled"] = True
        return data

    def list_events(
        self,
        *,
        window_seconds: int = 3600,
        limit: int = 5000,
        event_types: list[str] | None = None,
        created_after: int | None = None,
    ) -> list[dict]:
        if not self.enabled:
            return []
        return self.store.list_observability_events(
            window_seconds=window_seconds,
            limit=limit,
            event_types=event_types,
            created_after=created_after,
        )

    @contextmanager
    def measure(self, *, event_type: str, source: str, meta: dict | None = None):
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.record_event(
                event_type=event_type,
                source=source,
                duration_ms=elapsed_ms,
                meta=meta,
            )
