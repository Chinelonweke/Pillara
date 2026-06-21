# ai/rag/chunker.py
#
# Implements the chunking strategy decided earlier:
# 1. Semantic chunking (split by meaning, not character count)
# 2. Three-level hierarchical chunking (document → section → atomic fact)
# 3. Metadata-enriched chunks
# 4. Atomic interaction chunk format
#
# This file processes raw FDA drug label text into chunks ready for ChromaDB.

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Chunk:
    """A single chunk ready for embedding and storage in ChromaDB."""
    text: str
    chunk_id: str
    drug_name: str
    section: str
    chunk_level: int  # 1=document, 2=section, 3=atomic fact
    source: str = "fda_label"
    severity_flag: str = ""
    ingestion_date: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )


class SemanticChunker:
    """
    Splits drug documents into meaningful chunks.

    SPLIT PRIORITY (highest to lowest):
    1. Major section headers ("## ")
    2. Sub-section headers ("### ")
    3. Paragraph breaks ("\\n\\n")
    4. Line breaks ("\\n")
    5. Sentence boundaries (". ") — last resort only

    WHY THIS ORDER:
    Splitting at a section boundary never breaks a thought mid-sentence.
    Splitting at sentence boundaries (last resort) risks separating
    related sentences, which is why overlap exists as a safety net.
    """

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP

    def _estimate_tokens(self, text: str) -> int:
        """
        Rough token estimate: ~4 characters per token for English text.
        WHY ESTIMATE (not exact tokenizer):
        Exact tokenization requires loading a tokenizer model — slow for chunking.
        A 4-char approximation is accurate enough for chunk sizing decisions.
        """
        return len(text) // 4

    def split_by_separators(self, text: str) -> list[str]:
        """
        Recursively splits text using the separator priority list.
        Tries the highest-priority separator first; only falls back
        to lower-priority separators if chunks are still too large.
        """
        separators = ["\n\n## ", "\n\n### ", "\n\n", "\n", ". "]
        return self._recursive_split(text, separators)

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        if self._estimate_tokens(text) <= self.chunk_size:
            return [text]

        if not separators:
            # No more separators to try — hard split at character boundary
            char_limit = self.chunk_size * 4
            return [text[i:i + char_limit] for i in range(0, len(text), char_limit)]

        separator = separators[0]
        remaining_separators = separators[1:]

        parts = text.split(separator)
        chunks = []
        current_chunk = ""

        for part in parts:
            candidate = current_chunk + separator + part if current_chunk else part

            if self._estimate_tokens(candidate) <= self.chunk_size:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # This part alone might still be too big — recurse with next separator
                if self._estimate_tokens(part) > self.chunk_size:
                    chunks.extend(self._recursive_split(part, remaining_separators))
                    current_chunk = ""
                else:
                    current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def add_overlap(self, chunks: list[str]) -> list[str]:
        """
        Adds overlap between consecutive chunks.
        WHY: prevents information loss at chunk boundaries.
        Each chunk (except the first) includes the tail of the previous chunk.
        """
        if len(chunks) <= 1:
            return chunks

        overlapped = [chunks[0]]
        overlap_chars = self.chunk_overlap * 4  # convert tokens to approx chars

        for i in range(1, len(chunks)):
            previous_tail = chunks[i - 1][-overlap_chars:] if len(chunks[i - 1]) > overlap_chars else chunks[i - 1]
            overlapped.append(previous_tail + " " + chunks[i])

        return overlapped


