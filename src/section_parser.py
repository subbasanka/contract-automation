"""
Module 2: Section Parser
Splits full document text into individual Exhibit B product attachment sections.

Key design note: Section boundaries use robust markers (EXHIBIT B ATTACHMENT headers)
rather than heuristic length, to avoid cutting sections short when content like
Price Protection spans page boundaries.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Pattern to match Exhibit B Attachment headers
# Examples:
#   "EXHIBIT B, ATTACHMENT 1"
#   "EXHIBIT B ATTACHMENT 2"
#   "Exhibit B, Attachment 3"
EXHIBIT_B_PATTERN = re.compile(
    r"EXHIBIT\s+B[,\s]+ATTACHMENT\s+(\d+)",
    re.IGNORECASE,
)

# Pattern to detect "deleted and replaced" language
DELETED_REPLACED_PATTERN = re.compile(
    r"(?:hereby\s+)?deleted\s+in\s+its\s+entirety\s+and\s+replaced\s+with",
    re.IGNORECASE,
)

# Pattern to extract the product name from an attachment section
PRODUCT_NAME_PATTERN = re.compile(
    r'["\u201c]Product["\u201d]\s+shall\s+mean\s+(.+?)(?:\.|,|\s+marketed)',
    re.IGNORECASE,
)

# Alternative product name pattern from section header
PRODUCT_HEADER_PATTERN = re.compile(
    r"ATTACHMENT\s+\d+\s*[-\u2013\u2014:]\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)


def find_exhibit_b_boundaries(text: str) -> list[dict]:
    """Find all Exhibit B Attachment boundaries in the text.

    Returns a list of dicts with:
      - attachment_number: int
      - start: character offset of the match
      - header_text: the matched header string
    """
    boundaries = []
    for match in EXHIBIT_B_PATTERN.finditer(text):
        boundaries.append({
            "attachment_number": int(match.group(1)),
            "start": match.start(),
            "header_text": match.group(0),
        })
    return boundaries


def split_into_sections(text: str) -> list[dict]:
    """Split document text into Exhibit B Attachment sections.

    Each section extends from its EXHIBIT B ATTACHMENT header to the start of
    the next EXHIBIT B ATTACHMENT header (or end of document). This ensures
    that content spanning page boundaries (like Price Protection) is not cut off.

    Returns a list of dicts with:
      - attachment_number: int
      - text: full section text
      - product_name: extracted product name (if found)
      - is_replacement: bool (True if section uses "deleted and replaced" language)
    """
    boundaries = find_exhibit_b_boundaries(text)

    if not boundaries:
        logger.warning(
            "No Exhibit B Attachment boundaries found. "
            "Treating entire document as a single section."
        )
        return [{
            "attachment_number": 0,
            "text": text,
            "product_name": _extract_product_name(text),
            "is_replacement": bool(DELETED_REPLACED_PATTERN.search(text)),
        }]

    sections = []
    for i, boundary in enumerate(boundaries):
        start = boundary["start"]
        end = boundaries[i + 1]["start"] if i + 1 < len(boundaries) else len(text)
        section_text = text[start:end].strip()

        sections.append({
            "attachment_number": boundary["attachment_number"],
            "text": section_text,
            "product_name": _extract_product_name(section_text),
            "is_replacement": bool(DELETED_REPLACED_PATTERN.search(section_text)),
        })

    logger.info("Found %d Exhibit B Attachment section(s).", len(sections))
    return sections


def _extract_product_name(section_text: str) -> str | None:
    """Extract the product name from a section's text."""
    # Try the "Product shall mean" pattern first
    match = PRODUCT_NAME_PATTERN.search(section_text)
    if match:
        name = match.group(1).strip().strip('""\u201c\u201d')
        return _normalize_product_name(name)

    # Fall back to header pattern: "ATTACHMENT N - ProductName"
    match = PRODUCT_HEADER_PATTERN.search(section_text)
    if match:
        name = match.group(1).strip().strip('""\u201c\u201d')
        return _normalize_product_name(name)

    return None


def _normalize_product_name(name: str) -> str:
    """Normalize product name for consistent comparison."""
    # Remove trademark symbols, extra whitespace
    name = re.sub(r"[®™©]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.upper()


def parse_amendment_sections(text: str) -> dict:
    """Parse a full amendment document into structured sections.

    Returns a dict with:
      - preamble: text before the first Exhibit B Attachment (contains agreement-level changes)
      - sections: list of Exhibit B Attachment section dicts
    """
    boundaries = find_exhibit_b_boundaries(text)

    if boundaries:
        preamble = text[: boundaries[0]["start"]].strip()
    else:
        preamble = text

    sections = split_into_sections(text)

    return {
        "preamble": preamble,
        "sections": sections,
    }
