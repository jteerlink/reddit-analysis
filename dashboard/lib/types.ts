export interface Topic {
  topic_id: number;
  keywords: string;
  doc_count: number;
  coherence_score?: number | null;
  label?: string | null;
  llm_label?: string | null;
  deterministic_label?: string | null;
  label_keywords?: string | null;
  label_source?: "llm_artifact" | "deterministic_fallback" | "unlabeled" | string;
  weekly_counts?: number[];
}

export interface TopicGraphNode extends Topic {
  keyword_terms: string[];
  emerging?: boolean;
}

export interface TopicGraphEdge {
  source: number;
  target: number;
  similarity: number;
  shared_keywords: string[];
}

export interface TopicGraphResponse {
  nodes: TopicGraphNode[];
  edges: TopicGraphEdge[];
}

export interface TopicHeatmapRow {
  topic_id: number;
  week_start: string;
  avg_sentiment: number | null;
}

export interface ResponseProvenance {
  state?: string;
  label?: string;
  source?: string | null;
  source_table?: string | null;
  source_ids?: string[];
  schema_version?: number;
  artifact_id?: string | null;
  source_input_hash?: string | null;
  freshness_timestamp?: string | null;
  algorithm?: string | null;
  provider?: string | null;
  detail?: string | null;
}

export interface TopicHeatmapResponse {
  items: TopicHeatmapRow[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface TopicOverTime {
  topic_id: number;
  week_start: string;
  doc_count: number;
  avg_sentiment?: number | null;
}

export interface SentimentSummary {
  label: string;
  count: number;
  weighted_count?: number;
  mean_confidence?: number | null;
  weighted?: boolean;
}

export interface SentimentDaily {
  subreddit: string;
  date: string;
  mean_score: number | null;
  rolling_7d?: number | null;
  rolling_30d?: number | null;
}

export interface VolumeDaily {
  date: string;
  subreddit: string;
  count: number;
}

export interface ChangePoint {
  subreddit: string;
  date: string;
  magnitude: number;
}

export interface Forecast {
  subreddit: string;
  date: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
}

export interface CollectionSummary {
  total_posts: number;
  total_comments: number;
  last_timestamp: string | null;
  last_ml_timestamp: string | null;
  trending_topics?: TrendingTopic[];
}

export interface TrendingTopic extends Topic {
  week_start?: string;
  parents?: Array<{ parent_id: string; display_name: string; doc_count: number }>;
}

export interface Post {
  id: string;
  date: string;
  subreddit: string;
  content_type: string;
  label: string | null;
  confidence: number;
  clean_text: string;
}

export interface ActivityEvent {
  timestamp: string;
  type: string;
  severity: "info" | "warn" | "error" | "success";
  title: string;
  detail: string;
  source_ids: string[];
  state?: string;
  provenance?: ResponseProvenance;
}

export interface VaderAgreement {
  subreddit: string;
  agreement_rate: number;
  total: number;
}

export interface LowConfidenceExample {
  id: string;
  date?: string | null;
  subreddit?: string | null;
  content_type?: string | null;
  label: string;
  confidence: number;
  text_preview: string;
}

export interface VaderDisagreement extends LowConfidenceExample {
  vader_label: string;
}

export interface LowConfidenceResponse {
  items: LowConfidenceExample[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface VaderDisagreementResponse {
  items: VaderDisagreement[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface ConfidenceBySubreddit {
  subreddit: string;
  total: number;
  mean_confidence: number;
  low_confidence_count: number;
}

export interface ConfidenceBySubredditResponse {
  items: ConfidenceBySubreddit[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface EmbeddingPoint {
  id: string;
  x: number;
  y: number;
  cluster_id: number;
  topic_id?: number | null;
  subreddit?: string | null;
  parent_id?: string | null;
  sentiment?: string | null;
  date?: string | null;
  preview?: string | null;
}

export interface EmbeddingMapResponse {
  items: EmbeddingPoint[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface SemanticSearchResult {
  id: string;
  score: number;
  date?: string | null;
  subreddit?: string | null;
  content_type?: string | null;
  label?: string | null;
  confidence?: number | null;
  text_preview: string;
}

export interface SemanticSearchResponse {
  items: SemanticSearchResult[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface BriefSection {
  title: string;
  body: string;
  claims?: string[];
  evidence?: BriefEvidence[];
  drivers?: string[];
  implications?: string[];
  delta?: string;
  delta_source?: string;
  current_window?: string;
  comparison_window?: string;
  evidence_gap?: string;
  [key: string]: unknown;
}

export interface BriefEvidence {
  anchor_type: string;
  anchor_id: string;
  label?: string;
  snippet?: string;
  relevance?: string;
}

export interface AnalystBrief {
  brief_id: string;
  period: string;
  headline: string;
  sections: BriefSection[];
  source_events: number[];
  generated_at?: string | null;
  model_name?: string | null;
  state?: string;
  provenance?: ResponseProvenance & { artifact_id?: string | null };
}

export interface AnalystBriefsResponse {
  items: AnalystBrief[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface FreshnessResponse {
  latest_artifact_at?: string | null;
  latest_success_at?: string | null;
  queued: number;
  running: number;
  failed: number;
  succeeded: number;
  enrichment_available: boolean;
  reason?: string | null;
  state: string;
  llm_enrichment_available?: boolean;
  llm_reason?: string | null;
}

export interface ModelRegistryEntry {
  model_name: string;
  provider: string;
  available: boolean;
  metadata?: Record<string, unknown>;
  discovered_at?: string | null;
}

export interface ModelRegistryResponse {
  default_host: string;
  cloud_configured: boolean;
  local_override: boolean;
  models: ModelRegistryEntry[];
  error?: string | null;
}

export interface NarrativeEvent {
  event_id: number;
  start_date: string;
  end_date: string;
  peak_date: string;
  title: string;
  summary: string;
  sentiment_delta?: number | null;
  dominant_subreddits: string[];
  top_terms: string[];
  top_post_ids: string[];
  lifecycle_state?: "emerging" | "accelerating" | "peaking" | "cooling" | "recurring";
}

export interface NarrativeEventsResponse {
  items: NarrativeEvent[];
  state: string;
  provenance?: ResponseProvenance;
}

export interface PipelineStep {
  num: number;
  name: string;
  description: string;
  state: string;
  done: boolean;
  prereq_ok: boolean;
}

export interface SubredditCategory {
  id: string;
  display_name: string;
  subreddits: string[];
  volume: number;
  mean_sentiment: number | null;
  sort_order: number;
}

export interface SubredditCategoriesResponse {
  parents: SubredditCategory[];
}

export interface SubredditGraphNode {
  subreddit: string;
  parent_id: string;
  display_name: string;
  post_count: number;
  comment_count: number;
  total_volume: number;
  mean_sentiment: number | null;
  top_topics: Array<{ topic_id: number; label?: string | null; share: number }>;
}

export interface SubredditGraphEdge {
  source: string;
  target: string;
  author_overlap: number;
  topic_overlap: number;
  score: number;
  shared_topic_ids: number[];
}

export interface SubredditGraphResponse {
  nodes: SubredditGraphNode[];
  edges: SubredditGraphEdge[];
}
