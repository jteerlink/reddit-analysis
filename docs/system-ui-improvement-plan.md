# System and UI improvement plan

## Objective and scope

Improve the reliability, speed, and usability of this personal tool for exploring AI and technology discussions. The product baseline is [PRD v2](prd_v2.md:7). Retain the existing Python batch pipeline, FastAPI API, Next.js dashboard, SQLite storage, and optional Neon mirror. No infrastructure replacement or new dependency is assumed.

This is an implementation plan, not authorization to execute every operation below. Work in small, reversible changes; preserve raw collected data and existing uncommitted work. The initial review found modifications in scripts/migrate_to_neon.py, scripts/run_pipeline.sh, src/reddit_api/main.py, and tests/test_migrate_to_neon.py.

## Review baseline

- Read-only local inspection found 67,576 posts, 37,447 comments, 95,273 predictions, and no eligible unscored records. These are a snapshot, not permanent targets.
- One topic contained 24,693 of 24,866 assignments. The cause of this concentration remains unverified.
- 84 focused tests passed; the full pipeline and live database backend were not benchmarked.
- Browser inspection confirmed mismatched chart windows, difficult-to-read cleaned evidence text, and briefs making causal claims beyond their displayed evidence.
- The live UI showed an Ollama cloud configuration. Do not assume inference is local when measuring latency, estimating cost, or changing generation behavior.

## Delivery order

| Phase | Outcome | Depends on | Relative effort |
|---|---|---|---|
| 1 | Consistent filters and correct time-series results | Baseline | Medium |
| 2 | Traceable, restrained analysis and readable evidence | Phase 1 for regenerated results | Medium |
| 3 | Repeatable, versioned daily refresh | Phase 1 contracts | Medium |
| 4 | Less repeated computation and complete search | Phase 3 version contracts | Medium |
| 5 | Validated sentiment and useful topics | Phases 2–4 | Larger, experimental |
| 6 | Clearer dashboard presentation | Phases 1–2 contracts; final checks after 5 | Small–medium |

Effort is comparative; benchmark and evaluation results determine the final size. Each phase should be independently reviewable. Backend correctness and UI presentation can be worked on in parallel once their response contracts are agreed.

## Phase 1 — Correct scope, dates, and change detection

**Evidence and files:** [overview route](../src/api/routes/dashboard.py:26), [sentiment page](../dashboard/app/sentiment/page.tsx:54), [moving averages](../src/ml/timeseries.py:82), [change points](../src/ml/timeseries.py:125), [forecast storage](../src/ml/db.py:355), dashboard/lib/store.ts, src/api/db.py, dashboard/components/charts/ForecastAreaChart.tsx.

Work:
- Define one filter contract for dates, communities, and content type. Document which diagnostic views intentionally cover the entire corpus; label those visibly.
- Pass selected filters to trending topics and sentiment views. Preserve selections on navigation; remove the fixed chart cutoff and disclose any supported-history limit.
- Use calendar-based rolling windows. Treat days without observations as missing, not neutral; expose contributing counts. Keep the existing daily-mean weighting initially and label it explicitly.
- Exclude the terminal PELT boundary, correct boundary indexing, and suppress zero-magnitude shifts.
- Distinguish current forecasts from prior runs. Record generated-at and training-through dates; show the latest run's future horizon separately from historical forecast evaluation.
- Verify the interval coverage actually configured in Prophet; the UI's percentage must match it. Do not infer coverage from an existing label.
- Replace derived results only within the recomputed scope, so obsolete change points and forecasts do not survive merely because persistence uses upserts.

Acceptance:
- A date/community selection survives navigation and scopes overview totals, trending results, sentiment, and evidence consistently.
- Jan 1 = +1 and Feb 1 = −1 produces a Feb 1 seven-day average of −1, not 0. Missing days remain distinguishable from neutral days.
- A constant series emits no shifts; a synthetic step has a correctly located boundary.
- Forecast charts identify their generation date and show exactly the configured future horizon for the current run; prior runs do not appear as current forecasts.
- Repeating the same analysis produces the same derived rows without duplicates or obsolete events.

## Phase 2 — Ground briefs and expose readable evidence

**Evidence and files:** [brief evidence construction](../src/analysis/briefs.py:195), [brief prompt](../src/analysis/prompts.py:143), [overview summaries](../src/api/routes/analysis.py:177), src/analysis/jobs.py, src/analysis/models.py, dashboard/app/briefs/page.tsx, dashboard/app/deep-dive/page.tsx, tests/test_brief_evidence.py.

Work:
- Separate measured observations, possible explanations, and unknowns. A sentiment change alone must not support claims about churn, market share, product releases, or causation.
- Extend the existing evidence validation: resolve anchors to source records, supply representative original excerpts and sample counts, and reject unsupported numbers or unresolved references. Valid IDs alone do not prove that a source supports a claim.
- Require direct source support for specific event descriptions. Where unavailable, retain a neutral description such as “sentiment declined” and expose the evidence gap.
- Distinguish missing collection coverage from zero measured activity; neither establishes a collapse in community engagement.
- Show original post/comment text, title, subreddit, timestamp, and original-thread link in Deep Dive. Keep cleaned model input in an expandable section.
- Version prompts and artifacts. Mark old briefs as historical or superseded rather than silently presenting them as corrected. Regenerate current briefs only after upstream data is validated.

