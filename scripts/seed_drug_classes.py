# scripts/seed_drug_classes.py
#
# Entry point for the drug class knowledge pipeline.
# Run this manually or via GitHub Actions (weekly schedule).
#
# USAGE:
#   python scripts/seed_drug_classes.py           # seed all drug classes
#   python scripts/seed_drug_classes.py --dry-run # preview without writing
#
# WHAT IT DOES:
# Runs workers/drug_class_pipeline.py which:
# 1. Takes 10 major drug classes (Penicillins, Sulfonamides, NSAIDs, etc.)
# 2. Enriches each with live RxNorm API data (member drugs, class IDs)
# 3. Converts structured data into readable clinical text
# 4. Chunks text by section (mechanism, adverse effects, cross-reactivity etc.)
# 5. Upserts into ChromaDB — safe to run repeatedly, no duplicates
#
# After running this, the AI chat can answer:
# - "What are sulfonamides?"
# - "How do beta-blockers work?"
# - "What drug class is metformin?"
# - "What are the side effects of ACE inhibitors?"
# - "Can I take an NSAID if I'm on a beta-blocker?"

import asyncio
import sys

sys.path.insert(0, ".")

from workers.drug_class_pipeline import run_pipeline
from monitoring.logger import configure_logging

configure_logging()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed Pillara ChromaDB with drug class knowledge from RxNorm + MedRT"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be seeded without writing to ChromaDB",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN — no data will be written to ChromaDB\n")

    result = asyncio.run(run_pipeline(dry_run=args.dry_run))

    print(f"\n{'='*50}")
    print(f"Classes processed: {result['classes_processed']}")
    print(f"Chunks upserted:   {result['chunks_upserted']}")
    if result["classes_failed"]:
        print(f"FAILED:            {', '.join(result['classes_failed'])}")
    if result["dry_run"]:
        print("\nThis was a dry run. Run without --dry-run to seed ChromaDB.")
    else:
        print("\nChromaDB updated. AI chat will now answer educational questions.")
    print("="*50)
