"""Pure rule-tree transforms and inspections for Akamai property rule trees."""
import logging

_NULL_LOGGER = logging.getLogger("akamai_core.transforms")
_NULL_LOGGER.addHandler(logging.NullHandler())


def has_behavior(json_tree, behavior_name: str) -> bool:
    """Check if the rules tree contains a behavior with the given name."""
    if isinstance(json_tree, dict):
        for key, value in json_tree.items():
            if key == "name" and value == behavior_name:
                return True
            if has_behavior(value, behavior_name):
                return True
    elif isinstance(json_tree, list):
        for item in json_tree:
            if has_behavior(item, behavior_name):
                return True
    return False


def has_ss(json_tree) -> bool:
    return has_behavior(json_tree, "siteShield")


def has_oipacl(json_tree) -> bool:
    return has_behavior(json_tree, "originIpAcl")


def replace_siteShield(tree):
    """Replace "siteShield" nodes with "originIpAcl" and "tieredDistribution"."""
    origin_acl = {"name": "originIpAcl", "options": {"enable": True}}
    tiered = {"name": "tieredDistribution", "options": {"enabled": True}}

    def _rep(node, td_seen):
        if isinstance(node, list):
            new_lst = []
            for i in node:
                if isinstance(i, dict) and i.get("name") == "siteShield":
                    new_lst.append(origin_acl)
                    if not td_seen:
                        new_lst.append(tiered)
                        td_seen = True
                    continue
                if isinstance(i, dict) and i.get("name") == "tieredDistribution":
                    i.setdefault("options", {})["enabled"] = True
                    new_i, td_seen = _rep(i, True)
                    new_lst.append(new_i)
                    td_seen = True
                    continue
                new_i, td_seen = _rep(i, td_seen)
                new_lst.append(new_i)
            return new_lst, td_seen
        if isinstance(node, dict):
            return {k: _rep(v, td_seen)[0] for k, v in node.items()}, td_seen
        return node, td_seen

    return _rep(tree, False)[0]


def update_sureRoute(node, logger: logging.Logger = _NULL_LOGGER) -> bool:
    """Migrate "sureRoute" nodes from "CUSTOM_MAP" to "PERFORMANCE". Returns True if changed."""
    changed = False
    if isinstance(node, dict):
        if node.get("name") == "sureRoute" and node.get("options", {}).get("type") == "CUSTOM_MAP":
            logger.info("    -> SureRoute CUSTOM_MAP detected. Updating to PERFORMANCE.")
            node["options"]["type"] = "PERFORMANCE"
            node["options"].pop("customMap", None)
            return True
        for v in node.values():
            if update_sureRoute(v, logger):
                changed = True
        return changed
    if isinstance(node, list):
        for item in node:
            if update_sureRoute(item, logger):
                changed = True
        return changed
    return changed


def analyze_property_behaviors(node, results=None):
    """Scans the property tree to extract compliance flags and statuses."""
    if results is None:
        results = {
            "oipacl": "No",
            "tiered_distribution": "No",
            "siteshield": "No",
            "sureroute_type": "Missing",
        }

    if isinstance(node, dict):
        name = node.get("name")
        if name == "originIpAcl":
            if node.get("options", {}).get("enabled") is True or node.get("options", {}).get("enable") is True:
                results["oipacl"] = "Yes"
        elif name == "tieredDistribution":
            if node.get("options", {}).get("enabled") is True or node.get("options", {}).get("enable") is True:
                results["tiered_distribution"] = "Yes"
        elif name == "siteShield":
            results["siteshield"] = "Yes"
        elif name == "sureRoute":
            results["sureroute_type"] = node.get("options", {}).get("type", "UNKNOWN")

        for v in node.values():
            analyze_property_behaviors(v, results)
    elif isinstance(node, list):
        for item in node:
            analyze_property_behaviors(item, results)

    return results
