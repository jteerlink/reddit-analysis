// Generated from FastAPI OpenAPI schemas. Run `npm run generate:api-types` in dashboard.
export const generatedApiSchemas = {
  "ActivityEvent": {
    "properties": {
      "detail": {
        "title": "Detail",
        "type": "string"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "severity": {
        "default": "info",
        "enum": [
          "info",
          "warn",
          "error",
          "success"
        ],
        "title": "Severity",
        "type": "string"
      },
      "source_ids": {
        "items": {
          "type": "string"
        },
        "title": "Source Ids",
        "type": "array"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      },
      "timestamp": {
        "title": "Timestamp",
        "type": "string"
      },
      "title": {
        "title": "Title",
        "type": "string"
      },
      "type": {
        "title": "Type",
        "type": "string"
      }
    },
    "required": [
      "timestamp",
      "type",
      "title",
      "detail"
    ],
    "title": "ActivityEvent",
    "type": "object"
  },
  "AnalysisProvenance": {
    "properties": {
      "algorithm": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Algorithm"
      },
      "artifact_id": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Artifact Id"
      },
      "detail": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Detail"
      },
      "freshness_timestamp": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Freshness Timestamp"
      },
      "label": {
        "default": "real_data",
        "enum": [
          "real_data",
          "deterministic_fallback",
          "llm_artifact",
          "missing_config",
          "stale_artifact"
        ],
        "title": "Label",
        "type": "string"
      },
      "producer_job": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Producer Job"
      },
      "provider": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Provider"
      },
      "schema_version": {
        "default": 1,
        "title": "Schema Version",
        "type": "integer"
      },
      "source": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Source"
      },
      "source_ids": {
        "items": {
          "type": "string"
        },
        "title": "Source Ids",
        "type": "array"
      },
      "source_input_hash": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Source Input Hash"
      },
      "source_table": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Source Table"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "AnalysisProvenance",
    "type": "object"
  },
  "AnalystBrief": {
    "properties": {
      "brief_id": {
        "title": "Brief Id",
        "type": "string"
      },
      "generated_at": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Generated At"
      },
      "headline": {
        "title": "Headline",
        "type": "string"
      },
      "model_name": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Model Name"
      },
      "period": {
        "title": "Period",
        "type": "string"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "sections": {
        "items": {
          "additionalProperties": true,
          "type": "object"
        },
        "title": "Sections",
        "type": "array"
      },
      "source_events": {
        "items": {
          "type": "integer"
        },
        "title": "Source Events",
        "type": "array"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "required": [
      "brief_id",
      "period",
      "headline"
    ],
    "title": "AnalystBrief",
    "type": "object"
  },
  "ArtifactRecord": {
    "properties": {
      "artifact_id": {
        "title": "Artifact Id",
        "type": "string"
      },
      "attempts": {
        "default": 0,
        "title": "Attempts",
        "type": "integer"
      },
      "created_at": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Created At"
      },
      "error_category": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Error Category"
      },
      "error_message": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Error Message"
      },
      "freshness_timestamp": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Freshness Timestamp"
      },
      "idempotency_key": {
        "title": "Idempotency Key",
        "type": "string"
      },
      "kind": {
        "title": "Kind",
        "type": "string"
      },
      "max_attempts": {
        "default": 3,
        "title": "Max Attempts",
        "type": "integer"
      },
      "model_name": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Model Name"
      },
      "prompt_version": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Prompt Version"
      },
      "provider": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Provider"
      },
      "run_id": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Run Id"
      },
      "schema_version": {
        "default": 1,
        "title": "Schema Version",
        "type": "integer"
      },
      "source_input_hash": {
        "title": "Source Input Hash",
        "type": "string"
      },
      "status": {
        "enum": [
          "queued",
          "running",
          "succeeded",
          "failed",
          "canceled",
          "stale"
        ],
        "title": "Status",
        "type": "string"
      },
      "updated_at": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Updated At"
      }
    },
    "required": [
      "artifact_id",
      "kind",
      "status",
      "idempotency_key",
      "source_input_hash"
    ],
    "title": "ArtifactRecord",
    "type": "object"
  },
  "ArtifactStatusResponse": {
    "properties": {
      "artifacts": {
        "items": {
          "$ref": "#/components/schemas/ArtifactRecord"
        },
        "title": "Artifacts",
        "type": "array"
      }
    },
    "required": [
      "artifacts"
    ],
    "title": "ArtifactStatusResponse",
    "type": "object"
  },
  "ConfidenceBySubreddit": {
    "properties": {
      "low_confidence_count": {
        "title": "Low Confidence Count",
        "type": "integer"
      },
      "mean_confidence": {
        "title": "Mean Confidence",
        "type": "number"
      },
      "subreddit": {
        "title": "Subreddit",
        "type": "string"
      },
      "total": {
        "title": "Total",
        "type": "integer"
      }
    },
    "required": [
      "subreddit",
      "total",
      "mean_confidence",
      "low_confidence_count"
    ],
    "title": "ConfidenceBySubreddit",
    "type": "object"
  },
  "ConfidenceBySubredditResponse": {
    "properties": {
      "items": {
        "items": {
          "$ref": "#/components/schemas/ConfidenceBySubreddit"
        },
        "title": "Items",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "ConfidenceBySubredditResponse",
    "type": "object"
  },
  "EmbeddingMapResponse": {
    "properties": {
      "items": {
        "items": {
          "$ref": "#/components/schemas/EmbeddingPoint"
        },
        "title": "Items",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "EmbeddingMapResponse",
    "type": "object"
  },
  "EmbeddingPoint": {
    "properties": {
      "cluster_id": {
        "title": "Cluster Id",
        "type": "integer"
      },
      "date": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Date"
      },
      "id": {
        "title": "Id",
        "type": "string"
      },
      "preview": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Preview"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "sentiment": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Sentiment"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      },
      "subreddit": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Subreddit"
      },
      "topic_id": {
        "anyOf": [
          {
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "title": "Topic Id"
      },
      "x": {
        "title": "X",
        "type": "number"
      },
      "y": {
        "title": "Y",
        "type": "number"
      }
    },
    "required": [
      "id",
      "x",
      "y",
      "cluster_id"
    ],
    "title": "EmbeddingPoint",
    "type": "object"
  },
  "FreshnessResponse": {
    "properties": {
      "enrichment_available": {
        "default": false,
        "title": "Enrichment Available",
        "type": "boolean"
      },
      "failed": {
        "default": 0,
        "title": "Failed",
        "type": "integer"
      },
      "latest_artifact_at": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Latest Artifact At"
      },
      "latest_success_at": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Latest Success At"
      },
      "llm_enrichment_available": {
        "default": false,
        "title": "Llm Enrichment Available",
        "type": "boolean"
      },
      "llm_reason": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Llm Reason"
      },
      "missing_tables": {
        "items": {
          "type": "string"
        },
        "title": "Missing Tables",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "queued": {
        "default": 0,
        "title": "Queued",
        "type": "integer"
      },
      "reason": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Reason"
      },
      "running": {
        "default": 0,
        "title": "Running",
        "type": "integer"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      },
      "succeeded": {
        "default": 0,
        "title": "Succeeded",
        "type": "integer"
      }
    },
    "title": "FreshnessResponse",
    "type": "object"
  },
  "HTTPValidationError": {
    "properties": {
      "detail": {
        "items": {
          "$ref": "#/components/schemas/ValidationError"
        },
        "title": "Detail",
        "type": "array"
      }
    },
    "title": "HTTPValidationError",
    "type": "object"
  },
  "LowConfidenceExample": {
    "properties": {
      "confidence": {
        "title": "Confidence",
        "type": "number"
      },
      "content_type": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Content Type"
      },
      "date": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Date"
      },
      "id": {
        "title": "Id",
        "type": "string"
      },
      "label": {
        "title": "Label",
        "type": "string"
      },
      "subreddit": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Subreddit"
      },
      "text_preview": {
        "title": "Text Preview",
        "type": "string"
      }
    },
    "required": [
      "id",
      "label",
      "confidence",
      "text_preview"
    ],
    "title": "LowConfidenceExample",
    "type": "object"
  },
  "LowConfidenceResponse": {
    "properties": {
      "items": {
        "items": {
          "$ref": "#/components/schemas/LowConfidenceExample"
        },
        "title": "Items",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "LowConfidenceResponse",
    "type": "object"
  },
  "ModelRegistryEntry": {
    "properties": {
      "available": {
        "default": false,
        "title": "Available",
        "type": "boolean"
      },
      "discovered_at": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Discovered At"
      },
      "metadata": {
        "additionalProperties": true,
        "title": "Metadata",
        "type": "object"
      },
      "model_name": {
        "title": "Model Name",
        "type": "string"
      },
      "provider": {
        "default": "ollama",
        "title": "Provider",
        "type": "string"
      }
    },
    "required": [
      "model_name"
    ],
    "title": "ModelRegistryEntry",
    "type": "object"
  },
  "ModelRegistryResponse": {
    "properties": {
      "cloud_configured": {
        "title": "Cloud Configured",
        "type": "boolean"
      },
      "default_host": {
        "title": "Default Host",
        "type": "string"
      },
      "error": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Error"
      },
      "local_override": {
        "title": "Local Override",
        "type": "boolean"
      },
      "models": {
        "items": {
          "$ref": "#/components/schemas/ModelRegistryEntry"
        },
        "title": "Models",
        "type": "array"
      }
    },
    "required": [
      "default_host",
      "cloud_configured",
      "local_override",
      "models"
    ],
    "title": "ModelRegistryResponse",
    "type": "object"
  },
  "NarrativeEvent": {
    "properties": {
      "dominant_subreddits": {
        "items": {
          "type": "string"
        },
        "title": "Dominant Subreddits",
        "type": "array"
      },
      "end_date": {
        "title": "End Date",
        "type": "string"
      },
      "event_id": {
        "title": "Event Id",
        "type": "integer"
      },
      "lifecycle_state": {
        "default": "peaking",
        "enum": [
          "emerging",
          "accelerating",
          "peaking",
          "cooling",
          "recurring"
        ],
        "title": "Lifecycle State",
        "type": "string"
      },
      "peak_date": {
        "title": "Peak Date",
        "type": "string"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "sentiment_delta": {
        "anyOf": [
          {
            "type": "number"
          },
          {
            "type": "null"
          }
        ],
        "title": "Sentiment Delta"
      },
      "start_date": {
        "title": "Start Date",
        "type": "string"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      },
      "summary": {
        "title": "Summary",
        "type": "string"
      },
      "title": {
        "title": "Title",
        "type": "string"
      },
      "top_post_ids": {
        "items": {
          "type": "string"
        },
        "title": "Top Post Ids",
        "type": "array"
      },
      "top_terms": {
        "items": {
          "type": "string"
        },
        "title": "Top Terms",
        "type": "array"
      }
    },
    "required": [
      "event_id",
      "start_date",
      "end_date",
      "peak_date",
      "title",
      "summary"
    ],
    "title": "NarrativeEvent",
    "type": "object"
  },
  "NarrativeEventsResponse": {
    "properties": {
      "items": {
        "items": {
          "$ref": "#/components/schemas/NarrativeEvent"
        },
        "title": "Items",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "NarrativeEventsResponse",
    "type": "object"
  },
  "SemanticSearchResponse": {
    "properties": {
      "items": {
        "items": {
          "$ref": "#/components/schemas/SemanticSearchResult"
        },
        "title": "Items",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "SemanticSearchResponse",
    "type": "object"
  },
  "SemanticSearchResult": {
    "properties": {
      "confidence": {
        "anyOf": [
          {
            "type": "number"
          },
          {
            "type": "null"
          }
        ],
        "title": "Confidence"
      },
      "content_type": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Content Type"
      },
      "date": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Date"
      },
      "id": {
        "title": "Id",
        "type": "string"
      },
      "label": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Label"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "score": {
        "title": "Score",
        "type": "number"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      },
      "subreddit": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Subreddit"
      },
      "text_preview": {
        "title": "Text Preview",
        "type": "string"
      }
    },
    "required": [
      "id",
      "score",
      "text_preview"
    ],
    "title": "SemanticSearchResult",
    "type": "object"
  },
  "ThreadAnalysis": {
    "properties": {
      "comment_count": {
        "default": 0,
        "title": "Comment Count",
        "type": "integer"
      },
      "controversy_score": {
        "default": 0.0,
        "title": "Controversy Score",
        "type": "number"
      },
      "negative_count": {
        "default": 0,
        "title": "Negative Count",
        "type": "integer"
      },
      "neutral_count": {
        "default": 0,
        "title": "Neutral Count",
        "type": "integer"
      },
      "positions_summary": {
        "default": "No persisted thread analysis is available yet.",
        "title": "Positions Summary",
        "type": "string"
      },
      "positive_count": {
        "default": 0,
        "title": "Positive Count",
        "type": "integer"
      },
      "post_id": {
        "title": "Post Id",
        "type": "string"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "representative_comments": {
        "items": {
          "additionalProperties": true,
          "type": "object"
        },
        "title": "Representative Comments",
        "type": "array"
      },
      "sentiment_spread": {
        "default": 0.0,
        "title": "Sentiment Spread",
        "type": "number"
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      },
      "subreddit": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Subreddit"
      },
      "title": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Title"
      }
    },
    "required": [
      "post_id"
    ],
    "title": "ThreadAnalysis",
    "type": "object"
  },
  "TopicHeatmapItem": {
    "properties": {
      "avg_sentiment": {
        "anyOf": [
          {
            "type": "number"
          },
          {
            "type": "null"
          }
        ],
        "title": "Avg Sentiment"
      },
      "topic_id": {
        "title": "Topic Id",
        "type": "integer"
      },
      "week_start": {
        "title": "Week Start",
        "type": "string"
      }
    },
    "required": [
      "topic_id",
      "week_start"
    ],
    "title": "TopicHeatmapItem",
    "type": "object"
  },
  "TopicHeatmapResponse": {
    "properties": {
      "items": {
        "items": {
          "$ref": "#/components/schemas/TopicHeatmapItem"
        },
        "title": "Items",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "TopicHeatmapResponse",
    "type": "object"
  },
  "VaderDisagreement": {
    "properties": {
      "confidence": {
        "title": "Confidence",
        "type": "number"
      },
      "content_type": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Content Type"
      },
      "date": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Date"
      },
      "id": {
        "title": "Id",
        "type": "string"
      },
      "label": {
        "title": "Label",
        "type": "string"
      },
      "subreddit": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "title": "Subreddit"
      },
      "text_preview": {
        "title": "Text Preview",
        "type": "string"
      },
      "vader_label": {
        "title": "Vader Label",
        "type": "string"
      }
    },
    "required": [
      "id",
      "label",
      "confidence",
      "text_preview",
      "vader_label"
    ],
    "title": "VaderDisagreement",
    "type": "object"
  },
  "VaderDisagreementResponse": {
    "properties": {
      "items": {
        "items": {
          "$ref": "#/components/schemas/VaderDisagreement"
        },
        "title": "Items",
        "type": "array"
      },
      "provenance": {
        "anyOf": [
          {
            "$ref": "#/components/schemas/AnalysisProvenance"
          },
          {
            "type": "null"
          }
        ]
      },
      "state": {
        "default": "ready",
        "enum": [
          "ready",
          "missing_schema",
          "unpopulated",
          "stale_artifact",
          "missing_config",
          "error"
        ],
        "title": "State",
        "type": "string"
      }
    },
    "title": "VaderDisagreementResponse",
    "type": "object"
  },
  "ValidationError": {
    "properties": {
      "loc": {
        "items": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "integer"
            }
          ]
        },
        "title": "Location",
        "type": "array"
      },
      "msg": {
        "title": "Message",
        "type": "string"
      },
      "type": {
        "title": "Error Type",
        "type": "string"
      }
    },
    "required": [
      "loc",
      "msg",
      "type"
    ],
    "title": "ValidationError",
    "type": "object"
  }
} as const;
export type GeneratedApiSchemas = typeof generatedApiSchemas;
