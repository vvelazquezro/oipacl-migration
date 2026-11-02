"""Unauthenticated liveness/readiness probes for GSAP's APL Workload health checks.

Registered directly on the Flask app (not the `main` blueprint) so they are
never subject to GSAP identity enforcement or the APP_ROOT_PATH prefix --
Kubernetes probes the pod IP and container port directly.
"""
from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.route("/readyz")
def readyz():
    # This app has no external dependency (DB, cache, etc.) to wait on at startup;
    # once Flask is serving requests it is ready to accept work.
    return jsonify({"status": "ok"}), 200


@bp.route("/livez")
def livez():
    return jsonify({"status": "ok"}), 200
