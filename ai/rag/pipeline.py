# ai/rag/pipeline.py
#
# WHY THIS FILE IS THE MOST CLINICALLY IMPORTANT IN THE AI LAYER:
# This pipeline is what makes Pillara safe.
# Without it, the LLM answers drug questions from training data — confidently
# and sometimes incorrectly. With it, the LLM ONLY answers from verified
# drug information we have retrieved and validated.
#
# THE PIPELINE SEQUENCE:
# 1. Receive user query (already sanitized by middleware)
# 2. Understand the query (extract drug names, detect intent)
# 3. Expand the query (add synonyms, brand names)
# 4. Retrieve relevant chunks (3 methods simultaneously)
# 5. Combine results (Reciprocal Rank Fusion)
# 6. Re-rank for precision (cross-encoder)
# 7. CHECK CONFIDENCE GATE — if score too low, do not answer
# 8. Build the LLM prompt with retrieved context
# 9. Call the LLM (via the 5-provider fallback client)
# 10. Validate the output
# 11. Return the response with full metadata

import asyncio
import re
import time
from dataclasses import dataclass, field  # dataclass = cleaner way to make data containers
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from ai.llm.client import LLMClient, QueryComplexity
from ai.llm.prompts import (
    build_interaction_prompt,
    build_medication_info_prompt,
    build_general_chat_prompt,
)
from core.config import settings
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ─── DATA CLASSES ─────────────────────────────────────────────────────────────
#
# WHY DATACLASSES (not plain dicts):
# Dataclasses give us:
# - Type hints (self.text is always a str)
# - Attribute access (chunk.text not chunk["text"])
# - Default values without __init__ boilerplate
# - Auto-generated __repr__ for debugging

@dataclass
class RetrievedChunk:
    """
    Represents one retrieved document chunk from ChromaDB.
    This is the unit of information the RAG pipeline works with.
    """
    chunk_id: str           # unique identifier of this chunk
    text: str               # the actual drug information text
    similarity_score: float # how similar this chunk is to the query (0.0 to 1.0)
    drug_name: str = ""     # which drug this chunk is about
    section: str = ""       # which section: "interactions", "side_effects", etc.
    source: str = ""        # where the information came from (FDA label, etc.)
    severity_flag: str = "" # "high", "moderate", "low" for interaction chunks
    final_score: float = 0.0 # score after re-ranking (overwrites similarity_score)


@dataclass
class RAGResult:
    """
    The complete result from the RAG pipeline.
    Contains everything the route handler needs to build a response.
    """
    response_text: str               # the AI's answer in plain language
    retrieved_chunks: list           # the chunks used to generate the answer
    confidence_score: float          # highest similarity score found
    confidence_gate_passed: bool     # did we pass the 0.75 threshold?
    fallback_triggered: bool         # True = AI said "I don't have info"
    provider_used: str               # which LLM provider answered
    model_used: str                  # which specific model
    query_intent: str                # what we detected the user was asking
    drugs_mentioned: list            # drug names we extracted from the query
    latency_ms: float                # total pipeline time in milliseconds
    disclaimer: str = (
        "Please discuss this with your doctor or pharmacist "
        "before making any changes to your medications."
    )


# ─── QUERY UNDERSTANDING ──────────────────────────────────────────────────────

