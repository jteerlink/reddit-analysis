"""Typed public contracts for persisted analysis artifacts."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

ArtifactStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "stale"]
AnalysisState = Literal["ready", "missing_schema", "unpopulated", "stale_artifact", "missing_config", "error"]
ProvenanceLabel = Literal[
    "real_data",
    "deterministic_fallback",
    "llm_artifact",
    "missing_config",
    "stale_artifact",
]


class AnalysisProvenance(BaseModel):
    state: AnalysisState = "ready"
    label: ProvenanceLabel = "real_data"
    source: Optional[str] = None
    source_table: Optional[str] = None
    source_ids: List[str] = Field(default_factory=list)
    producer_job: Optional[str] = None
    schema_version: int = 1
    artifact_id: Optional[str] = None
    source_input_hash: Optional[str] = None
    freshness_timestamp: Optional[str] = None
    algorithm: Optional[str] = None
    provider: Optional[str] = None
    detail: Optional[str] = None


class ArtifactRecord(BaseModel):
    artifact_id: str
    run_id: Optional[str] = None
    kind: str
    status: ArtifactStatus
    idempotency_key: str
    schema_version: int = 1
    provider: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    source_input_hash: str
    freshness_timestamp: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ArtifactStatusResponse(BaseModel):
    artifacts: List[ArtifactRecord]


class ActivityEvent(BaseModel):
    timestamp: str
    type: str
    severity: Literal["info", "warn", "error", "success"] = "info"
    title: str
    detail: str
    source_ids: List[str] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class FreshnessResponse(BaseModel):
    latest_artifact_at: Optional[str] = None
    latest_success_at: Optional[str] = None
    queued: int = 0
    running: int = 0
    failed: int = 0
    succeeded: int = 0
    enrichment_available: bool = False
    reason: Optional[str] = None
    state: AnalysisState = "ready"
    missing_tables: List[str] = Field(default_factory=list)
    provenance: Optional[AnalysisProvenance] = None
    llm_enrichment_available: bool = False
    llm_reason: Optional[str] = None


class ModelRegistryEntry(BaseModel):
    model_name: str
    provider: str = "ollama"
    available: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    discovered_at: Optional[str] = None


class ModelRegistryResponse(BaseModel):
    default_host: str
    cloud_configured: bool
    local_override: bool
    models: List[ModelRegistryEntry]
    error: Optional[str] = None


class NarrativeEvent(BaseModel):
    event_id: int
    start_date: str
    end_date: str
    peak_date: str
    title: str
    summary: str
    sentiment_delta: Optional[float] = None
    dominant_subreddits: List[str] = Field(default_factory=list)
    top_terms: List[str] = Field(default_factory=list)
    top_post_ids: List[str] = Field(default_factory=list)
    lifecycle_state: Literal["emerging", "accelerating", "peaking", "cooling", "recurring"] = "peaking"
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class NarrativeEventsResponse(BaseModel):
    items: List[NarrativeEvent] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class EmbeddingPoint(BaseModel):
    id: str
    x: float
    y: float
    cluster_id: int
    topic_id: Optional[int] = None
    subreddit: Optional[str] = None
    sentiment: Optional[str] = None
    date: Optional[str] = None
    preview: Optional[str] = None
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class EmbeddingMapResponse(BaseModel):
    items: List[EmbeddingPoint] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class SemanticSearchResult(BaseModel):
    id: str
    score: float
    date: Optional[str] = None
    subreddit: Optional[str] = None
    content_type: Optional[str] = None
    label: Optional[str] = None
    confidence: Optional[float] = None
    text_preview: str
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class SemanticSearchResponse(BaseModel):
    items: List[SemanticSearchResult] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class TopicHeatmapItem(BaseModel):
    topic_id: int
    week_start: str
    avg_sentiment: Optional[float] = None


class TopicHeatmapResponse(BaseModel):
    items: List[TopicHeatmapItem] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class LowConfidenceExample(BaseModel):
    id: str
    date: Optional[str] = None
    subreddit: Optional[str] = None
    content_type: Optional[str] = None
    label: str
    confidence: float
    text_preview: str


class VaderDisagreement(LowConfidenceExample):
    vader_label: str


class ConfidenceBySubreddit(BaseModel):
    subreddit: str
    total: int
    mean_confidence: float
    low_confidence_count: int


class LowConfidenceResponse(BaseModel):
    items: List[LowConfidenceExample] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class VaderDisagreementResponse(BaseModel):
    items: List[VaderDisagreement] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class ConfidenceBySubredditResponse(BaseModel):
    items: List[ConfidenceBySubreddit] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class ThreadAnalysis(BaseModel):
    post_id: str
    title: Optional[str] = None
    subreddit: Optional[str] = None
    comment_count: int = 0
    sentiment_spread: float = 0.0
    controversy_score: float = 0.0
    positions_summary: str = "No persisted thread analysis is available yet."
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    representative_comments: List[Dict[str, Any]] = Field(default_factory=list)
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None


class AnalystBrief(BaseModel):
    brief_id: str
    period: str
    headline: str
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    source_events: List[int] = Field(default_factory=list)
    generated_at: Optional[str] = None
    model_name: Optional[str] = None
    state: AnalysisState = "ready"
    provenance: Optional[AnalysisProvenance] = None
