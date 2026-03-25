"""
Module 1: Document Ingestion
Accepts amendment PDFs, extracts raw text, identifies contract, loads latest snapshot.
"""

import os
import re
import json
import logging
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

# Minimum characters on page 1 to consider the PDF digitally readable
OCR_THRESHOLD = 50


def extract_text_from_pdf(pdf_path: str) -> list[str]:
    """Extract text from each page of a PDF.

    Returns a list of strings, one per page.
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return pages


def check_ocr_needed(pages: list[str]) -> bool:
    """Check if OCR is needed by examining the first page text length."""
    if not pages:
        return True
    first_page_text = pages[0].strip()
    if len(first_page_text) < OCR_THRESHOLD:
        logger.warning(
            "First page has only %d characters — document may be scanned. "
            "OCR fallback recommended.",
            len(first_page_text),
        )
        return True
    return False


def extract_agreement_number(full_text: str) -> str | None:
    """Extract the agreement number from the document text.

    Handles patterns like:
      - "Agreement No. 0090909"
      - "Agreement Number 0090909"
      - "formerly Agreement No. 0012345"
    """
    # Primary pattern
    match = re.search(
        r"Agreement\s+No\.?\s*[:;]?\s*(\d{5,})",
        full_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    # Alternative pattern with "Number"
    match = re.search(
        r"Agreement\s+Number\s*[:;]?\s*(\d{5,})",
        full_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    return None


def extract_amendment_number(full_text: str) -> int | None:
    """Extract the amendment number from the document text.

    Returns 0 for the original contract, or the amendment number (1, 2, ...).
    Returns None if the amendment number cannot be determined.
    """
    match = re.search(
        r"Amendment\s+No\.?\s*[:;]?\s*(\d+)",
        full_text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))

    # Check if this is an original agreement (no amendment mention)
    if re.search(r"(rebate\s+agreement|master\s+agreement)", full_text, re.IGNORECASE):
        if not re.search(r"amendment", full_text, re.IGNORECASE):
            return 0

    return None


def get_latest_snapshot(snapshot_dir: str, agreement_id: str) -> dict | None:
    """Load the latest snapshot for a given agreement ID.

    Snapshots are stored as snapshot_v{N}.json in the agreement's directory.
    Returns the parsed JSON dict, or None if no snapshots exist.
    """
    agreement_dir = os.path.join(snapshot_dir, agreement_id)
    if not os.path.isdir(agreement_dir):
        return None

    snapshot_files = sorted(
        [
            f
            for f in os.listdir(agreement_dir)
            if f.startswith("snapshot_v") and f.endswith(".json")
        ],
        key=lambda f: int(re.search(r"v(\d+)", f).group(1)),
    )

    if not snapshot_files:
        return None

    latest_file = os.path.join(agreement_dir, snapshot_files[-1])
    logger.info("Loading latest snapshot: %s", latest_file)
    with open(latest_file, "r", encoding="utf-8") as fh:
        return json.load(fh)


def ingest_document(
    pdf_path: str,
    snapshot_dir: str = "snapshots",
) -> dict:
    """Main ingestion entry point.

    Returns a dict with:
      - pages: list of page text strings
      - full_text: concatenated text
      - agreement_id: extracted agreement number
      - amendment_number: int (0 = original)
      - ocr_needed: bool
      - prior_snapshot: dict or None
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = extract_text_from_pdf(pdf_path)
    ocr_needed = check_ocr_needed(pages)
    full_text = "\n".join(pages)

    agreement_id = extract_agreement_number(full_text)
    if not agreement_id:
        raise ValueError(
            "Could not extract agreement number from document. "
            "Please check the PDF contains a valid agreement header."
        )

    amendment_number = extract_amendment_number(full_text)
    if amendment_number is None:
        logger.warning("Could not determine amendment number; defaulting to 0.")
        amendment_number = 0

    prior_snapshot = None
    if amendment_number > 0:
        prior_snapshot = get_latest_snapshot(snapshot_dir, agreement_id)
        if prior_snapshot is None:
            logger.warning(
                "No prior snapshot found for agreement %s. "
                "Delta comparison will treat all fields as new.",
                agreement_id,
            )

    return {
        "pages": pages,
        "full_text": full_text,
        "agreement_id": agreement_id,
        "amendment_number": amendment_number,
        "ocr_needed": ocr_needed,
        "prior_snapshot": prior_snapshot,
    }
