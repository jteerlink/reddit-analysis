const BASE = "/api";

async function get<T>(path: string, params?: Record<string, string | string[] | number | undefined>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined) continue;
      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, v));
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  summary: (subreddits?: string[]) =>
    get("/summary", subreddits?.length ? { subreddits } : undefined),
  sentimentSummary: (subreddits?: string[]) =>
    get("/sentiment/summary", subreddits?.length ? { subreddits } : undefined),
  sentimentDaily: (subreddits?: string[], days = 90) =>
    get("/sentiment/daily", { ...(subreddits?.length ? { subreddits } : {}), days }),
  changePoints: (subreddits?: string[]) =>
    get("/sentiment/change-points", subreddits?.length ? { subreddits } : undefined),
  forecast: (subreddits?: string[]) =>
    get("/sentiment/forecast", subreddits?.length ? { subreddits } : undefined),
  volumeDaily: (subreddits?: string[], days = 30) =>
    get("/volume/daily", { ...(subreddits?.length ? { subreddits } : {}), days }),
  topics: () => get("/topics"),
  emergingTopics: (days = 7) => get("/topics/emerging", { days }),
  topicGraph: (n = 50, minSimilarity = 0.15) => get("/topics/graph", { n, min_similarity: minSimilarity }),
  topicHeatmap: (n = 30) => get("/topics/heatmap", { n }),
  topicOverTime: (id: number) => get(`/topics/${id}/over-time`),
  postsSearch: (params: {
    keyword?: string;
    subreddits?: string[];
    start?: string;
    end?: string;
    label?: string;
    content_type?: string;
    topic_id?: number;
    limit?: number;
    offset?: number;
  }) => get("/posts/search", params as Record<string, string | string[] | number | undefined>),
  vaderAgreement: () => get("/model/vader-agreement"),
  subreddits: () => get<string[]>("/subreddits"),
  dateRange: () => get("/date-range"),
  pipelineStatus: () => get("/pipeline/status"),
  analysisActivity: () => get("/analysis/activity"),
  analysisFreshness: () => get("/analysis/freshness"),
  analysisModels: () => get("/analysis/model-registry"),
  narrativeEvents: () => get("/analysis/narrative-events"),
  embeddingMap: () => get("/analysis/embedding-map"),
  semanticSearch: (q: string, limit = 50) => get("/analysis/semantic-search", { q, limit }),
  latestBrief: () => get("/analysis/briefs/latest"),
};
