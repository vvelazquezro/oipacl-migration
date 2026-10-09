"""In-memory job registry + bounded worker pool for running Akamai operations in the background.

Each job gets its own log queue (consumed by an SSE endpoint) and its own
result files, keyed by job_id, so concurrent users never see each other's
data. Credentials only ever live in a job's local variables / a 0600 temp
file for the duration of the job (see akamai_core.auth.build_client).
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from akamai_core.activate import activate_properties
from akamai_core.audit import AUDIT_HEADERS, audit_properties
from akamai_core.auth import build_client
from akamai_core.errors import PapiRequestError
from akamai_core.migrate import ACTIVATE_HEADERS, ERROR_HEADERS as MIGRATE_ERROR_HEADERS, migrate_properties

_SENTINEL = object()
_JOB_TTL_SECONDS = 3600  # jobs (and their credentials-free results) are dropped after this


@dataclass
class Job:
    id: str
    action: str
    status: str = "queued"  # queued -> running -> done | error
    error: str | None = None
    files: dict | None = None  # {filename: (headers, rows)}
    summary: dict | None = None  # friendly counts shown on completion
    charts: dict | None = None  # {chart_key: [{"label":, "count":, "names": [...]}]} for audit/migrate jobs
    names: list | None = None  # original property list, for audit jobs, so Migrate can be prefilled
    created_at: float = field(default_factory=time.time)
    log_queue: "queue.Queue" = field(default_factory=queue.Queue)
    log_lines: list = field(default_factory=list)  # full log, retained so it can be downloaded after the job ends


class _QueueLogHandler(logging.Handler):
    def __init__(self, q: "queue.Queue", log_lines: list):
        super().__init__()
        self.q = q
        self.log_lines = log_lines

    def emit(self, record):
        line = self.format(record)
        self.log_lines.append(line)
        self.q.put({"type": "log", "line": line})


def _make_job_logger(job: Job) -> logging.Logger:
    logger = logging.getLogger(f"job.{job.id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _QueueLogHandler(job.log_queue, job.log_lines)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger


_SURE_ROUTE_LABELS = {"Missing": "No SureRoute", "CUSTOM_MAP": "Custom Map", "PERFORMANCE": "Performance"}


def _bucket_audit_rows(rows, col_idx, label_fn):
    """Groups resolved audit rows by a labeled column, for the results charts."""
    buckets = {}
    for row in rows:
        if row[1] in ("N/A", "ERROR"):
            continue
        label = label_fn(row[col_idx])
        buckets.setdefault(label, []).append(row[0])
    return [{"label": label, "count": len(names), "names": names} for label, names in buckets.items()]


def build_audit_charts(rows: list[list]) -> dict:
    return {
        "sureroute": _bucket_audit_rows(rows, 5, lambda v: _SURE_ROUTE_LABELS.get(v, v.replace("_", " ").title())),
        "siteshield": _bucket_audit_rows(rows, 4, lambda v: "With SiteShield" if v == "Yes" else "Without SiteShield"),
        "tiered_distribution": _bucket_audit_rows(rows, 3, lambda v: "With Tiered Distribution" if v == "Yes" else "Without Tiered Distribution"),
    }


def build_migrate_charts(to_activate: list[list], errors: list[list],
                          activation_succeeded: list[list] | None = None, activation_errors: list[list] | None = None) -> dict:
    charts = {
        "migration": [
            {"label": "Migrated", "count": len(to_activate), "names": [r[0] for r in to_activate]},
            {"label": "Skipped / Failed", "count": len(errors), "names": [r[0] for r in errors]},
        ],
    }
    if activation_succeeded is not None or activation_errors is not None:
        activation_succeeded = activation_succeeded or []
        activation_errors = activation_errors or []
        charts["activation"] = [
            {"label": "Activated", "count": len(activation_succeeded), "names": [r[0] for r in activation_succeeded]},
            {"label": "Activation Failed", "count": len(activation_errors), "names": [r[0] for r in activation_errors]},
        ]
    return charts


class JobManager:
    def __init__(self, max_workers: int):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="akamai-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, action: str, creds: dict, params: dict) -> str:
        job = Job(id=uuid.uuid4().hex, action=action)
        with self._lock:
            self._jobs[job.id] = job
        self._purge_expired()
        self._executor.submit(self._run, job, creds, params)
        return job.id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _purge_expired(self):
        cutoff = time.time() - _JOB_TTL_SECONDS
        with self._lock:
            expired = [jid for jid, j in self._jobs.items() if j.created_at < cutoff]
            for jid in expired:
                del self._jobs[jid]

    def _run(self, job: Job, creds: dict, params: dict):
        job.status = "running"
        logger = _make_job_logger(job)

        def on_progress(current, total, name=None):
            job.log_queue.put({"type": "progress", "current": current, "total": total, "name": name})

        try:
            with build_client(creds) as client:
                if job.action == "audit":
                    rows = audit_properties(client, params["names"], params["version"], params["account_key"],
                                             logger, on_progress=on_progress)
                    job.files = {"audit_results.csv": (AUDIT_HEADERS, rows)}
                    not_found = sum(1 for r in rows if r[1] in ("N/A", "ERROR"))
                    job.summary = {"scanned": len(rows), "resolved": len(rows) - not_found, "not_found": not_found}
                    job.charts = build_audit_charts(rows)
                    job.names = params["names"]

                elif job.action == "migrate":
                    result = migrate_properties(client, params["names"], params["version"], params["account_key"],
                                                 params["notes"], logger, on_progress=on_progress)
                    to_activate = result["to_activate"]
                    errors = result["errors"]

                    activate_option = params.get("activate_option", "none")
                    activation_succeeded: list = []
                    activation_errors: list = []

                    if activate_option != "none" and to_activate:
                        networks = {"staging": ["staging"], "production": ["production"], "both": ["staging", "production"]}[activate_option]
                        rows = [[name, str(version)] for name, version in to_activate]
                        for network in networks:
                            logger.info("Auto-activating %d migrated propert(ies) to %s...", len(rows), network)
                            act_result = activate_properties(client, rows, network, params["account_key"], params["notes"],
                                                              params["notify_email"], params["peer_reviewer_email"],
                                                              logger, on_progress=on_progress)
                            activation_succeeded.extend([n, v, network] for n, v in act_result["succeeded"])
                            activation_errors.extend([n, v, network, reason] for n, v, reason in act_result["errors"])

                    job.files = {}
                    if errors:
                        job.files["migration_errors.csv"] = (MIGRATE_ERROR_HEADERS, errors)
                    if activate_option == "none":
                        # Only surface the "still needs activation" list when nothing was auto-deployed above.
                        job.files["properties_to_activate.csv"] = (ACTIVATE_HEADERS, to_activate)
                    if activation_succeeded or activation_errors:
                        combined = [[n, v, net, "Success"] for n, v, net in activation_succeeded] + \
                                   [[n, v, net, reason] for n, v, net, reason in activation_errors]
                        job.files["activation_results.csv"] = (
                            ["Configuration name", "Configuration version", "Network", "Status"], combined)

                    job.summary = {"migrated": len(to_activate), "skipped_or_failed": len(errors)}
                    if activate_option != "none":
                        job.summary["activated"] = len(activation_succeeded)
                        job.summary["activation_failed"] = len(activation_errors)

                    job.charts = build_migrate_charts(
                        to_activate, errors,
                        activation_succeeded if activate_option != "none" else None,
                        activation_errors if activate_option != "none" else None,
                    )

                elif job.action == "activate":
                    result = activate_properties(client, params["rows"], params["version"], params["account_key"],
                                                  params["notes"], params["notify_email"], params["peer_reviewer_email"],
                                                  logger, on_progress=on_progress)
                    combined = [[n, v, "Success"] for n, v in result["succeeded"]] + \
                               [[n, v, reason] for n, v, reason in result["errors"]]
                    job.files = {"activation_results.csv": (["Configuration name", "Configuration version", "Status"], combined)}
                    job.summary = {"succeeded": len(result["succeeded"]), "failed": len(result["errors"])}

            logger.info("Job complete.")
            job.status = "done"
        except PapiRequestError as e:
            logger.error("API error: %s", e)
            job.status = "error"
            job.error = str(e)
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            job.status = "error"
            job.error = str(e)
        finally:
            job.log_queue.put(_SENTINEL)


def stream_job_logs(job: Job):
    """Generator yielding SSE-formatted lines for a job's live log, then closes when the job finishes.

    Handles reconnects to an already-finished job: the queue's sentinel is only ever
    consumed once, so status/summary/error are re-derived from the Job itself.
    """
    while True:
        if job.log_queue.empty() and job.status in ("done", "error"):
            payload = {"status": job.status, "error": job.error, "summary": job.summary}
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
            break
        try:
            item = job.log_queue.get(timeout=15)
        except queue.Empty:
            yield ": keep-alive\n\n"
            continue
        if item is _SENTINEL:
            payload = {"status": job.status, "error": job.error, "summary": job.summary}
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
            break
        if item.get("type") == "progress":
            yield f"event: progress\ndata: {json.dumps(item)}\n\n"
        else:
            yield f"data: {item['line']}\n\n"