Acceptance:
- Every factual claim in the latest brief has a resolvable evidence link; unsupported explanations are omitted or explicitly labeled hypotheses.
- Fixtures with only sentiment deltas cannot produce accepted causal or churn claims. Conflicting or absent evidence renders a visible limitation.
- Clicking evidence reaches the matching original record without silently changing the selected research scope.
- Original punctuation and casing are visible by default; model input remains inspectable.
- A manual review of the latest brief checks semantic support, beyond automated schema validation.

## Phase 3 — Separate refresh from training and version results

**Evidence and files:** [full pipeline](../scripts/run_pipeline.sh:1194), [unscored selection](../src/ml/db.py:188), [sentiment inference](../src/ml/sentiment.py:288), src/ml/topics.py, src/analysis/db.py, scripts/migrate_to_neon.py, scripts/schedule_historical_collection.py.

Work:
- Provide a routine refresh path: collect, preprocess new records, infer with the current model, assign topics with the current topic model where supported, update aggregates, and generate requested artifacts.
- Make sentiment retraining and topic refitting explicit operations. Preserve the existing full-run entry point as an intentional rebuild option.
- Give models immutable versions based on saved artifacts and preprocessing configuration. A directory path is not a model version.
- Choose an active analysis version; do not aggregate predictions from different versions without identifying that fact. Rescore deliberately when promoting a replacement.
- Give topic models run-specific identities, so a reused numeric topic ID cannot inherit an unrelated old label or historical trend. Audit the apparent difference between three current topics and the much larger stored label inventory before migrating.
- Track completion and freshness using input/version watermarks. Avoid dependency installation on every routine run; use the existing lockfile and an explicit setup/check path.
- Keep SQLite and the optional Neon mirror consistent with changed contracts; mirror once after a successful refresh.

Acceptance:
- An unchanged-data refresh performs no model training, no new embedding work, and no duplicate inference.
- A newly promoted model is distinguishable from the prior model even when stored under the same logical location.
- Restarting an interrupted run resumes incomplete work; partial runs are not reported as fully current.
- Old topic labels cannot attach to a new cluster solely because its integer ID matches.
- Existing single-step and full-run commands retain documented behavior and pass regression checks.

## Phase 4 — Reduce repeated work and repair search completeness

**Evidence and files:** [inference loop](../src/ml/sentiment.py:308), [embedding checkpoints](../src/ml/preprocessing.py:315), [semantic search](../src/analysis/queries.py:563), [summary cache](../src/api/routes/analysis.py:196), src/analysis/db.py.

Work:
- Load tokenizer/model once per inference run and reuse them across database batches.
- Replace repeated full-history embedding copies with bounded checkpoints or chunked storage using existing libraries. Reconcile database rows and vectors after interrupted writes; preserve the existing cache until conversion succeeds.
- Score the eligible embedding matrix with vectorized cosine similarity, select top results, then load their metadata. Apply filters before ranking and handle missing/zero vectors explicitly.
- Remove the arbitrary first-10,000 search boundary. Chunk vector scoring if necessary to bound memory; no new vector database is required by this plan.
- Return deterministic/cached chart summaries immediately. Generate prose on explicit request or during the batch run, with direct lookup by input hash and version.
- Rotate verbose logs and bound retained run logs without discarding the evidence needed to diagnose the latest runs.

Acceptance:
- Multiple inference batches initialize the model exactly once and preserve predictions within the defined numerical tolerance.
- Fault injection between embedding/database writes recovers without permanently skipping records.
- A best-match document beyond row 10,000 is returned; top results match an exact reference calculation on a test corpus.
- Browsing or changing filters makes zero LLM-generation calls; cached results identify their source window and version.
- Compare elapsed time and peak memory on the same fixed corpus/hardware/backend before and after. Prediction and search correctness must pass; measured regressions must be explained before accepting the optimization. Set any numerical speed target after the baseline exists.

## Phase 5 — Evaluate sentiment and restore useful topic separation

**Evidence and files:** [weak labeling](../scripts/generate_weak_labels.py:105), [validation split](../src/ml/sentiment.py:136), [text cleaning](../src/ml/preprocessing.py:115), [topic gate](../src/ml/topics.py:246), scripts/train_topic_model.py, dashboard/app/model-health/page.tsx.

Work:
- Assemble approximately 250 examples stratified by community, time, class, and content type. Include sarcasm, mixed sentiment, and explicit targets. Reserve a held-out portion by thread/time before tuning.
- Establish a short annotation rubric separating general tone from sentiment toward a named product. Human-reviewed labels are the independent reference; agent-only labels are not a substitute.
- Compare VADER and the current classifier on held-out macro F1, per-class errors, and confidence reliability. Present VADER agreement separately from accuracy.
- Preserve natural sentence structure for sentiment and evaluate it against the current cleaned input. Version this change before regenerating predictions.
- Diagnose topic concentration through embedding integrity, sampled source documents, language mix, clustering, reduction, and label freshness. Test a bounded set of configurations rather than forcing an arbitrary topic count.
- Review representative documents for each proposed topic; require labels to describe the cluster as a whole. Consider simple named-product facets as a complement to discovered themes.
- Backtest sentiment forecasts against persistence and recent-average baselines using time-ordered splits. Keep forecasts visibly experimental unless they outperform the selected baseline and interval coverage is reported.

