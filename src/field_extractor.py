"""
Module 3: Field Extraction (Regex-based)
Extracts the 22 query_6 fields from each product section using regex patterns.
"""

import re
import hashlib
import logging

logger = logging.getLogger(__name__)


def extract_fields(
    section_text: str,
    preamble_text: str,
    agreement_id: str,
    amendment_number: int,
    company_name: str | None = None,
) -> dict:
    """Extract all 22 query_6 fields from a product section.

    Args:
        section_text: The Exhibit B Attachment text for this product.
        preamble_text: The preamble/header text of the document.
        agreement_id: The agreement number.
        amendment_number: 0 for original, 1+ for amendments.
        company_name: Company name if already known.

    Returns:
        Dict with all 22 query_6 fields.
    """
    if not company_name:
        company_name = _extract_company_name(preamble_text)

    product_name = _extract_product_name(section_text)
    formulary_status = _extract_formulary_status(section_text)
    base_rebate_pct = _extract_base_rebate(section_text, formulary_status)
    price_threshold = _extract_price_protection_threshold(section_text)
    start_date, end_date = _extract_term_dates(section_text)
    payment_terms = _extract_payment_terms(preamble_text)
    admin_fee = _extract_admin_fee(section_text, preamble_text)
    frequency = _extract_frequency(section_text, preamble_text)

    # Derived fields
    company_short = _shorten_company(company_name) if company_name else "UNKNOWN"
    amendment_label = "K" if amendment_number == 0 else str(amendment_number)
    sap_id = f"{company_short}-Comm-{agreement_id}-{agreement_id}"
    program_name = _build_program_name(product_name, formulary_status, frequency)

    # Definition hashes for change detection
    definition_hash = _hash_definitions(section_text)

    return {
        "SAPID": sap_id,
        "Amendment #": amendment_label,
        "Contract #": agreement_id,
        "Company": company_name or "UNKNOWN",
        "Program Name": program_name,
        "Product": product_name or "UNKNOWN",
        "Formulary Status / BoB": formulary_status or "UNKNOWN",
        "Tier Benefit / Base Rebate %": base_rebate_pct,
        "Price Increase Threshold %": price_threshold,
        "Program Start Date": start_date or "",
        "Program End Date": end_date or "",
        "Payment Terms (Days)": payment_terms,
        "Admin Fee %": admin_fee,
        "Frequency": frequency or "Semi-Annual",
        "Commencement Date": _extract_commencement_date(preamble_text) or "",
        "Termination Date": _extract_termination_date(preamble_text) or "",
        "Notice Period (Days)": _extract_notice_period(preamble_text),
        "Minimum Rebate": _extract_minimum_rebate(section_text),
        "Maximum Rebate": _extract_maximum_rebate(section_text),
        "Market Share Requirement": _extract_market_share(section_text),
        "Definition Hash": definition_hash,
        "Notes": "",
    }


# --- Individual field extraction functions ---


