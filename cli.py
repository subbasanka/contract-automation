"""
CLI interface for the Contract Amendment Delta Automation pipeline.

Usage:
    # Process a single amendment
    python cli.py process path/to/amendment.pdf

    # Process original + amendment(s) in sequence
    python cli.py chain path/to/original.pdf path/to/amendment1.pdf path/to/amendment2.pdf

    # Options
    python cli.py process amendment.pdf --snapshot-dir ./snapshots --output-dir ./output
"""

import argparse
import logging
import sys

from src.pipeline import process_amendment, process_contract_chain


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_process(args):
    """Process a single amendment PDF."""
    result = process_amendment(
        pdf_path=args.pdf,
        snapshot_dir=args.snapshot_dir,
        output_dir=args.output_dir,
    )
    print(f"\n{'='*60}")
    print(f"Agreement:  {result['agreement_id']}")
    print(f"Amendment:  {result['amendment_number']}")
    print(f"Delta:      {result['delta_summary']}")
    print(f"Report:     {result['output_file']}")
    print(f"Snapshot:   {result['snapshot_path']}")
    print(f"{'='*60}")


def cmd_chain(args):
    """Process a chain of contract PDFs in order."""
    results = process_contract_chain(
        pdf_paths=args.pdfs,
        snapshot_dir=args.snapshot_dir,
        output_dir=args.output_dir,
    )
    print(f"\n{'='*60}")
    print(f"Processed {len(results)} document(s):")
    for r in results:
        print(f"  v{r['amendment_number']}: {r['delta_summary']}")
        print(f"         Report: {r['output_file']}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Contract Amendment Delta Automation Pipeline",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'process' command — single PDF
    proc_parser = subparsers.add_parser(
        "process",
        help="Process a single amendment PDF",
    )
    proc_parser.add_argument("pdf", help="Path to the amendment PDF")
    proc_parser.add_argument(
        "--snapshot-dir", default="snapshots",
        help="Directory for snapshots (default: ./snapshots)",
    )
    proc_parser.add_argument(
        "--output-dir", default="output",
        help="Directory for output reports (default: ./output)",
    )

    # 'chain' command — multiple PDFs
    chain_parser = subparsers.add_parser(
        "chain",
        help="Process a chain of PDFs (original + amendments in order)",
    )
    chain_parser.add_argument(
        "pdfs", nargs="+",
        help="PDF paths in version order (original first)",
    )
    chain_parser.add_argument(
        "--snapshot-dir", default="snapshots",
        help="Directory for snapshots (default: ./snapshots)",
    )
    chain_parser.add_argument(
        "--output-dir", default="output",
        help="Directory for output reports (default: ./output)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "process":
        cmd_process(args)
    elif args.command == "chain":
        cmd_chain(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