class HierarchicalChunker:
    """
    Creates three levels of chunks for a drug document:
    Level 1: whole document summary
    Level 2: section-level chunks (~400 tokens)
    Level 3: atomic fact chunks (~80-100 tokens) — used for interactions

    USAGE:
        chunker = HierarchicalChunker()
        chunks = chunker.process_drug_document(
            drug_name="ibuprofen",
            sections={"interactions": "...", "side_effects": "...", "general": "..."}
        )
    """

    def __init__(self):
        self.semantic_chunker = SemanticChunker()

    def process_drug_document(
        self,
        drug_name: str,
        sections: dict,
        source: str = "fda_label",
    ) -> list[Chunk]:
        """
        sections: dict mapping section name to raw text
        e.g. {"general": "...", "drug_interactions": "...", "side_effects": "..."}

        Returns a flat list of Chunk objects across all three levels.
        """
        all_chunks = []
        chunk_counter = 0

        # LEVEL 1 — Document summary (concatenated short overview)
        summary_parts = [text[:300] for text in sections.values()]
        document_summary = " ".join(summary_parts)[:1000]
        all_chunks.append(Chunk(
            text=f"{drug_name.title()} Full Drug Profile: {document_summary}",
            chunk_id=f"{drug_name}_doc_{chunk_counter:03d}",
            drug_name=drug_name,
            section="document_summary",
            chunk_level=1,
            source=source,
        ))
        chunk_counter += 1

        # LEVEL 2 — Section-level chunks
        for section_name, section_text in sections.items():
            if not section_text or not section_text.strip():
                continue

            section_chunks = self.semantic_chunker.split_by_separators(section_text)
            section_chunks = self.semantic_chunker.add_overlap(section_chunks)

            for chunk_text in section_chunks:
                severity = self._detect_severity(chunk_text) if section_name == "drug_interactions" else ""
                all_chunks.append(Chunk(
                    text=chunk_text,
                    chunk_id=f"{drug_name}_{section_name}_{chunk_counter:03d}",
                    drug_name=drug_name,
                    section=section_name,
                    chunk_level=2,
                    source=source,
                    severity_flag=severity,
                ))
                chunk_counter += 1

        # LEVEL 3 — Atomic interaction facts (only for drug_interactions section)
        if "drug_interactions" in sections:
            atomic_chunks = self._extract_atomic_interactions(
                drug_name=drug_name,
                text=sections["drug_interactions"],
                source=source,
                start_counter=chunk_counter,
            )
            all_chunks.extend(atomic_chunks)

        logger.info(
            "drug_document_chunked",
            drug_name=drug_name,
            no_phi_context=True,
            # WHY no_phi_context=True HERE:
            # process_drug_document() is only ever called from
            # scripts/seed_drug_data.py against generic FDA reference data —
            # never from a live request handling a specific patient's
            # medication. Verified by grepping every call site in the
            # codebase before adding this flag. If this function is ever
            # called from a patient-facing code path in the future, this
            # flag should be removed at that point.
            total_chunks=len(all_chunks),
        )

        return all_chunks

    def _detect_severity(self, text: str) -> str:
        """Detects severity level from interaction text using keyword matching."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["contraindicated", "avoid", "severe", "life-threatening", "do not"]):
            return "high"
        elif any(kw in text_lower for kw in ["caution", "monitor", "moderate", "may increase"]):
            return "moderate"
        elif any(kw in text_lower for kw in ["minor", "mild", "unlikely"]):
            return "low"
        return ""

    def _extract_atomic_interactions(
        self,
        drug_name: str,
        text: str,
        source: str,
        start_counter: int,
    ) -> list[Chunk]:
        """
        Extracts individual drug-drug interaction facts in the structured atomic format:

        INTERACTION: DrugA + DrugB
        SEVERITY: HIGH/MODERATE/LOW
        MECHANISM: ...
        EFFECT: ...
        ACTION REQUIRED: ...
        SOURCE: ...

        WHY THIS FORMAT:
        Every key fact is on a labelled line. Even a partial chunk retrieval
        retains the most critical information (SEVERITY, ACTION REQUIRED).
        """
        chunks = []
        counter = start_counter

        # Split by common interaction delimiters (sentences mentioning "with")
        # This is a simplified extraction — in production, this would use
        # NER (Named Entity Recognition) to identify drug name pairs
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sentence in sentences:
            if len(sentence.strip()) < 20:
                continue

            severity = self._detect_severity(sentence)
            if not severity:
                continue  # only create atomic chunks for sentences with clear severity signals

            atomic_text = (
                f"INTERACTION: {drug_name.title()} drug interaction\n"
                f"SEVERITY: {severity.upper()}\n"
                f"DETAILS: {sentence.strip()}\n"
                f"SOURCE: {source}\n"
                f"ACTION REQUIRED: "
                + ("Avoid this combination unless under medical supervision."
                   if severity == "high"
                   else "Monitor closely and consult your doctor or pharmacist.")
            )

            chunks.append(Chunk(
                text=atomic_text,
                chunk_id=f"{drug_name}_interaction_atomic_{counter:03d}",
                drug_name=drug_name,
                section="drug_interactions",
                chunk_level=3,
                source=source,
                severity_flag=severity,
            ))
            counter += 1

        return chunks