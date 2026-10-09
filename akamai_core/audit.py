"""Audit: scan a list of properties and report compliance flags."""
import logging

from .client import PapiClient
from .properties import get_property_rules, resolve_property
from .transforms import analyze_property_behaviors

AUDIT_HEADERS = ["Property Name", "Version", "OIPACL", "Tiered Distribution", "SiteShield", "SureRoute Type"]


def audit_properties(client: PapiClient, names: list[str], env_target: str, account_key: str,
                      logger: logging.Logger, on_progress=None) -> list[list]:
    """Returns a list of result rows (see AUDIT_HEADERS) for every requested property name."""
    rows = []
    total = len(names)
    for idx, name in enumerate(names, start=1):
        if on_progress:
            on_progress(idx, total, name)
        logger.info("Analyzing property: %s ...", name)
        try:
            base_info, matched_field = resolve_property(client, name, account_key)
            if not base_info:
                logger.warning("Could not resolve property '%s': not found via propertyName/hostname/edgeHostname", name)
                rows.append([name, "N/A", "N/A", "N/A", "N/A", "N/A"])
                continue

            tree, version_info = get_property_rules(client, base_info, env_target, account_key)
            if not tree:
                logger.warning("Could not resolve property '%s': %s", name, version_info)
                rows.append([name, "N/A", "N/A", "N/A", "N/A", "N/A"])
                continue

            res = analyze_property_behaviors(tree)
            version = version_info["propertyVersion"]
            logger.info("Result: v%s | OIPACL: %s | SiteShield: %s | SureRoute: %s",
                        version, res["oipacl"], res["siteshield"], res["sureroute_type"])
            rows.append([name, version, res["oipacl"], res["tiered_distribution"], res["siteshield"], res["sureroute_type"]])
        except Exception as e:
            logger.error("Error processing property %s: %s", name, e)
            rows.append([name, "ERROR", "N/A", "N/A", "N/A", "N/A"])

    return rows
