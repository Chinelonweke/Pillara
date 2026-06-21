# scripts/seed_drug_data.py
#
# Fetches drug label data from the FDA's openFDA API and ingests it into ChromaDB.
# Run this once at setup, and weekly via a scheduled job to keep data fresh.
#
# USAGE:
#   python scripts/seed_drug_data.py
#   python scripts/seed_drug_data.py --drugs ibuprofen,warfarin,metformin

import argparse
import asyncio
import sys

import httpx
import chromadb
from chromadb.config import Settings as ChromaSettings

sys.path.insert(0, ".")  # allow imports from project root when run as a script

from core.config import settings
from ai.rag.chunker import HierarchicalChunker
from monitoring.logger import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# Common drugs to seed initially — expand this list as needed
DEFAULT_DRUG_LIST = [
    "ibuprofen", "acetaminophen", "aspirin", "warfarin", "metformin",
    "amoxicillin", "lisinopril", "atorvastatin", "metoprolol", "omeprazole",
    "amlodipine", "simvastatin", "losartan", "gabapentin", "hydrochlorothiazide",
    "sertraline", "furosemide", "prednisone", "tramadol", "fluoxetine",
]


async def fetch_fda_label(drug_name: str) -> dict | None:
    """
    Fetches drug label data from openFDA.
    API docs: https://open.fda.gov/apis/drug/label/
    """
    url = f"{settings.FDA_API_BASE_URL}/label.json"
    params = {
        "search": f'openfda.generic_name:"{drug_name}"',
        "limit": 1,
    }
    if settings.FDA_API_KEY:
        params["api_key"] = settings.FDA_API_KEY

    async with httpx.AsyncClient(timeout=settings.FDA_API_TIMEOUT) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return results[0] if results else None
        except httpx.HTTPStatusError as error:
            logger.warning("fda_fetch_failed", drug_name=drug_name, no_phi_context=True, status=error.response.status_code)
            return None
        except Exception as error:
            logger.error("fda_fetch_error", drug_name=drug_name, no_phi_context=True, error=str(error))
            return None


def extract_sections(label_data: dict) -> dict:
    """
    Extracts relevant sections from the FDA label JSON.
    openFDA returns arrays of strings for each section — we join them.
    """
    def get_text(field: str) -> str:
        values = label_data.get(field, [])
        return " ".join(values) if values else ""

    return {
        "general": get_text("description") or get_text("indications_and_usage"),
        "drug_interactions": get_text("drug_interactions"),
        "side_effects": get_text("adverse_reactions"),
        "dosing": get_text("dosage_and_administration"),
        "warnings": get_text("warnings") or get_text("boxed_warning"),
    }


async def ingest_drug(
    drug_name: str,
    collection,
    chunker: HierarchicalChunker,
) -> int:
    """Fetches, chunks, and ingests one drug into ChromaDB. Returns chunk count."""
    label_data = await fetch_fda_label(drug_name)

    if not label_data:
        logger.warning("drug_not_found_in_fda", drug_name=drug_name, no_phi_context=True)
        return 0

    sections = extract_sections(label_data)

    if not any(sections.values()):
        logger.warning("drug_no_usable_sections", drug_name=drug_name, no_phi_context=True)
        return 0

    chunks = chunker.process_drug_document(drug_name=drug_name, sections=sections)

    if not chunks:
        return 0

    # Add to ChromaDB
    # ChromaDB's add() handles embedding automatically using its default embedding function
    # For production, configure ChromaDB to use fastembed explicitly for consistency
    collection.add(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "drug_name": c.drug_name,
                "section": c.section,
                "chunk_level": c.chunk_level,
                "source": c.source,
                "severity_flag": c.severity_flag,
                "ingestion_date": c.ingestion_date,
            }
            for c in chunks
        ],
    )

    logger.info("drug_ingested", drug_name=drug_name, no_phi_context=True, chunk_count=len(chunks))
    return len(chunks)


async def main(drug_list: list[str]) -> None:
    chroma_client = chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = chroma_client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    chunker = HierarchicalChunker()

    total_chunks = 0
    succeeded = 0
    failed = 0

    for drug_name in drug_list:
        try:
            chunk_count = await ingest_drug(drug_name, collection, chunker)
            if chunk_count > 0:
                succeeded += 1
                total_chunks += chunk_count
            else:
                failed += 1
        except Exception as error:
            logger.error("drug_ingestion_failed", drug_name=drug_name, no_phi_context=True, error=str(error))
            failed += 1

        # Be respectful of the FDA API rate limits
        await asyncio.sleep(0.5)

    logger.info(
        "ingestion_complete",
        total_drugs=len(drug_list),
        succeeded=succeeded,
        failed=failed,
        total_chunks=total_chunks,
    )
    print(f"\nDone. {succeeded}/{len(drug_list)} drugs ingested, {total_chunks} total chunks.")
    if failed:
        print(f"{failed} drugs could not be fetched from FDA — check logs for details.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Pillara's drug knowledge base from FDA data")
    parser.add_argument(
        "--drugs",
        type=str,
        help="Comma-separated list of drug names. If omitted, uses the default list.",
    )
    args = parser.parse_args()

    drugs = args.drugs.split(",") if args.drugs else DEFAULT_DRUG_LIST
    drugs = [d.strip().lower() for d in drugs if d.strip()]

    asyncio.run(main(drugs))