def _extract_company_name(text: str) -> str | None:
    """Extract company name from preamble."""
    patterns = [
        r"between\s+(.+?)\s+(?:\(|and\s+)",
        r"by\s+and\s+between\s+(.+?)\s+\(",
        r"entered\s+into\s+by\s+(.+?)\s+(?:and|\()",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().strip(",")
            # Clean up common suffixes already in name
            return name
    return None


def _extract_product_name(text: str) -> str | None:
    """Extract product name from section text."""
    patterns = [
        r'["\u201c]Product["\u201d]\s+shall\s+mean\s+(.+?)(?:\.|,|\s+marketed)',
        r'["\u201c]Product["\u201d]\s+means\s+(.+?)(?:\.|,|\s+marketed)',
        r"Product:\s*(.+?)(?:\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().strip('""\u201c\u201d')
            name = re.sub(r"[®™©]", "", name)
            return name.strip()
    return None


def _extract_formulary_status(text: str) -> str | None:
    """Extract formulary status from section text."""
    # Look for formulary status definitions
    status_patterns = [
        (r"EQUAL\s+STATUS", "Equal Status"),
        (r"PREFERRED\s+STATUS", "Preferred Status"),
        (r"EXCLUSIVE\s+STATUS", "Exclusive Status"),
        (r"NON[- ]?PREFERRED", "Non-Preferred"),
        (r"DISADVANTAGED", "Disadvantaged"),
    ]
    found_statuses = []
    for pattern, label in status_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            found_statuses.append(label)

    if found_statuses:
        return found_statuses[0]  # Primary status
    return None


def _extract_base_rebate(text: str, formulary_status: str | None) -> str | None:
    """Extract base rebate percentage.

    Looks for patterns like:
      - "EQUAL STATUS  10%"
      - "Base Rebate Percentage... 15%"
      - "rebate of ten percent (10%)"
    """
    # Pattern: STATUS  N%
    if formulary_status:
        status_key = formulary_status.upper().replace(" ", r"\s+")
        match = re.search(
            rf"{status_key}\s+(\d+(?:\.\d+)?)\s*%",
            text,
            re.IGNORECASE,
        )
        if match:
            return f"{match.group(1)}%"

    # Pattern: Base Rebate Percentage ... N%
    match = re.search(
        r"Base\s+Rebate\s+Percentage[^%]*?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}%"

    # Pattern: rebate of ... percent (N%)
    match = re.search(
        r"rebate\s+of\s+.*?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}%"

    # Generic: find any percentage near "rebate"
    match = re.search(
        r"rebate[^.]{0,80}?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}%"

    return None


def _extract_price_protection_threshold(text: str) -> str | None:
    """Extract price protection threshold percentage.

    Looks for patterns like:
      - "Price Protection Threshold Percentage... equals... percent (N%)"
      - "threshold... N%"
    Always extracts the numeric value in parentheses over the spelled-out word.
    """
    # Pattern with parenthetical number (preferred — handles text/number mismatches)
    match = re.search(
        r"Price\s+Protection\s+Threshold\s+Percentage[^.]*?"
        r"(?:equals|equal\s+to|means|shall\s+be)[^.]*?"
        r"\((\d+(?:\.\d+)?)\s*%\s*\)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return f"{match.group(1)}%"

    # Pattern without parentheses
    match = re.search(
        r"Price\s+Protection\s+Threshold\s+Percentage[^.]*?"
        r"(?:equals|equal\s+to|means|shall\s+be)\s+.*?"
        r"(\d+(?:\.\d+)?)\s*(?:%|percent)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return f"{match.group(1)}%"

    # Broader fallback
    match = re.search(
        r"Price\s+Protection[^.]*?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return f"{match.group(1)}%"

    return None


def _extract_term_dates(text: str) -> tuple[str | None, str | None]:
    """Extract program start and end dates from TERM section."""
    start_date = None
    end_date = None

    # Pattern: commence on DATE
    match = re.search(
        r"commence\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        start_date = _normalize_date(match.group(1))

    # Pattern: through DATE / until DATE / ending DATE / expire on DATE
    match = re.search(
        r"(?:through|until|ending|expire[s]?\s+on|end\s+on)\s+(\w+\s+\d{1,2},?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        end_date = _normalize_date(match.group(1))

    # Pattern: MM/DD/YYYY through MM/DD/YYYY
    match = re.search(
        r"(\d{1,2}/\d{1,2}/\d{4})\s+(?:through|to|-)\s+(\d{1,2}/\d{1,2}/\d{4})",
        text,
    )
    if match:
        start_date = start_date or match.group(1)
        end_date = end_date or match.group(2)

    return start_date, end_date


def _extract_commencement_date(text: str) -> str | None:
    """Extract agreement commencement date from preamble."""
    match = re.search(
        r"(?:commencement|effective)\s+date[^.]*?(\d{1,2}/\d{1,2}/\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        return _normalize_date(match.group(1))
    return None


def _extract_termination_date(text: str) -> str | None:
    """Extract agreement termination date from preamble."""
    match = re.search(
        r"terminat(?:ion|e)[^.]*?(\d{1,2}/\d{1,2}/\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        return _normalize_date(match.group(1))
    return None


def _extract_payment_terms(text: str) -> str | None:
    """Extract payment terms (days) from preamble."""
    match = re.search(
        r"(\d+)\s+(?:calendar\s+)?days?\s+(?:after|following|of)\s+receipt",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    match = re.search(
        r"payment[^.]*?(\d+)\s+(?:calendar\s+)?days",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)

    return None


def _extract_admin_fee(text: str, preamble: str) -> str | None:
    """Extract administrative fee percentage."""
    combined = text + "\n" + preamble
    match = re.search(
        r"admin(?:istrative|istration)?\s+fee[^.]*?(\d+(?:\.\d+)?)\s*%",
        combined,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}%"
    return None


def _extract_frequency(text: str, preamble: str) -> str | None:
    """Extract reporting/rebate frequency."""
    combined = text + "\n" + preamble
    freq_patterns = [
        (r"semi[- ]?annual", "Semi-Annual"),
        (r"quarterly", "Quarterly"),
        (r"monthly", "Monthly"),
        (r"annual(?!.*semi)", "Annual"),
    ]
    for pattern, label in freq_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            return label
    return None


def _extract_notice_period(text: str) -> str | None:
    """Extract notice period in days."""
    match = re.search(
        r"(\d+)\s+(?:calendar\s+)?days?\s*(?:prior\s+)?(?:written\s+)?notice",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def _extract_minimum_rebate(text: str) -> str | None:
    """Extract minimum rebate if specified."""
    match = re.search(
        r"minimum\s+rebate[^.]*?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}%"
    return None


def _extract_maximum_rebate(text: str) -> str | None:
    """Extract maximum rebate if specified."""
    match = re.search(
        r"maximum\s+rebate[^.]*?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}%"
    return None


def _extract_market_share(text: str) -> str | None:
    """Extract market share requirement if specified."""
    match = re.search(
        r"market\s+share[^.]*?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}%"
    return None


def _hash_definitions(text: str) -> str:
    """Create a hash of the definitions section for change detection."""
    # Extract definitions block
    match = re.search(
        r"DEFINITIONS(.+?)(?:TERM|REBATE|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        definitions_text = match.group(1).strip()
    else:
        definitions_text = text[:2000]  # Use first 2000 chars as fallback

    # Normalize whitespace and case for consistent hashing
    normalized = re.sub(r"\s+", " ", definitions_text).strip().lower()
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def _normalize_date(date_str: str) -> str:
    """Normalize date string to MM/DD/YYYY format."""
    # Already in MM/DD/YYYY
    if re.match(r"\d{1,2}/\d{1,2}/\d{4}", date_str):
        return date_str

    # Month name format: "January 1, 2025" or "January 1 2025"
    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
    }
    match = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", date_str)
    if match:
        month_name = match.group(1).lower()
        day = match.group(2).zfill(2)
        year = match.group(3)
        month = months.get(month_name, "01")
        return f"{month}/{day}/{year}"

    return date_str


def _shorten_company(name: str) -> str:
    """Create a short company identifier."""
    # Remove common suffixes
    short = re.sub(
        r"\s*(Inc\.?|LLC|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|L\.?P\.?)$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    # Take first word
    parts = short.split()
    return parts[0] if parts else "UNKNOWN"


def _build_program_name(
    product: str | None,
    status: str | None,
    frequency: str | None,
) -> str:
    """Build the program name in format: Product_Status_S.Freq.O"""
    product_part = product or "UNKNOWN"
    status_part = status or "Unknown"
    freq_short = "S.A" if frequency == "Semi-Annual" else frequency[:1] if frequency else "S.A"
    return f"{product_part}_{status_part}_{freq_short}.O"
