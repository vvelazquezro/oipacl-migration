"""Activate: push migrated property versions to staging or production."""
from __future__ import annotations

import logging
import re

from .client import PapiClient

ERROR_HEADERS = ["Configuration name", "Configuration version", "Error Detail"]

_PM_ERRORS = [
    "Domain validation is pending",
    "is not available with the modules",
    "refers to a policy named",
    "that does not exist",
    "property hostname is required",
]


def activate_single(client: PapiClient, name: str, version: str, network: str, account_key: str,
                     notes: str, notify_email: str, peer_reviewer_email: str,
                     logger: logging.Logger) -> tuple[bool, str | None]:
    """Activates one property version. Returns (success, error_reason_or_None)."""
    res = client.post("/papi/v1/search/find-by-value", {"propertyName": name}, account_key)
    items = res.get("versions", {}).get("items") if isinstance(res, dict) else None
    if not items:
        logger.error("Property %s not found.", name)
        return False, "Not Found during activation"

    prop = items[0]
    notify_emails = [e.strip() for e in notify_email.split(",") if e.strip()]
    payload = {
        "propertyVersion": int(version), "network": network.upper(), "note": notes,
        "notifyEmails": notify_emails, "acknowledgeAllWarnings": True,
        "activationType": "ACTIVATE", "ignoreHttpErrors": True, "canFastFallback": True,
    }
    if network.lower() == "production":
        payload["complianceRecord"] = {"noncomplianceReason": "EMERGENCY", "peerReviewedBy": peer_reviewer_email, "unitTested": True}

    logger.info("--- Activating: %s v%s ---", name, version)
    try:
        params = {"contractId": prop["contractId"], "groupId": prop["groupId"], "accountSwitchKey": account_key}
        ans = client.post_with_params(f"/papi/v1/properties/{prop['propertyId']}/activations", payload, params)

        act_id = ans.get("activationId") or (
            re.search(r"/activations/(atv_[^?]+)", ans.get("activationLink", "")).group(1)
            if ans.get("activationLink") else None
        )
        if act_id:
            logger.info("SUCCESS: %s (ID: %s)", name, act_id)
            return True, None

        detail = str(ans.get("detail", ""))
        if "is already active" in detail or "already being activated" in detail:
            logger.info("SUCCESS: %s v%s already active or in progress.", name, version)
            return True, None

        if any(e in str(ans) for e in _PM_ERRORS):
            logger.error("PM ERROR: %s -> %s", name, detail or ans)
            return False, "PM Config Error"

        logger.error("UNKNOWN ERROR: %s. Response: %s", name, ans)
        return False, "Unknown Activation Error"

    except Exception as e:
        logger.error("SCRIPT ERROR for %s: %s", name, e)
        return False, str(e)


def activate_properties(client: PapiClient, rows: list[list], network: str, account_key: str,
                         notes: str, notify_email: str, peer_reviewer_email: str,
                         logger: logging.Logger, on_progress=None) -> dict:
    """rows: list of [name, version]. Returns {"succeeded": [...], "errors": [[name, version, reason]]}."""
    succeeded = []
    errors = []
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        if not row:
            continue
        name, version = row[0], row[1]
        if on_progress:
            on_progress(idx, total, name)
        ok, reason = activate_single(client, name, version, network, account_key, notes, notify_email, peer_reviewer_email, logger)
        if ok:
            succeeded.append([name, version])
        else:
            errors.append([name, version, reason])
    return {"succeeded": succeeded, "errors": errors}
