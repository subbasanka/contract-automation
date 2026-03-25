"""
Module 5: Delta Comparison Engine
Compares two snapshots field-by-field and produces a structured change report.
Handles ADDED, REMOVED, and MODIFIED products.
"""

import logging

logger = logging.getLogger(__name__)

# Fields to compare between product versions
PRODUCT_COMPARE_FIELDS = [
    "base_rebate_pct",
    "formulary_status",
    "price_protection_threshold",
    "start_date",
    "end_date",
    "admin_fee",
    "frequency",
    "minimum_rebate",
    "maximum_rebate",
    "market_share",
    "definition_hash",
]

# Agreement-level fields to compare
AGREEMENT_COMPARE_FIELDS = [
    "commencement_date",
    "termination_date",
    "payment_terms_days",
    "notice_period_days",
]


def compare_snapshots(
    old_snapshot: dict | None,
    new_snapshot: dict,
) -> dict:
    """Compare two snapshots and produce a structured delta report.

    Args:
        old_snapshot: The previous version's snapshot (None for original contract).
        new_snapshot: The current version's snapshot.

    Returns:
        Delta report dict with:
          - version_from: int
          - version_to: int
          - product_changes: list of product change dicts
          - agreement_changes: list of agreement-level change dicts
          - summary: human-readable summary string
    """
    if old_snapshot is None:
        return _build_initial_delta(new_snapshot)

    delta = {
        "version_from": old_snapshot.get("version", 0),
        "version_to": new_snapshot.get("version", 0),
        "product_changes": [],
        "agreement_changes": [],
        "summary": "",
    }

    old_products = old_snapshot.get("products", {})
    new_products = new_snapshot.get("products", {})

    all_product_keys = set(old_products.keys()) | set(new_products.keys())

    for product_key in sorted(all_product_keys):
        in_old = product_key in old_products
        in_new = product_key in new_products

        if in_new and not in_old:
            # ADDED
            delta["product_changes"].append({
                "product": product_key,
                "change_type": "ADDED",
                "fields": new_products[product_key],
                "changed_fields": {},
                "notes": f"New product added in amendment {new_snapshot.get('version', '?')}",
            })

        elif in_old and not in_new:
            # REMOVED
            delta["product_changes"].append({
                "product": product_key,
                "change_type": "REMOVED",
                "fields": old_products[product_key],
                "changed_fields": {},
                "notes": f"Product removed in amendment {new_snapshot.get('version', '?')}",
            })

        else:
            # Both exist — check for MODIFIED
            old_prod = old_products[product_key]
            new_prod = new_products[product_key]
            changed_fields = _compare_product_fields(old_prod, new_prod)

            if changed_fields:
                delta["product_changes"].append({
                    "product": product_key,
                    "change_type": "MODIFIED",
                    "fields": new_products[product_key],
                    "changed_fields": changed_fields,
                    "notes": _build_change_notes(changed_fields),
                })

    # Agreement-level changes
    delta["agreement_changes"] = _compare_agreement_fields(old_snapshot, new_snapshot)

    # Build summary
    added = sum(1 for c in delta["product_changes"] if c["change_type"] == "ADDED")
    removed = sum(1 for c in delta["product_changes"] if c["change_type"] == "REMOVED")
    modified = sum(1 for c in delta["product_changes"] if c["change_type"] == "MODIFIED")
    agreement_changes = len(delta["agreement_changes"])

    parts = []
    if added:
        parts.append(f"{added} added")
    if removed:
        parts.append(f"{removed} removed")
    if modified:
        parts.append(f"{modified} modified")
    if agreement_changes:
        parts.append(f"{agreement_changes} agreement-level change(s)")

    delta["summary"] = (
        f"Amendment {delta['version_to']}: {', '.join(parts)}"
        if parts
        else f"Amendment {delta['version_to']}: No changes detected"
    )

    logger.info(delta["summary"])
    return delta


def _build_initial_delta(snapshot: dict) -> dict:
    """Build a delta for the original contract (all products are ADDED)."""
    product_changes = []
    for product_key, product_data in snapshot.get("products", {}).items():
        product_changes.append({
            "product": product_key,
            "change_type": "ADDED",
            "fields": product_data,
            "changed_fields": {},
            "notes": "Original contract",
        })

    return {
        "version_from": None,
        "version_to": snapshot.get("version", 0),
        "product_changes": product_changes,
        "agreement_changes": [],
        "summary": f"Original contract: {len(product_changes)} product(s)",
    }


def _compare_product_fields(old_prod: dict, new_prod: dict) -> dict:
    """Compare individual fields between two product versions.

    Returns a dict of changed fields: {field_name: {"old": ..., "new": ...}}
    """
    changes = {}
    for field in PRODUCT_COMPARE_FIELDS:
        old_val = old_prod.get(field)
        new_val = new_prod.get(field)

        # Normalize None vs empty string
        old_normalized = _normalize_value(old_val)
        new_normalized = _normalize_value(new_val)

        if old_normalized != new_normalized:
            changes[field] = {
                "old": old_val,
                "new": new_val,
            }

    return changes


def _compare_agreement_fields(old_snapshot: dict, new_snapshot: dict) -> list[dict]:
    """Compare agreement-level fields between snapshots."""
    changes = []

    # Top-level agreement fields
    for field in ["commencement_date", "termination_date"]:
        old_val = old_snapshot.get(field)
        new_val = new_snapshot.get(field)
        if _normalize_value(old_val) != _normalize_value(new_val):
            changes.append({
                "field": field,
                "old": old_val,
                "new": new_val,
            })

    # Nested agreement_fields
    old_fields = old_snapshot.get("agreement_fields", {})
    new_fields = new_snapshot.get("agreement_fields", {})
    all_keys = set(old_fields.keys()) | set(new_fields.keys())

    for key in sorted(all_keys):
        old_val = old_fields.get(key)
        new_val = new_fields.get(key)
        if _normalize_value(old_val) != _normalize_value(new_val):
            changes.append({
                "field": key,
                "old": old_val,
                "new": new_val,
            })

    return changes


def _normalize_value(val) -> str:
    """Normalize a value for comparison."""
    if val is None:
        return ""
    return str(val).strip().lower()


def _build_change_notes(changed_fields: dict) -> str:
    """Build a human-readable notes string for changed fields."""
    parts = []
    for field_name, change in changed_fields.items():
        old = change["old"] or "N/A"
        new = change["new"] or "N/A"
        # Use a friendlier field name
        display_name = field_name.replace("_", " ").replace("pct", "%")
        parts.append(f"CHANGED: {display_name}: {old} \u2192 {new}")
    return "; ".join(parts)
