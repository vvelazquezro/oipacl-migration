"""Property lookup and rule-tree retrieval, shared by audit/migrate/activate."""
from .client import PapiClient

SEARCH_FIELDS = ("propertyName", "hostname", "edgeHostname")


def get_target_version(items, target):
    """Get the version info matching the requested environment (no fallback to draft)."""
    for p in items:
        if (target == "production" and p.get("productionStatus") == "ACTIVE") or \
           (target == "staging" and p.get("stagingStatus") == "ACTIVE") or \
           (target == "latest" and p.get("stagingStatus") == "INACTIVE" and p.get("productionStatus") == "INACTIVE"):
            return p
    return None


def resolve_property(client: PapiClient, search_value: str, account_key: str, preferred_field: str = "propertyName"):
    """Search for a property by name/hostname/edge hostname, trying the preferred field first."""
    search_value = str(search_value).strip()
    attempts = list(SEARCH_FIELDS)
    if preferred_field in attempts:
        attempts.remove(preferred_field)
        attempts.insert(0, preferred_field)

    for field in attempts:
        res = client.post("/papi/v1/search/find-by-value", {field: search_value}, account_key)
        items = res.get("versions", {}).get("items") if isinstance(res, dict) else None
        if items:
            return items[0], field
    return None, None


def get_property_rules(client: PapiClient, base_info: dict, env_target: str, account_key: str):
    """Resolves the target version and its rule tree for a property.

    Returns (rules_dict, version_info) or (None, reason_str) on failure.
    """
    params = {"contractId": base_info["contractId"], "groupId": base_info["groupId"], "accountSwitchKey": account_key}

    versions_res = client.get(f"/papi/v1/properties/{base_info['propertyId']}/versions", params)
    all_versions = versions_res.get("versions", {}).get("items", [])

    info = get_target_version(all_versions, env_target)
    if not info:
        return None, "No Active Version"

    raw_rules = client.get(f"/papi/v1/properties/{base_info['propertyId']}/versions/{info['propertyVersion']}/rules/", params)
    rules = raw_rules.get("rules")
    if not rules:
        return None, "Rules tree empty"

    return {"rules": rules}, info