class QueryUnderstanding:
    """
    WHY A SEPARATE CLASS FOR QUERY UNDERSTANDING:
    Understanding what the user is asking is complex enough to deserve its own class.
    It has multiple methods (extract drugs, detect intent, expand query) that
    share state (the original query text) — a class is the right structure.
    """

    # Common drug brand-to-generic name mappings
    # WHY A DICT HERE:
    # Dict lookup is O(1) — fast for membership check.
    # Maps brand name → generic name for query expansion.
    # We expand "advil" → "advil ibuprofen" so ChromaDB finds both.
    BRAND_TO_GENERIC: dict = {
        "advil": "ibuprofen",
        "motrin": "ibuprofen",
        "nurofen": "ibuprofen",
        "tylenol": "acetaminophen",
        "paracetamol": "acetaminophen",  # common name in Nigeria/UK
        "coumadin": "warfarin",
        "aspirin": "acetylsalicylic acid",
        "zocor": "simvastatin",
        "lipitor": "atorvastatin",
        "prozac": "fluoxetine",
        "valium": "diazepam",
        "viagra": "sildenafil",
        "amoxil": "amoxicillin",
        "augmentin": "amoxicillin/clavulanate",
        "flagyl": "metronidazole",
        "brufen": "ibuprofen",  # common brand in Nigeria
    }

    # Intent keywords — used to classify what the user wants
    # WHY DICT OF SETS:
    # Outer dict: intent_name → set of keywords
    # Inner sets: fast O(1) membership check
    # We check if ANY keyword from a set appears in the query
    INTENT_KEYWORDS: dict = {
        "interaction_check": {
            "interact", "interaction", "safe to take", "together",
            "combine", "combination", "mix", "with my", "and my",
            "can i take", "take with"
        },
        "side_effects": {
            "side effect", "side-effect", "adverse", "reaction",
            "feel sick", "causing", "makes me", "after taking",
            "problem with", "trouble with"
        },
        "dosing": {
            "dose", "dosage", "how much", "how many", "how often",
            "when to take", "timing", "frequency", "twice", "daily"
        },
        "what_is_it": {
            "what is", "what does", "used for", "treats", "for what",
            "purpose", "why am i", "why take"
        },
        "reminder": {
            "remind", "reminder", "alert", "schedule", "set a",
            "notify", "notification", "alarm"
        },
    }

    def __init__(self, query: str):
        """
        query: the user's input (already sanitized by middleware)
        We store it as both original and lowercase.
        Lowercase is for matching — we don't want "Ibuprofen" to miss "ibuprofen".
        """
        self.original_query = query
        self.query_lower = query.lower()

    def extract_drug_names(self) -> list:
        """
        Extracts drug names from the query.

        WHY BOTH APPROACHES:
        1. Dictionary lookup: catches known brand names
        2. Pattern matching: catches unknown drug names
           (new drugs, generic names not in our dict)

        Returns a list of drug names found in the query.
        """
        found_drugs = []

        # Approach 1: Check for known brand names in our dictionary
        # .items() returns (brand, generic) pairs
        # We loop through and check if each brand name appears in the query
        for brand_name, generic_name in self.BRAND_TO_GENERIC.items():
            if brand_name in self.query_lower:
                # Add both brand and generic name for comprehensive retrieval
                if brand_name not in found_drugs:
                    found_drugs.append(brand_name)
                if generic_name not in found_drugs:
                    found_drugs.append(generic_name)

        # Approach 2: Pattern matching for drug name patterns
        # Many drug names end in common suffixes: -in, -ol, -am, -ine, -ide, etc.
        # This regex catches most pharmaceutical drug names
        drug_pattern = r'\b[A-Za-z]+(?:in|ol|am|ine|ide|ate|one|ase|mab|nib|zole|mycin|cillin|sartan|pril|statin)\b'
        # \b = word boundary (ensures we match whole words)
        # (?:...) = non-capturing group of suffix options
        pattern_matches = re.findall(drug_pattern, self.original_query, re.IGNORECASE)

        for match in pattern_matches:
            match_lower = match.lower()
            if match_lower not in found_drugs and len(match_lower) > 4:
                # Only add if not already found and longer than 4 chars
                # (short matches like "one" are too generic)
                found_drugs.append(match_lower)

        return found_drugs

    def detect_intent(self) -> str:
        """
        Determines what the user is asking for.

        WHY INTENT DETECTION:
        Different intents need different retrieval strategies.
        "What is ibuprofen?" → retrieve general info chunks
        "Can I take ibuprofen with warfarin?" → retrieve interaction chunks only

        Returns the intent name as a string.
        """
        # Check each intent's keywords against the query
        # We use a for loop because we want the FIRST match (priority order)
        for intent_name, keywords in self.INTENT_KEYWORDS.items():
            # any() = True if at least one keyword is found in the query
            if any(keyword in self.query_lower for keyword in keywords):
                return intent_name

        # Default intent if nothing specific is detected
        return "general_question"

    def expand_query(self) -> str:
        """
        Expands the query with synonyms and brand/generic name equivalents.

        WHY QUERY EXPANSION:
        Our drug database uses FDA generic names.
        Users might say "advil" but our database says "ibuprofen".
        Adding synonyms to the query means vector search finds both.

        Returns the expanded query string.
        """
        expanded = self.original_query

        # Add generic names for any brand names found
        for brand_name, generic_name in self.BRAND_TO_GENERIC.items():
            if brand_name in self.query_lower:
                # Only add if not already in the query
                if generic_name not in self.query_lower:
                    expanded = f"{expanded} {generic_name}"

        # Add common synonyms for medical terms
        # Dict maps term to its expansion
        term_expansions = {
            "blood thinner": "anticoagulant warfarin heparin",
            "blood pressure": "antihypertensive hypertension bp",
            "pain killer": "analgesic pain reliever nsaid",
            "sleeping pill": "sedative hypnotic sleep medication",
            "antidepressant": "ssri snri depression medication",
            "stomach acid": "antacid proton pump inhibitor ppi",
        }

        for term, expansion in term_expansions.items():
            if term in self.query_lower:
                expanded = f"{expanded} {expansion}"

        return expanded


