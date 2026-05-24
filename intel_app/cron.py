"""
In-process scheduler. The middleware ticks per request; this module owns the registry
of jobs and the worker-thread plumbing.

Jobs run in daemon threads so they never block the web request and never prevent
process shutdown. Each thread closes its DB connections on exit so we don't leak.
"""
import logging
import threading

from django import db
from django.core.management import call_command

logger = logging.getLogger(__name__)


def _run_poll_geosams():
    call_command('poll_geosams_transactions')


def _run_cleanup_momo():
    call_command('cleanup_momo_alerts')


# Map SystemTask.key -> callable. New jobs: add an entry here and a SystemTask row.
TASKS = {
    'poll_geosams': _run_poll_geosams,
    'cleanup_momo': _run_cleanup_momo,
}


def run_in_thread(key):
    fn = TASKS.get(key)
    if fn is None:
        logger.warning("scheduler: unknown task key %r", key)
        return False

    def runner():
        # Lazy import — `intel_app.models` may not be importable at module-load time
        # in every context, but it always is by the time we're spawning workers.
        from intel_app.models import SystemTask

        status, detail = "ok", ""
        try:
            fn()
        except Exception as e:
            logger.exception("scheduler: task %s raised", key)
            status, detail = "error", str(e)[:500]
        finally:
            try:
                SystemTask.objects.filter(key=key).update(
                    last_run_status=status,
                    last_run_detail=detail,
                )
            except Exception:
                logger.exception("scheduler: failed to update SystemTask outcome for %s", key)
            # Each Django DB call in this thread opened a new connection from the per-
            # thread pool; close them so we don't pin connections after the job exits.
            db.connections.close_all()

    threading.Thread(target=runner, daemon=True, name=f"cron-{key}").start()
    return True