Acceptance:
- The labeled evaluation set, split rules, metrics, and error examples are reproducible; evaluation data is excluded from tuning.
- A replacement sentiment model is promoted only if held-out macro F1 improves without a material per-class regression; record the allowed regression threshold before comparing candidates.
- Confidence is labeled as model confidence, not percent accuracy; show sample size and independent evaluation status.
- Topic review records size distribution, outlier share, and representative-text judgments. Each promoted label accurately describes at least 8 of 10 reviewed representative examples; this is an operational review gate, not a population accuracy estimate.
- If no model improves on the baseline, retain the baseline and document the limitation rather than expanding training complexity.

## Phase 6 — Simplify the UI around exploration

**Files:** dashboard/components/layout/Sidebar.tsx, dashboard/components/overview/PipelineHealthCard.tsx, dashboard/components/overview/ActivityFeedStrip.tsx, dashboard/components/overview/TrendingSignalHero.tsx, dashboard/components/charts/SubredditNetworkGraph.tsx, dashboard/app/briefs/page.tsx, dashboard/app/globals.css, README.md.

Work:
- Use plain labels: “Community groups,” “Comments,” “Last collected,” and “Last analyzed.” Replace the live-stream wording with an accurate batch description.
- Show next scheduled run only when a real schedule is available; otherwise show “Not configured.” Separate data age from processing duration.
- Date forecast activity by generation time, with the horizon shown separately; future predicted dates are not completed activity timestamps.
- Label raw-volume rankings “Most discussed.” Add growth ranking only with a stated comparison period, denominator, and minimum sample requirement.
- Show the latest brief first, collapse older runs, shorten the default view, and put source evidence one click away. Move provider and schema details into diagnostics.
- Increase secondary text contrast and readable chart labels. Add network focus that highlights a selected node and its neighbors; dim unrelated edges and make the selection keyboard accessible.
- Preserve the current visual style and update the outdated README to reflect the actual research intent and supported refresh commands.

Acceptance:
- Overview answers what was collected, through when, what changed, and where to inspect evidence without requiring interpretation of pipeline internals.
- Old briefs remain accessible but do not dominate the initial page. Loading, empty, stale, and failed states are visibly different.
- Normal body/secondary text meets a 4.5:1 contrast target; interactive controls have visible keyboard focus.
- Inspect at the existing desktop viewport and a narrow viewport: no clipped controls, unreadable overlapping selected-node labels, or horizontal overflow in the primary navigation/content.

## Verification and safe rollout

1. Capture baseline timings and screenshots before changes. Add regression coverage for demonstrated bugs before changing their implementation; avoid snapshot-only tests that merely preserve current defects.
2. Validate on a consistent SQLite backup and separate model/cache output locations. Do not copy an active SQLite file without accounting for WAL state. Preserve original data and artifacts for rollback.
3. Run targeted Python tests, then the complete pytest suite with configured coverage; run applicable Python lint/type checks. Run dashboard type checking, API-type consistency checks, and build. Read the installed Next.js guidance before frontend implementation.
4. Extend the existing tests for filter scope, evidence support, reruns, version selection, search completeness, and interrupted checkpoints. Update generated API types whenever contracts change.
5. Verify browser flows end to end: select dates/community → inspect trend → open topic/source → read brief evidence → return with scope preserved. Check actual rendered results after loading completes.
6. For any schema change, provide an additive migration and verify it against both SQLite and an isolated PostgreSQL target before changing the configured mirror. Record a validation gap if the latter is unavailable.
7. Regenerate derived data only after its phase passes. Mark legacy results stale until regeneration completes; retain rollback artifacts until the new dashboard is verified.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Fixes change historical graphs | Preserve a baseline snapshot, identify the analysis version, and explain changed calculation semantics. |
| Topic refits invalidate prior labels | Version cluster identities and prevent cross-run joins by bare numeric ID. |
| Regeneration is expensive | Benchmark first, use incremental refreshes, and promote models deliberately. |
| Human labels are unavailable | Complete the evaluation tooling and sample selection, but leave independent accuracy explicitly unverified. |
| LLM schemas pass while prose overclaims | Combine reference/numeric validation with representative manual semantic review and conservative fallback text. |
| UI shows mixed old/new artifacts | Include source windows, generation times, and version-aware freshness in responses. |
| Cleanup expands into a rewrite | Keep each change focused, reuse existing libraries, and stop when acceptance checks pass. |

## Recommended first delivery

Deliver phases 1 and 2 first: consistent scope, correct time-series calculations, readable source evidence, and restrained briefs. Then make refreshes repeatable and faster before spending time on model experiments or additional visualization features.