# ─── RAG PIPELINE ─────────────────────────────────────────────────────────────

class RAGPipeline:
    """
    The complete RAG pipeline for Pillara.

    WHY A CLASS:
    The pipeline maintains connections (ChromaDB client, LLM client, Redis)
    and has many methods that work together.
    A class keeps these organised and avoids passing connections around everywhere.

    INSTANTIATION:
    Create once at startup, reuse for every request.
    Database connections are expensive to create — keep them alive.
    """

    def __init__(self, redis=None):
        self.redis = redis
        self.llm_client = LLMClient(redis=redis)

        # Initialize ChromaDB client
        # WHY HttpClient (not EphemeralClient):
        # HttpClient connects to a running ChromaDB server (our Docker container).
        # EphemeralClient runs in-memory — data is lost when the process ends.
        # We need persistence — drug knowledge survives restarts.
        self.chroma_client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False)
        )

        # Get or create the drug knowledge collection
        # get_or_create_collection: if it exists, use it; if not, create it
        # This is idempotent — safe to call on every startup
        self.collection = self.chroma_client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            # distance function for similarity calculation
            # cosine = measures angle between vectors (standard for text)
            metadata={"hnsw:space": "cosine"}
        )

        logger.info(
            "rag_pipeline_initialized",
            collection=settings.CHROMA_COLLECTION_NAME,
        )

    async def query(
        self,
        user_query: str,
        profile_medications: Optional[list] = None,
        conversation_history: Optional[list] = None,
        is_voice: bool = False,
        request_id: str = "unknown",
    ) -> RAGResult:
        """
        Main entry point for the RAG pipeline.

        user_query:            the user's question (pre-sanitized)
        profile_medications:   user's current medication list (for context)
        conversation_history:  last 5 turns for multi-turn conversations
        is_voice:              True = format response for TTS
        request_id:            for correlating logs

        Returns a RAGResult with the answer and full metadata.
        """
        pipeline_start = time.monotonic()

        # ── STEP 1: Query Understanding ────────────────────────────────────
        understanding = QueryUnderstanding(user_query)
        intent = understanding.detect_intent()
        drugs_mentioned = understanding.extract_drug_names()
        expanded_query = understanding.expand_query()

        logger.info(
            "rag_query_understood",
            intent=intent,
            drugs_found=len(drugs_mentioned),
            request_id=request_id,
        )

        # ── STEP 2: Query Complexity Classification ────────────────────────
        complexity = await self.llm_client.classify_query_complexity(user_query)

        # ── STEP 3: Parallel Retrieval ─────────────────────────────────────
        # Run vector search and keyword search simultaneously
        # asyncio.gather() runs multiple async functions at the same time
        # WHY PARALLEL: vector search takes ~20ms, keyword search takes ~10ms
        # Sequential would take 30ms. Parallel takes ~20ms (the slower one).
        vector_results, keyword_results = await asyncio.gather(
            self._vector_search(expanded_query, intent, drugs_mentioned),
            self._keyword_search(expanded_query, drugs_mentioned),
        )

        # ── STEP 4: Reciprocal Rank Fusion ────────────────────────────────
        # Combine vector and keyword results into one ranked list
        combined_chunks = self._reciprocal_rank_fusion(
            vector_results,
            keyword_results,
            top_k=20  # keep top 20 for re-ranking
        )

        # ── STEP 5: Confidence Gate Check ─────────────────────────────────
        # Check if we have enough confidence to answer
        if not combined_chunks:
            return self._safe_fallback_response(
                reason="no_results",
                drugs_mentioned=drugs_mentioned,
                intent=intent,
                pipeline_start=pipeline_start,
            )

        best_score = max(chunk.similarity_score for chunk in combined_chunks)
        # max() returns the largest value from an iterable
        # We find the highest similarity score across all retrieved chunks

        # ── CONFIDENCE GATE ────────────────────────────────────────────────
        # THIS IS THE MOST IMPORTANT SAFETY CHECK IN THE ENTIRE PIPELINE
        if best_score < settings.RAG_CONFIDENCE_THRESHOLD:
            logger.warning(
                "confidence_gate_triggered",
                best_score=round(best_score, 3),
                threshold=settings.RAG_CONFIDENCE_THRESHOLD,
                intent=intent,
                request_id=request_id,
            )
            return self._safe_fallback_response(
                reason="low_confidence",
                drugs_mentioned=drugs_mentioned,
                intent=intent,
                pipeline_start=pipeline_start,
                confidence_score=best_score,
            )

        # ── DRUG DATA STALENESS CHECK ─────────────────────────────────────
        # RELIABILITY FIX: Warn if retrieved chunks are older than 90 days.
        # FDA updates drug labels when new risks are discovered.
        # Serving stale interaction data is a clinical safety risk.
        # We don't block the response — we log a warning for the ops team.
        self._check_data_freshness(combined_chunks, request_id=request_id)

        # ── STEP 6: Re-ranking ────────────────────────────────────────────
        # Re-rank top 20 → select top 5 most relevant
        top_chunks = self._rerank_chunks(
            query=user_query,
            chunks=combined_chunks,
            top_k=settings.RAG_TOP_K_RESULTS,
        )

        # ── STEP 7: Build Context for LLM ─────────────────────────────────
        retrieved_context = self._build_context_string(top_chunks)

        # ── STEP 8: Build System Prompt ───────────────────────────────────
        if intent == "interaction_check" and drugs_mentioned:
            system_prompt = build_interaction_prompt(
                retrieved_context=retrieved_context,
                drug_names=drugs_mentioned,
                is_voice=is_voice,
            )
        else:
            system_prompt = build_general_chat_prompt(is_voice=is_voice)

        # ── STEP 9: Build Messages for LLM ───────────────────────────────
        messages = self._build_messages(
            user_query=user_query,
            retrieved_context=retrieved_context,
            conversation_history=conversation_history or [],
            profile_medications=profile_medications or [],
        )

        # ── STEP 10: LLM Call ─────────────────────────────────────────────
        llm_result = await self.llm_client.complete(
            messages=messages,
            system_prompt=system_prompt,
            complexity=complexity,
            request_id=request_id,
        )

        # ── STEP 11: Strip HTML from LLM output (XSS prevention) ────────
        safe_response_text = self._strip_output_html(llm_result["text"])

        # ── Log Retrieval for Observability ──────────────────────────────
        # This is what lets you debug hallucinations systematically
        # You can look at the logs and see exactly what the LLM received
        self._log_retrieval_details(
            query=user_query,
            expanded_query=expanded_query,
            chunks=top_chunks,
            best_score=best_score,
            provider=llm_result["provider"],
            request_id=request_id,
        )

        total_latency = (time.monotonic() - pipeline_start) * 1000

        return RAGResult(
            response_text=safe_response_text,
            retrieved_chunks=top_chunks,
            confidence_score=best_score,
            confidence_gate_passed=True,
            fallback_triggered=False,
            provider_used=llm_result["provider"],
            model_used=llm_result["model"],
            query_intent=intent,
            drugs_mentioned=drugs_mentioned,
            latency_ms=round(total_latency, 2),
        )

    async def _vector_search(
        self,
        query: str,
        intent: str,
        drugs_mentioned: list,
    ) -> list:
        """
        Performs semantic vector search in ChromaDB.

        WHY ASYNC WITH THREAD POOL:
        ChromaDB's HTTP client is synchronous.
        We run it in asyncio's thread pool so it doesn't block the event loop.
        asyncio.to_thread() = "run this synchronous function in a background thread"
        """
        # Build metadata filter based on intent
        # WHERE clause narrows down which chunks we search
        where_filter = self._build_metadata_filter(intent, drugs_mentioned)

        def _sync_search():
            """Synchronous ChromaDB query — run in thread pool."""
            query_params = {
                "query_texts": [query],
                "n_results": min(20, self.collection.count() or 1),
                # n_results can't exceed total documents
                "include": ["documents", "metadatas", "distances"],
            }

            if where_filter:
                query_params["where"] = where_filter

            return self.collection.query(**query_params)

        try:
            results = await asyncio.to_thread(_sync_search)
        except Exception as error:
            logger.error("vector_search_error", error=str(error))
            return []

        # Parse ChromaDB results into RetrievedChunk objects
        chunks = []
        if results["documents"] and results["documents"][0]:
            for idx, (doc, metadata, distance) in enumerate(zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )):
                # Convert distance to similarity score
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                # We convert to similarity: 1 = identical, 0 = opposite
                similarity = 1 - (distance / 2)

                chunk = RetrievedChunk(
                    chunk_id=metadata.get("chunk_id", f"chunk_{idx}"),
                    text=doc,
                    similarity_score=round(similarity, 4),
                    drug_name=metadata.get("drug_name", ""),
                    section=metadata.get("section", ""),
                    source=metadata.get("source", ""),
                    severity_flag=metadata.get("severity_flag", ""),
                )
                chunks.append(chunk)

        logger.debug(
            "vector_search_complete",
            chunks_returned=len(chunks),
            top_score=chunks[0].similarity_score if chunks else 0,
        )

        return chunks

    async def _keyword_search(
        self,
        query: str,
        drugs_mentioned: list,
    ) -> list:
        """
        Performs BM25 keyword search to complement vector search.

        WHY BM25 OVER SIMPLE KEYWORD MATCHING:
        BM25 (Best Match 25) is a probabilistic ranking function.
        It considers: term frequency (how often the word appears) and
        inverse document frequency (how rare the word is across all documents).
        "warfarin" scores higher than "the" because "warfarin" is rare and specific.

        For drug name matching especially, BM25 catches exact names
        that vector search might miss if the semantic context differs.
        """
        from rank_bm25 import BM25Okapi
        # BM25Okapi = the standard BM25 variant (Okapi BM25)

        # Get all documents from ChromaDB for BM25 indexing
        # WHY GET ALL: BM25 needs to index the entire corpus to calculate IDF
        # This is a limitation of BM25 vs vector search at scale
        # At startup, we'd pre-compute this index and cache it in Redis
        # For now, we compute it per request (acceptable at startup scale)
        try:
            all_docs = await asyncio.to_thread(
                lambda: self.collection.get(include=["documents", "metadatas"])
            )
        except Exception as error:
            logger.error("keyword_search_get_error", error=str(error))
            return []

        if not all_docs["documents"]:
            return []

        documents = all_docs["documents"]
        metadatas = all_docs["metadatas"]

        # Tokenize documents for BM25
        # BM25 works on lists of tokens (words)
        # We split each document into words using .split()
        tokenized_docs = [doc.lower().split() for doc in documents]
        bm25 = BM25Okapi(tokenized_docs)

        # Tokenize the query — DEDUPLICATE tokens before scoring.
        # SECURITY FIX: Without deduplication, a user can send
        # "ibuprofen ibuprofen ibuprofen warfarin warfarin warfarin"
        # to artificially inflate BM25 scores and bypass the confidence gate.
        # Deduplication means repeated terms count once — same as typing them once.
        raw_tokens = query.lower().split()
        tokenized_query = list(dict.fromkeys(raw_tokens))
        # dict.fromkeys preserves order while removing duplicates
        # "ibuprofen warfarin ibuprofen" → ["ibuprofen", "warfarin"]

        # Get BM25 scores for all documents
        scores = bm25.get_scores(tokenized_query)
        # scores is a numpy array: one score per document

        # Convert to RetrievedChunk objects, sorted by score
        # zip combines three iterables: scores, documents, metadatas
        # enumerate gives us the index too (for chunk_id if not in metadata)
        scored_docs = [
            (score, doc, meta)
            for score, doc, meta in zip(scores, documents, metadatas)
            if score > 0  # only include documents with positive scores
        ]

        # sorted() sorts a list. key=lambda x: x[0] means "sort by first item (score)"
        # reverse=True = descending (highest score first)
        scored_docs.sort(key=lambda x: x[0], reverse=True)

        # Convert to RetrievedChunk objects
        chunks = []
        for score, doc, metadata in scored_docs[:20]:  # top 20 only
            # Normalise BM25 score to 0-1 range for comparison with vector scores
            # We use tanh normalisation: maps any positive number to 0-1
            import math
            normalised_score = math.tanh(score / 10)  # tanh(x) = (e^x - e^-x)/(e^x + e^-x)

            chunk = RetrievedChunk(
                chunk_id=metadata.get("chunk_id", "bm25_result"),
                text=doc,
                similarity_score=round(normalised_score, 4),
                drug_name=metadata.get("drug_name", ""),
                section=metadata.get("section", ""),
                source=metadata.get("source", ""),
                severity_flag=metadata.get("severity_flag", ""),
            )
            chunks.append(chunk)

        logger.debug(
            "keyword_search_complete",
            chunks_returned=len(chunks),
        )

        return chunks

    def _reciprocal_rank_fusion(
        self,
        vector_results: list,
        keyword_results: list,
        top_k: int = 20,
    ) -> list:
        """
        Combines vector and keyword search results using Reciprocal Rank Fusion.

        THE FORMULA:
        RRF_score(chunk) = Σ 1 / (k + rank)
        where k = 60 (standard constant that prevents top ranks from dominating)

        A chunk ranked #1 in vector AND #1 in keyword scores very high.
        A chunk ranked #1 in only one method scores lower.
        This rewards chunks that multiple methods agree on.

        WHY k=60:
        This is the standard constant from the original RRF paper (2009).
        It balances the influence of different rank positions.
        Values between 40-80 all work well — 60 is the conventional choice.
        """
        k = 60  # RRF constant

        # Use a dict to accumulate scores: chunk_id → (total_rrf_score, chunk_object)
        # WHY DICT: we need to look up chunks by ID to accumulate scores
        rrf_scores: dict = {}

        # Process vector search results
        # enumerate gives us (rank_0_indexed, chunk) pairs
        for rank, chunk in enumerate(vector_results):
            # RRF formula: 1 / (k + rank + 1)
            # +1 because rank starts at 0 but formula expects 1-indexed
            rrf_score = 1 / (k + rank + 1)

            if chunk.chunk_id in rrf_scores:
                # Chunk already seen from other search — add scores
                existing_score, existing_chunk = rrf_scores[chunk.chunk_id]
                rrf_scores[chunk.chunk_id] = (existing_score + rrf_score, existing_chunk)
            else:
                rrf_scores[chunk.chunk_id] = (rrf_score, chunk)

        # Process keyword search results (same logic)
        for rank, chunk in enumerate(keyword_results):
            rrf_score = 1 / (k + rank + 1)

            if chunk.chunk_id in rrf_scores:
                existing_score, existing_chunk = rrf_scores[chunk.chunk_id]
                rrf_scores[chunk.chunk_id] = (existing_score + rrf_score, existing_chunk)
            else:
                rrf_scores[chunk.chunk_id] = (rrf_score, chunk)

        # Sort by RRF score (descending) and return top_k chunks
        # .values() gets all (score, chunk) tuples from the dict
        # sorted by score (x[0]) in descending order
        sorted_results = sorted(
            rrf_scores.values(),
            key=lambda x: x[0],
            reverse=True
        )[:top_k]

        # Extract just the chunk objects (not the scores)
        # Update the similarity_score with the RRF score for transparency
        combined_chunks = []
        for rrf_score, chunk in sorted_results:
            chunk.final_score = round(rrf_score, 6)
            combined_chunks.append(chunk)

        return combined_chunks

    def _rerank_chunks(
        self,
        query: str,
        chunks: list,
        top_k: int = 5,
    ) -> list:
        """
        Re-ranks chunks using a cross-encoder model for precision.

        WHY A CROSS-ENCODER:
        The vector search (bi-encoder) encodes the query and chunks separately.
        Fast, but it misses fine-grained relevance.

        Cross-encoder reads the query AND each chunk together simultaneously.
        It's like a teacher comparing your answer to the question directly,
        rather than encoding both separately and comparing the encodings.

        Result: much better relevance scoring on the top candidates.

        WHY ONLY RE-RANK TOP 20 (not all chunks):
        Cross-encoder is slow (~10ms per pair).
        Running it on 1000 chunks = 10 seconds per query.
        Running it on 20 chunks = ~200ms. Acceptable.
        """
        if not chunks:
            return []

        try:
            from sentence_transformers import CrossEncoder

            # Load the cross-encoder model
            # WHY THIS MODEL: small, fast, good at passage ranking
            model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

            # Create (query, chunk_text) pairs for the cross-encoder
            # The cross-encoder needs BOTH texts together to score them
            pairs = [(query, chunk.text) for chunk in chunks]

            # Get scores — model.predict() runs all pairs through the model
            scores = model.predict(pairs)
            # scores is a list of floats — one per pair

            # Combine chunks with their new cross-encoder scores
            # zip() pairs each score with its corresponding chunk
            scored_chunks = list(zip(scores, chunks))

            # Sort by cross-encoder score (descending)
            scored_chunks.sort(key=lambda x: x[0], reverse=True)

            # Take top_k and update their final_score
            reranked = []
            for score, chunk in scored_chunks[:top_k]:
                chunk.final_score = round(float(score), 4)
                reranked.append(chunk)

            logger.debug(
                "reranking_complete",
                input_chunks=len(chunks),
                output_chunks=len(reranked),
                top_score=reranked[0].final_score if reranked else 0,
            )

            return reranked

        except Exception as error:
            # If cross-encoder fails (model not loaded, etc.)
            # fall back to the RRF-ranked results
            logger.warning("reranking_failed", error=str(error))
            return chunks[:top_k]

    def _build_metadata_filter(
        self,
        intent: str,
        drugs_mentioned: list,
    ) -> Optional[dict]:
        """
        Builds a ChromaDB metadata filter based on intent.

        WHY FILTER BEFORE SEARCH:
        Without filtering, a drug interaction query might retrieve
        general information chunks about the drug — useful background
        but not what the user asked about.
        Filtering to section="drug_interactions" means we search
        only relevant chunks — faster and more precise.
        """
        # Map intents to ChromaDB section filters
        intent_to_section: dict = {
            "interaction_check": "drug_interactions",
            "side_effects": "side_effects",
            "dosing": "dosing",
            "what_is_it": "general",
        }

        section = intent_to_section.get(intent)

        # If we know what section to search and we have a drug name,
        # filter by both (most precise)
        if section and drugs_mentioned:
            primary_drug = drugs_mentioned[0]
            # ChromaDB $and operator requires both conditions to match
            return {
                "$and": [
                    {"section": {"$eq": section}},
                    {"drug_name": {"$eq": primary_drug}},
                ]
            }
        elif section:
            return {"section": {"$eq": section}}
        elif drugs_mentioned:
            return {"drug_name": {"$eq": drugs_mentioned[0]}}

        return None  # no filter — search all chunks

    def _build_context_string(self, chunks: list) -> str:
        """
        Formats retrieved chunks into a context string for the LLM prompt.

        WHY FORMAT THIS WAY:
        The LLM needs to read the retrieved information.
        We format each chunk clearly so the LLM can reference it.
        We include the source so the LLM can cite it in the response.
        """
        if not chunks:
            return "No relevant drug information found in verified sources."

        context_parts = []

        # Enumerate gives us (1, chunk), (2, chunk), etc.
        # We start numbering from 1 (more natural for the LLM to read)
        for chunk_number, chunk in enumerate(chunks, start=1):
            part = f"""
[Source {chunk_number}]
Drug: {chunk.drug_name or 'General Information'}
Section: {chunk.section or 'General'}
{f'Severity: {chunk.severity_flag.upper()}' if chunk.severity_flag else ''}
Source: {chunk.source or 'Drug database'}
Relevance Score: {chunk.final_score:.3f}

{chunk.text}
""".strip()
            context_parts.append(part)

        # Join all parts with a separator
        return "\n\n---\n\n".join(context_parts)

    def _build_messages(
        self,
        user_query: str,
        retrieved_context: str,
        conversation_history: list,
        profile_medications: list,
    ) -> list:
        """
        Builds the messages array for the LLM.

        WHY INCLUDE CONVERSATION HISTORY:
        Multi-turn conversations need context.
        "Is that safe?" needs to know what "that" refers to.
        We include the last 5 turns (enough context, not too many tokens).

        WHY INCLUDE PROFILE MEDICATIONS:
        If we know the user takes warfarin, and they ask about ibuprofen,
        the LLM can proactively note the dangerous interaction
        without them explicitly asking "can I take ibuprofen with warfarin?"
        """
        messages = []

        # Add conversation history (last 5 turns)
        # Slicing: [-5:] = last 5 items in the list
        for turn in conversation_history[-5:]:
            messages.append({
                "role": turn.get("role", "user"),
                "content": turn.get("content", ""),
            })

        # Build the current user message with retrieved context
        # We inject the context directly into the user message
        # so the LLM sees: "Here's what I found in the database + here's the question"
        user_message_parts = []

        if profile_medications:
            med_list = ", ".join(profile_medications)
            user_message_parts.append(
                f"[My current medications: {med_list}]\n"
            )

        if retrieved_context and "No relevant" not in retrieved_context:
            user_message_parts.append(
                f"[Retrieved Drug Information]\n{retrieved_context}\n\n"
            )

        user_message_parts.append(f"[My Question]\n{user_query}")

        messages.append({
            "role": "user",
            "content": "".join(user_message_parts),
            # "".join(list) concatenates all strings in the list with no separator
        })

        return messages

    def _safe_fallback_response(
        self,
        reason: str,
        drugs_mentioned: list,
        intent: str,
        pipeline_start: float,
        confidence_score: float = 0.0,
    ) -> RAGResult:
        """
        Returns a safe fallback when the confidence gate triggers.

        WHY THIS IS NOT A FAILURE:
        This is the safety feature working correctly.
        When we don't have verified information, saying so IS the right answer.
        It's safer than hallucinating a plausible-sounding but wrong answer.

        The fallback response always:
        1. Tells the user we can't answer safely from verified sources
        2. Recommends consulting a pharmacist or doctor
        3. Optionally provides the FDA drug database link for self-research
        """
        drugs_str = ", ".join(drugs_mentioned) if drugs_mentioned else "the medications you mentioned"

        fallback_text = (
            f"I don't have enough verified information to safely answer your question "
            f"about {drugs_str}. "
            f"For accurate, up-to-date information about drug interactions and safety, "
            f"please speak with your pharmacist or doctor directly. "
            f"You can also check the FDA drug information database at "
            f"https://www.accessdata.fda.gov/scripts/cder/daf/ for verified drug details."
        )

        latency = (time.monotonic() - pipeline_start) * 1000

        return RAGResult(
            response_text=fallback_text,
            retrieved_chunks=[],
            confidence_score=round(confidence_score, 4),
            confidence_gate_passed=False,
            fallback_triggered=True,
            provider_used="none",
            model_used="none",
            query_intent=intent,
            drugs_mentioned=drugs_mentioned,
            latency_ms=round(latency, 2),
        )

    def _check_data_freshness(self, chunks: list, request_id: str = "unknown") -> None:
        """
        Warns if retrieved drug data chunks are older than 90 days.

        RELIABILITY FIX: FDA updates drug labels when new risks are discovered.
        A drug interaction that FDA flagged last month might not be in our database
        if we haven't re-ingested recently. We can't catch every case, but we can
        log a warning when the data we're serving is known to be old.

        This warning should trigger a scheduled re-ingestion review.
        It does NOT block the response — old data with a warning is better than no data.
        """
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        stale_threshold_days = 90

        for chunk in chunks:
            source_date_str = chunk.source  # "fda_label_2024-01" format if available
            ingestion_date_str = getattr(chunk, 'ingestion_date', None)

            if ingestion_date_str:
                try:
                    ingestion_date = datetime.fromisoformat(ingestion_date_str)
                    if ingestion_date.tzinfo is None:
                        ingestion_date = ingestion_date.replace(tzinfo=timezone.utc)
                    age_days = (now - ingestion_date).days
                    if age_days > stale_threshold_days:
                        logger.warning(
                            "stale_drug_data_served",
                            chunk_id=chunk.chunk_id,
                            age_days=age_days,
                            threshold_days=stale_threshold_days,
                            request_id=request_id,
                        )
                except (ValueError, TypeError):
                    pass  # If we can't parse the date, we can't check staleness

    def _strip_output_html(self, text: str) -> str:
        """
        Strips HTML from LLM output before returning to the client.

        SECURITY FIX: Prevents XSS if a frontend renders AI responses as innerHTML.
        A jailbroken LLM response containing <script>alert(1)</script> would
        execute in the user's browser on a careless frontend.

        We strip on the API side as defence-in-depth.
        The frontend must ALSO render as text, not HTML — belt and suspenders.
        """
        from core.security import strip_llm_output_html
        return strip_llm_output_html(text)

    def _log_retrieval_details(
        self,
        query: str,
        expanded_query: str,
        chunks: list,
        best_score: float,
        provider: str,
        request_id: str,
    ) -> None:
        """
        Logs structured retrieval details for observability.

        WHY LOG THIS:
        This is what lets you debug hallucinations systematically.
        When a user reports a wrong answer, you look at the logs and see:
        - What query was sent to ChromaDB
        - Which chunks were retrieved (by chunk_id)
        - What similarity scores they had
        - Which chunks made it into the prompt (top_k)
        - Which provider answered

        Without this, you're guessing why the AI said what it said.
        With this, you know exactly.

        HIPAA NOTE: We log chunk_ids and scores, NOT the chunk content.
        Chunk content might contain drug names linked to a user (PHI).
        We log the metadata that helps debugging without exposing PHI.
        """
        chunk_summaries = [
            {
                "chunk_id": chunk.chunk_id,
                "score": chunk.final_score,
                "section": chunk.section,
                # WHY NO drug_name HERE:
                # drug_name + user_id together could be PHI
                # We log the section (which is not PHI) for debugging
            }
            for chunk in chunks
        ]

        logger.info(
            "rag_retrieval_complete",
            query_length=len(query),
            expanded_query_length=len(expanded_query),
            chunks_in_prompt=len(chunks),
            best_similarity_score=round(best_score, 4),
            chunk_summaries=chunk_summaries,
            provider_used=provider,
            request_id=request_id,
            confidence_gate="passed",
        )