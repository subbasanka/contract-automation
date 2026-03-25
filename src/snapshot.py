"""
Module 4: Snapshot Builder
Builds and maintains cumulative JSON snapshots of contract state.
Each snapshot represents the full contract state after a given amendment.
"""

import os
import json
import logging
from pathlib import Path
from copy import deepcopy

logger = logging.getLogger(__name__)


def build_snapshot(
    extracted_products: list[dict],
    agreement_id: str,
    amendment_number: int,
    company_name: str,
    preamble_fields: dict,
    prior_snapshot: dict | None = None,
) -> dict:
    """Build a cumulative snapshot from extracted fields.

    If a prior snapshot exists, the new snapshot starts as a copy of the prior one,
    then applies the changes from the current amendment. Products marked as
    "deleted and replaced" fully overwrite the prior version.

    Args:
        extracted_products: List of field dicts from field_extractor.
        agreement_id: The agreement number.
        amendment_number: 0 for original, 1+ for amendments.
        company_name: Company name.
        preamble_fields: Agreement-level fields extracted from preamble.
        prior_snapshot: The previous version's snapshot, or None.

    Returns:
        Complete snapshot dict.
    """
    if prior_snapshot and amendment_number > 0:
        snapshot = deepcopy(prior_snapshot)
        snapshot["version"] = amendment_number
    else:
        snapshot = {
            "agreement_id": agreement_id,
            "version": amendment_number,
            "company": company_name,
            "commencement_date": "",
            "termination_date": "",
            "agreement_fields": {},
            "products": {},
        }

    # Update agreement-level fields from preamble
    if preamble_fields:
        for key, value in preamble_fields.items():
            if value:  # Only update non-empty fields
                if key in ("commencement_date", "termination_date"):
                    snapshot[key] = value
                else:
                    snapshot["agreement_fields"][key] = value

    # Update product-level fields
    for product_fields in extracted_products:
        product_name = product_fields.get("Product", "UNKNOWN")
        if product_name == "UNKNOWN":
            continue

        product_key = product_name.upper()

        # Build product entry
        product_entry = {
            "product_name": product_name,
            "base_rebate_pct": product_fields.get("Tier Benefit / Base Rebate %"),
            "formulary_status": product_fields.get("Formulary Status / BoB"),
            "price_protection_threshold": product_fields.get("Price Increase Threshold %"),
            "start_date": product_fields.get("Program Start Date"),
            "end_date": product_fields.get("Program End Date"),
            "admin_fee": product_fields.get("Admin Fee %"),
            "frequency": product_fields.get("Frequency"),
            "minimum_rebate": product_fields.get("Minimum Rebate"),
            "maximum_rebate": product_fields.get("Maximum Rebate"),
            "market_share": product_fields.get("Market Share Requirement"),
            "definition_hash": product_fields.get("Definition Hash"),
            "amendment_label": product_fields.get("Amendment #"),
        }

        # If product existed in prior snapshot, merge (only overwrite non-None fields)
        if product_key in snapshot["products"] and amendment_number > 0:
            existing = snapshot["products"][product_key]
            for field_key, field_val in product_entry.items():
                if field_val is not None:
                    existing[field_key] = field_val
        else:
            snapshot["products"][product_key] = product_entry

    return snapshot


def save_snapshot(snapshot: dict, snapshot_dir: str) -> str:
    """Save a snapshot to disk.

    Returns the file path of the saved snapshot.
    """
    agreement_id = snapshot["agreement_id"]
    version = snapshot["version"]

    agreement_dir = os.path.join(snapshot_dir, agreement_id)
    os.makedirs(agreement_dir, exist_ok=True)

    filename = f"snapshot_v{version}.json"
    filepath = os.path.join(agreement_dir, filename)

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, ensure_ascii=False)

    logger.info("Saved snapshot: %s", filepath)
    return filepath


def load_snapshot(snapshot_dir: str, agreement_id: str, version: int) -> dict | None:
    """Load a specific version snapshot."""
    filepath = os.path.join(snapshot_dir, agreement_id, f"snapshot_v{version}.json")
    if not os.path.isfile(filepath):
        return None

    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_snapshot_chain(snapshot_dir: str, agreement_id: str) -> list[int]:
    """Validate that all versions in the chain exist (v0 through vN).

    Returns a list of missing version numbers (empty list = valid chain).
    """
    agreement_dir = os.path.join(snapshot_dir, agreement_id)
    if not os.path.isdir(agreement_dir):
        return []

    # Find all version numbers
    versions = []
    for f in os.listdir(agreement_dir):
        if f.startswith("snapshot_v") and f.endswith(".json"):
            try:
                v = int(f.replace("snapshot_v", "").replace(".json", ""))
                versions.append(v)
            except ValueError:
                continue

    if not versions:
        return []

    max_version = max(versions)
    expected = set(range(max_version + 1))
    actual = set(versions)
    missing = sorted(expected - actual)

    if missing:
        logger.warning(
            "Snapshot chain for agreement %s has gaps at versions: %s",
            agreement_id,
            missing,
        )

    return missing


def extract_preamble_fields(preamble_text: str) -> dict:
    """Extract agreement-level fields from the document preamble.

    These are fields that apply to the entire agreement, not specific products.
    """
    import re

    fields = {}

    # Commencement date
    match = re.search(
        r"(?:commencement|effective)\s+date[^.]*?"
        r"(\d{1,2}/\d{1,2}/\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        preamble_text,
        re.IGNORECASE,
    )
    if match:
        fields["commencement_date"] = match.group(1)

    # Termination date
    match = re.search(
        r"terminat(?:ion|e)\s+date[^.]*?"
        r"(\d{1,2}/\d{1,2}/\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        preamble_text,
        re.IGNORECASE,
    )
    if match:
        fields["termination_date"] = match.group(1)

    # Payment terms
    match = re.search(
        r"(\d+)\s+(?:calendar\s+)?days?\s+(?:after|following)\s+receipt",
        preamble_text,
        re.IGNORECASE,
    )
    if match:
        fields["payment_terms_days"] = match.group(1)

    # Notice period
    match = re.search(
        r"(\d+)\s+(?:calendar\s+)?days?\s*(?:prior\s+)?(?:written\s+)?notice",
        preamble_text,
        re.IGNORECASE,
    )
    if match:
        fields["notice_period_days"] = match.group(1)

    return fields
