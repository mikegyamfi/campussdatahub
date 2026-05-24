"""
Request-driven cron. Every request calls `_tick()`; the module-level cache makes the
hot path a single timestamp comparison, so we hit the DB only when a job is genuinely
due. When something is due we claim it atomically via select_for_update(skip_locked)
on the SystemTask row, then hand it to a daemon thread so the request is not delayed.

Under N gunicorn workers, the skip_locked filter means exactly one worker per tick wins
the claim and the others move on. If skip_locked is not supported (SQLite), we fall
back to a normal lock — fine for single-process dev.
"""
import logging
import threading
import time

from django.db import DatabaseError, NotSupportedError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Module-level cache: monotonic seconds when the next tick is allowed. Each gunicorn
# worker has its own. The DB-side claim keeps the global rate honest even if workers
# disagree about when to look.
_next_tick_allowed_monotonic = 0.0
_cache_lock = threading.Lock()
_min_recheck_seconds = 15.0


class SchedulerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            _tick()
        except Exception:
            logger.exception("scheduler tick raised")
        return self.get_response(request)


def _tick():
    global _next_tick_allowed_monotonic

    now_mono = time.monotonic()
    with _cache_lock:
        if now_mono < _next_tick_allowed_monotonic:
            return
        # Push the cache forward unconditionally. Even if we end up doing no work below,
        # we won't recheck for `_min_recheck_seconds`. This caps DB load to ~1 query per
        # worker per 15s and is safe because the DB-side claim is what actually decides
        # who runs what.
        _next_tick_allowed_monotonic = now_mono + _min_recheck_seconds

    # Import lazily so this module is importable before migrations have run.
    from intel_app import cron
    from intel_app.models import SystemTask

    now = timezone.now()
    try:
        claimed_keys = _claim_due_tasks(SystemTask, now)
    except DatabaseError:
        # Table doesn't exist yet (pre-migrate), or a transient DB issue. Either way,
        # back off and try again on the next request after the recheck window.
        logger.debug("scheduler: DB not ready; skipping tick", exc_info=True)
        return

    for key, _interval in claimed_keys:
        cron.run_in_thread(key)


def _claim_due_tasks(SystemTask, now):
    """
    Atomically pick up all due tasks. Returns list of (key, interval_seconds) tuples
    for tasks this worker now owns. Other workers will see them locked / freshly bumped
    and skip.
    """
    claimed = []
    with transaction.atomic():
        qs = SystemTask.objects.filter(enabled=True)
        try:
            qs = qs.select_for_update(skip_locked=True)
            rows = list(qs)
        except NotSupportedError:
            # SQLite — fall back to a plain lock. Fine for single-process dev.
            rows = list(SystemTask.objects.select_for_update().filter(enabled=True))

        for row in rows:
            if row.last_run_at is None:
                due = True
            else:
                age = (now - row.last_run_at).total_seconds()
                due = age >= row.interval_seconds
            if not due:
                continue
            row.last_run_at = now
            row.save(update_fields=['last_run_at'])
            claimed.append((row.key, row.interval_seconds))
    return claimed
