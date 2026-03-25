"""
Pipeline Orchestrator
Coordinates all six stages: ingestion -> parsing -> extraction -> snapshot -> delta -> report.
"""

import os
import logging

from .ingestion import ingest_document
from .section_parser import parse_amendment_sections
from .field_extractor import extract_fields
from .snapshot import build_snapshot, save_snapshot, extract_preamble_fields
from .delta_engine import compare_snapshots
from .report_writer import generate_report

logger = logging.getLogger(__name__)


def process_amendment(
    pdf_path: str,
    snapshot_dir: str = "snapshots",
    output_dir: str = "output",
) -> dict:
    """Process a single amendment PDF through the full pipeline.

    Args:
        pdf_path: Path to the amendment PDF.
        snapshot_dir: Directory for storing/loading snapshots.
        output_dir: Directory for output Excel reports.

    Returns:
        Dict with processing results:
          - output_file: path to generated xlsx
          - agreement_id: the agreement number
          - amendment_number: the amendment version
          - delta_summary: human-readable summary
          - snapshot_path: path to saved snapshot
    """
    os.makedirs(output_dir, exist_ok=True)

    # Stage 1: Document Ingestion
    logger.info("Stage 1: Ingesting document: %s", pdf_path)
    doc = ingest_document(pdf_path, snapshot_dir)

    if doc["ocr_needed"]:
        logger.warning(
            "Document may require OCR. Proceeding with available text, "
            "but results may be incomplete."
        )

    # Stage 2: Section Parsing
    logger.info("Stage 2: Parsing sections...")
    parsed = parse_amendment_sections(doc["full_text"])

    # Stage 3: Field Extraction
    logger.info("Stage 3: Extracting fields from %d section(s)...", len(parsed["sections"]))
    extracted_products = []
    for section in parsed["sections"]:
        fields = extract_fields(
            section_text=section["text"],
            preamble_text=parsed["preamble"],
            agreement_id=doc["agreement_id"],
            amendment_number=doc["amendment_number"],
        )
        extracted_products.append(fields)
        logger.info(
            "  Extracted: %s (rebate: %s)",
            fields.get("Product", "UNKNOWN"),
            fields.get("Tier Benefit / Base Rebate %", "N/A"),
        )

    # Stage 4: Snapshot Building
    logger.info("Stage 4: Building snapshot...")
    preamble_fields = extract_preamble_fields(parsed["preamble"])
    company_name = extracted_products[0].get("Company", "UNKNOWN") if extracted_products else "UNKNOWN"

    new_snapshot = build_snapshot(
        extracted_products=extracted_products,
        agreement_id=doc["agreement_id"],
        amendment_number=doc["amendment_number"],
        company_name=company_name,
        preamble_fields=preamble_fields,
        prior_snapshot=doc["prior_snapshot"],
    )

    snapshot_path = save_snapshot(new_snapshot, snapshot_dir)

    # Stage 5: Delta Comparison
    logger.info("Stage 5: Computing delta...")
    delta = compare_snapshots(doc["prior_snapshot"], new_snapshot)
    logger.info("  Delta: %s", delta["summary"])

    # Stage 6: Report Generation
    logger.info("Stage 6: Generating report...")
    output_filename = (
        f"query_6_{doc['agreement_id']}_v{doc['amendment_number']}.xlsx"
    )
    output_path = os.path.join(output_dir, output_filename)
    report_path = generate_report(delta, new_snapshot, output_path)

    logger.info("Pipeline complete. Report: %s", report_path)

    return {
        "output_file": report_path,
        "agreement_id": doc["agreement_id"],
        "amendment_number": doc["amendment_number"],
        "delta_summary": delta["summary"],
        "snapshot_path": snapshot_path,
        "delta": delta,
    }


def process_contract_chain(
    pdf_paths: list[str],
    snapshot_dir: str = "snapshots",
    output_dir: str = "output",
) -> list[dict]:
    """Process a sequence of contract PDFs (original + amendments) in order.

    Args:
        pdf_paths: List of PDF paths, ordered by version (original first).
        snapshot_dir: Directory for storing/loading snapshots.
        output_dir: Directory for output Excel reports.

    Returns:
        List of processing result dicts, one per document.
    """
    results = []
    for i, pdf_path in enumerate(pdf_paths):
        logger.info(
            "Processing document %d of %d: %s",
            i + 1,
            len(pdf_paths),
            pdf_path,
        )
        result = process_amendment(pdf_path, snapshot_dir, output_dir)
        results.append(result)
        logger.info("  Result: %s", result["delta_summary"])

    return results
