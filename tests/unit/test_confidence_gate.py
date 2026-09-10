"""
Unit tests for the RAG pipeline confidence gate.

These tests verify the gate's core safety property:
a keyword-only match (no vector evidence) must NEVER pass the confidence gate.

This is a regression test for the bug where BM25 tanh-normalised scores
were stored in similarity_score alongside vector cosine similarity scores,
allowing keyword overlap alone to unlock the LLM.
"""
from ai.rag.pipeline import RetrievedChunk


class TestConfidenceGateScoreSeparation:
    """Verify that vector and keyword scores are stored in separate fields."""

    def test_vector_chunk_has_nonzero_similarity_score(self):
        """A chunk from vector search must have similarity_score > 0."""
        chunk = RetrievedChunk(
            chunk_id="vec-001",
            text="Warfarin interacts with ibuprofen causing bleeding risk.",
            similarity_score=0.85,
            keyword_score=0.0,
        )
        assert chunk.similarity_score == 0.85
        assert chunk.keyword_score == 0.0

    def test_bm25_chunk_has_zero_similarity_score(self):
        """A chunk from BM25-only search must have similarity_score == 0.0."""
        chunk = RetrievedChunk(
            chunk_id="bm25-001",
            text="Drug interaction information for warfarin.",
            similarity_score=0.0,   # no vector evidence
            keyword_score=0.72,     # BM25 keyword match
        )
        assert chunk.similarity_score == 0.0
        assert chunk.keyword_score == 0.72

    def test_chunk_from_both_searches_has_both_scores(self):
        """A chunk returned by both searches has both scores populated."""
        chunk = RetrievedChunk(
            chunk_id="both-001",
            text="Severe bleeding risk when warfarin and ibuprofen combined.",
            similarity_score=0.81,
            keyword_score=0.65,
        )
        assert chunk.similarity_score > 0
        assert chunk.keyword_score > 0


class TestConfidenceGateLogic:
    """
    Test the gate logic directly — keyword-only chunks must never pass.

    These tests replicate what the pipeline does at lines ~595 and ~776:
      vector_scores = [c.similarity_score for c in chunks if c.similarity_score > 0]
      best_score = max(vector_scores) if vector_scores else 0.0

    We test the logic directly to avoid needing a full pipeline fixture.
    The integration tests (tests/integration/) verify the end-to-end behavior.
    """

    def _compute_gate_score(self, chunks: list[RetrievedChunk]) -> float:
        """Replicate the gate logic from pipeline.py."""
        vector_scores = [c.similarity_score for c in chunks if c.similarity_score > 0]
        return max(vector_scores) if vector_scores else 0.0

    def test_keyword_only_chunks_produce_zero_gate_score(self):
        """
        REGRESSION TEST: keyword-only chunks must produce a gate score of 0.0.

        This is the exact bug that was found:
        BM25 tanh scores above 0.75 were passing the gate because they were
        stored in similarity_score. With the fix, keyword_score is separate
        and never touches the gate calculation.
        """
        # Simulate chunks that only matched on boilerplate keywords
        # ("interaction", "severe", "consult") with no semantic relevance
        chunks = [
            RetrievedChunk(
                chunk_id=f"bm25-{i}",
                text="Drug interaction. Consult your doctor. Severe reactions possible.",
                similarity_score=0.0,    # no vector match
                keyword_score=0.82,      # HIGH keyword score — would have passed old gate
            )
            for i in range(5)
        ]

        gate_score = self._compute_gate_score(chunks)

        # Must be 0.0 — no vector evidence means gate should fire
        assert gate_score == 0.0, (
            f"Gate score was {gate_score} — keyword-only chunks should produce 0.0. "
            f"This is the regression the fix was designed to prevent."
        )

    def test_vector_chunks_above_threshold_pass_gate(self):
        """Vector chunks with high similarity correctly pass the gate."""
        chunks = [
            RetrievedChunk(
                chunk_id="vec-001",
                text="Warfarin and ibuprofen interaction causes serious bleeding.",
                similarity_score=0.88,
                keyword_score=0.0,
            )
        ]
        gate_score = self._compute_gate_score(chunks)
        assert gate_score == 0.88
        assert gate_score >= 0.75  # above default threshold

    def test_vector_chunks_below_threshold_fail_gate(self):
        """Low vector similarity correctly fails the gate."""
        chunks = [
            RetrievedChunk(
                chunk_id="vec-002",
                text="General pharmaceutical information.",
                similarity_score=0.42,
                keyword_score=0.0,
            )
        ]
        gate_score = self._compute_gate_score(chunks)
        assert gate_score == 0.42
        assert gate_score < 0.75  # below threshold — gate fires

    def test_mixed_chunks_gate_uses_only_vector_scores(self):
        """
        When both vector and keyword chunks are present, gate uses only vector scores.
        A high keyword score cannot inflate the gate beyond the vector score.
        """
        chunks = [
            RetrievedChunk(
                chunk_id="vec-001",
                text="Warfarin interactions.",
                similarity_score=0.62,   # below threshold
                keyword_score=0.0,
            ),
            RetrievedChunk(
                chunk_id="bm25-001",
                text="Interaction. Severe. Consult.",
                similarity_score=0.0,    # no vector evidence
                keyword_score=0.91,      # very high keyword score
            ),
        ]
        gate_score = self._compute_gate_score(chunks)

        # Gate score must be 0.62 (the vector score only)
        # NOT 0.91 (the keyword score) — that would be the old bug
        assert gate_score == 0.62
        assert gate_score < 0.75  # gate correctly fires despite high keyword score

    def test_all_vector_chunks_gate_uses_highest(self):
        """Gate correctly picks the highest vector score across multiple chunks."""
        chunks = [
            RetrievedChunk(chunk_id="v1", text="a", similarity_score=0.71, keyword_score=0.0),
            RetrievedChunk(chunk_id="v2", text="b", similarity_score=0.89, keyword_score=0.0),
            RetrievedChunk(chunk_id="v3", text="c", similarity_score=0.65, keyword_score=0.0),
        ]
        gate_score = self._compute_gate_score(chunks)
        assert gate_score == 0.89

    def test_empty_chunks_produce_zero_gate_score(self):
        """Empty chunk list produces 0.0 — gate always fires on no results."""
        gate_score = self._compute_gate_score([])
        assert gate_score == 0.0