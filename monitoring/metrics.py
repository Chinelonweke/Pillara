# monitoring/metrics.py
#
# Prometheus metrics — exposed at /metrics for scraping.
# Tracks: request counts, latencies, LLM provider usage, confidence gate triggers.
# These metrics feed dashboards and alerting (e.g. "confidence gate triggered >20% of requests").

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ─── HTTP METRICS ──────────────────────────────────────────────────────────────

http_requests_total = Counter(
    "pillara_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "pillara_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

# ─── LLM METRICS ────────────────────────────────────────────────────────────────

llm_requests_total = Counter(
    "pillara_llm_requests_total",
    "Total LLM completion requests",
    ["provider", "complexity"],
)

llm_request_duration_seconds = Histogram(
    "pillara_llm_request_duration_seconds",
    "LLM request latency in seconds",
    ["provider"],
)

llm_provider_failures_total = Counter(
    "pillara_llm_provider_failures_total",
    "LLM provider failures (triggers fallback)",
    ["provider", "error_type"],
)

llm_all_providers_failed_total = Counter(
    "pillara_llm_all_providers_failed_total",
    "Count of requests where ALL LLM providers failed (critical alert)",
)

# ─── RAG METRICS ────────────────────────────────────────────────────────────────

rag_confidence_gate_triggered_total = Counter(
    "pillara_rag_confidence_gate_triggered_total",
    "Count of queries that failed the confidence gate (safe fallback returned)",
)

rag_confidence_score = Histogram(
    "pillara_rag_confidence_score",
    "Distribution of RAG confidence scores",
    buckets=[0.0, 0.25, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0],
)

# ─── BUSINESS METRICS ─────────────────────────────────────────────────────────

active_users_gauge = Gauge(
    "pillara_active_sessions",
    "Current number of active user sessions",
)

medications_added_total = Counter(
    "pillara_medications_added_total",
    "Total medications added across all users",
)

interaction_checks_total = Counter(
    "pillara_interaction_checks_total",
    "Total drug interaction checks performed",
    ["overall_risk"],
)


def get_metrics() -> bytes:
    """Returns Prometheus metrics in text exposition format."""
    return generate_latest()