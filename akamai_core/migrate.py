"""Migrate: replace SiteShield with OriginIpAcl + TieredDistribution, and change SureRoute map."""
import logging
import re

from .client import PapiClient
from .properties import get_property_rules, resolve_property
from .transforms import has_oipacl, has_ss, replace_siteShield, update_sureRoute

ACTIVATE_HEADERS = ["Configuration name", "Configuration version"]
ERROR_HEADERS = ["Configuration name", "Configuration version", "Error Detail"]


def migrate_properties(client: PapiClient, names: list[str], env_target: str, account_key: str,
                        notes: str, logger: logging.Logger, on_progress=None) -> dict:
    """Evaluates and migrates each property. Returns {"to_activate": [...], "errors": [...]} rows."""
    to_activate = []
    errors = []
    total = len(names)

    for idx, name in enumerate(names, start=1):
        if on_progress:
            on_progress(idx, total, name)
        logger.info("Checking property: %s ...", name)
        try:
            base_info, matched_field = resolve_property(client, name, account_key)
            if not base_info:
                logger.warning("Not found for %s. Skipping...", name)
                errors.append([name, "N/A", "Not Found in API Search"])
                continue

            tree, version_info = get_property_rules(client, base_info, env_target, account_key)
            if not tree:
                logger.warning("%s for %s. Skipping...", version_info, name)
                errors.append([name, "N/A", version_info])
                continue

            has_ss_flag = has_ss(tree)
            has_oipacl_flag = has_oipacl(tree)
            sr_changed = update_sureRoute(tree, logger)
            needs_oipacl_injection = not has_ss_flag and not has_oipacl_flag

            logger.info("Evaluated flags -> SiteShield: %s | Needs OipAcl: %s | SureRoute changed: %s",
                        has_ss_flag, needs_oipacl_injection, sr_changed)

            if not (has_ss_flag or sr_changed or needs_oipacl_injection):
                logger.info("No changes required for %s.", name)
                errors.append([name, version_info["propertyVersion"], "No changes required"])
                continue

            if has_ss_flag:
                logger.info("    -> SiteShield behavior detected. Replacing with OriginIpAcl.")
                tree = replace_siteShield(tree)

            if needs_oipacl_injection:
                logger.info("    -> OriginIpAcl missing. Injecting into default rule.")
                tree["rules"].setdefault("behaviors", []).append(
                    {"name": "originIpAcl", "options": {"enable": True}}
                )

            params = {"contractId": base_info["contractId"], "groupId": base_info["groupId"], "accountSwitchKey": account_key}
            new_res = client.post(f"/papi/v1/properties/{base_info['propertyId']}/versions",
                                   {"createFromVersion": version_info["propertyVersion"]}, account_key)
            if "versionLink" not in new_res:
                logger.error("Failed creating new version for %s.", name)
                errors.append([name, version_info["propertyVersion"], "Failed creating new version"])
                continue

            new_v = re.search(r"/versions/(.+?)\?", new_res["versionLink"]).group(1)
            tree["comments"] = notes

            upd_res = client.put(f"/papi/v1/properties/{base_info['propertyId']}/versions/{new_v}/rules", tree, params)
            if "propertyVersion" in upd_res:
                to_activate.append([name, upd_res["propertyVersion"]])
                logger.info("Migrated %s to v%s", name, upd_res["propertyVersion"])
            else:
                logger.error("Failed to save rules for %s. Response: %s", name, upd_res)
                errors.append([name, new_v, "Failed to save PUT rules"])

        except Exception as e:
            logger.error("Error migrating %s: %s", name, e)
            errors.append([name, "N/A", str(e)])

    return {"to_activate": to_activate, "errors": errors}
