"""Reddit Analyzer dashboard theme — visual tokens, Plotly template, and reusable components.

Single source of truth for all visual styling. Call `inject_theme()` once at the top of
the main Streamlit entry point (after `st.set_page_config`).
"""

from __future__ import annotations

import html
from contextlib import contextmanager
from typing import Iterator, Optional

import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Color tokens (also expressed as CSS variables below — keep in sync)
# ---------------------------------------------------------------------------

BG = "#0B0C0E"
SURFACE = "#141619"
ELEVATED = "#1C1F23"
BORDER = "rgba(255,255,255,0.06)"
BORDER_STRONG = "rgba(255,255,255,0.12)"
TEXT = "#F3F4F6"
TEXT_MUTED = "#9CA3AF"
TEXT_SUBTLE = "#6B7280"
ACCENT = "#F59E0B"
ACCENT_SOFT = "rgba(245,158,11,0.14)"

SENTIMENT_COLORS = {
    "positive": "#34D399",
    "neutral": "#94A3B8",
    "negative": "#F87171",
}

# Amber-anchored qualitative palette for multi-series charts (colorblind-safe)
COLOR_SEQUENCE = [
    "#F59E0B",
    "#7C9AFF",
    "#34D399",
    "#F87171",
    "#A78BFA",
    "#FBBF24",
    "#60A5FA",
    "#FB923C",
]

# Diverging scale for heatmaps — coral → elevated surface → emerald
DIVERGING_SCALE = [
    [0.0, "#F87171"],
    [0.5, "#1C1F23"],
    [1.0, "#34D399"],
]

# Sequential amber scale used for the wordcloud & select continuous charts
AMBER_SEQUENTIAL = [
    [0.0, "#3A2A0C"],
    [0.5, "#B97309"],
    [1.0, "#FBBF24"],
]

COMPACT_MARGIN = dict(l=16, r=16, t=20, b=20)

# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------

PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Geist, -apple-system, system-ui, sans-serif", size=13, color=TEXT),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=COLOR_SEQUENCE,
        hoverlabel=dict(
            bgcolor=ELEVATED,
            bordercolor=ACCENT,
            font=dict(family="Geist Mono, monospace", size=12, color=TEXT),
        ),
        xaxis=dict(
            gridcolor=BORDER,
            linecolor=BORDER_STRONG,
            zerolinecolor=BORDER_STRONG,
            tickfont=dict(color=TEXT_MUTED, size=11),
            title=dict(font=dict(color=TEXT_MUTED, size=12)),
        ),
        yaxis=dict(
            gridcolor=BORDER,
            linecolor=BORDER_STRONG,
            zerolinecolor=BORDER_STRONG,
            tickfont=dict(color=TEXT_MUTED, size=11),
            title=dict(font=dict(color=TEXT_MUTED, size=12)),
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor=BORDER,
            borderwidth=0,
            font=dict(color=TEXT_MUTED, size=11),
        ),
        margin=COMPACT_MARGIN,
        title=dict(
            font=dict(family="Instrument Serif, Georgia, serif", size=18, color=TEXT),
            x=0.0,
            xanchor="left",
        ),
    )
)

# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap');

:root {
  --bg: #0B0C0E;
  --surface: #141619;
  --elevated: #1C1F23;
  --border: rgba(255,255,255,0.06);
  --border-strong: rgba(255,255,255,0.12);
  --text: #F3F4F6;
  --text-muted: #9CA3AF;
  --text-subtle: #6B7280;
  --accent: #F59E0B;
  --accent-soft: rgba(245,158,11,0.14);
  --pos: #34D399;
  --neu: #94A3B8;
  --neg: #F87171;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
  background: var(--bg);
  color: var(--text);
  font-family: 'Geist', -apple-system, system-ui, sans-serif;
  font-feature-settings: "cv11", "ss01";
}

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stDeployButton"] { display: none !important; }
[data-testid="stHeader"] { background: transparent; height: 0; }
[data-testid="stToolbar"] { display: none !important; }

/* Main block container */
.block-container {
  padding-top: 2.25rem;
  padding-bottom: 4rem;
  max-width: 1400px;
}

/* Sidebar */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #141619 0%, #0F1113 100%);
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .block-container {
  padding-top: 1.75rem;
}
[data-testid="stSidebar"] hr {
  margin: 1.25rem 0;
}

/* Typography */
h1, h2, h3, h4 {
  font-family: 'Instrument Serif', Georgia, serif;
  font-weight: 400;
  letter-spacing: -0.005em;
  color: var(--text);
}
h1 { font-size: 2.25rem; line-height: 1.1; }
h2 { font-size: 1.625rem; line-height: 1.2; margin-top: 0.5rem; }
h3 { font-size: 1.2rem; line-height: 1.3; }
p, label, span, div { color: inherit; }
[data-testid="stCaptionContainer"], .stCaption, small {
  color: var(--text-muted) !important;
  font-family: 'Geist', sans-serif;
  font-size: 0.8rem;
}

/* Built-in metric (fallback for anywhere we keep st.metric) */
[data-testid="stMetric"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.25rem;
}
[data-testid="stMetricLabel"] {
  font-size: 0.7rem !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted) !important;
}
[data-testid="stMetricValue"] {
  font-family: 'Instrument Serif', serif !important;
  font-size: 1.9rem !important;
  color: var(--text) !important;
  font-feature-settings: "tnum";
}

/* Tabs (pill/underline style) */
[data-testid="stTabs"] [role="tablist"] {
  gap: 0;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
}
[data-testid="stTabs"] [role="tab"] {
  background: transparent;
  color: var(--text-muted);
  font-family: 'Geist', sans-serif;
  font-weight: 500;
  font-size: 0.875rem;
  padding: 0.75rem 1.25rem;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  transition: color 0.15s ease, border-color 0.15s ease;
}
[data-testid="stTabs"] [role="tab"]:hover { color: var(--text); }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: var(--text);
  border-bottom-color: var(--accent);
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
  background-color: var(--accent) !important;
}
/* Group divider — Deep Dive | Model Health */
[data-testid="stTabs"] [role="tab"]:nth-child(5) {
  margin-left: 18px;
  padding-left: 22px;
  border-left: 1px solid var(--border);
}

/* Buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  background: var(--elevated);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-family: 'Geist', sans-serif;
  font-weight: 500;
  font-size: 0.85rem;
  padding: 0.5rem 1rem;
  transition: all 0.15s ease;
  box-shadow: none;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background: var(--surface);
  border-color: var(--border-strong);
  color: var(--text);
}
.stButton > button[kind="primary"] {
  background: var(--accent);
  color: #0B0C0E;
  border-color: var(--accent);
  font-weight: 600;
}
.stButton > button[kind="primary"]:hover {
  background: #FBBF24;
  color: #0B0C0E;
  border-color: #FBBF24;
}
.stButton > button:disabled,
.stButton > button[kind="primary"]:disabled {
  background: var(--surface) !important;
  color: var(--text-subtle) !important;
  border-color: var(--border) !important;
  opacity: 0.55;
}
.stDownloadButton > button {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border-strong);
}
.stDownloadButton > button:hover {
  color: var(--accent);
  border-color: var(--accent);
}

/* Inputs */
.stTextInput input, .stNumberInput input, .stDateInput input {
  background: var(--surface) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  font-family: 'Geist', sans-serif;
}
.stTextInput input:focus, .stNumberInput input:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-soft) !important;
}

/* Multiselect / Selectbox (BaseWeb) */
[data-baseweb="select"] > div,
[data-baseweb="input"] {
  background: var(--surface) !important;
  border-color: var(--border) !important;
  border-radius: 8px !important;
}
[data-baseweb="tag"] {
  background: var(--accent-soft) !important;
  border-radius: 6px !important;
}
[data-baseweb="tag"] > div {
  color: var(--accent) !important;
}

/* Radio */
[data-testid="stRadio"] label, [data-testid="stRadio"] p {
  color: var(--text-muted);
  font-size: 0.85rem;
}
[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
  border-color: var(--border-strong) !important;
}

/* Slider */
[data-testid="stSlider"] [data-baseweb="slider"] > div > div {
  background: var(--border) !important;
}
[data-testid="stSlider"] [role="slider"] {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
}

/* Dataframe */
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
[data-testid="stDataFrame"] div[role="columnheader"] {
  background: var(--elevated) !important;
  color: var(--text-muted) !important;
  font-family: 'Geist Mono', monospace !important;
  font-size: 0.72rem !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Code blocks */
[data-testid="stCodeBlock"], pre {
  background: #0A0B0D !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
}
[data-testid="stCodeBlock"] code, pre code {
  font-family: 'Geist Mono', 'SF Mono', monospace !important;
  font-size: 0.78rem !important;
  color: #D4D7DC !important;
}

/* Bordered container (chart_card) */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--surface);
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  padding: 1.25rem 1.375rem !important;
}

/* Alerts (info/success/warning/error) */
[data-testid="stAlert"], [data-testid="stNotification"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  color: var(--text-muted) !important;
}
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
  color: var(--text-muted) !important;
  font-size: 0.85rem;
}

/* Divider */
hr {
  border-color: var(--border) !important;
  opacity: 1;
}

/* Plotly chart background — ensure transparent around our dark surface */
.js-plotly-plot .plotly .main-svg {
  background: transparent !important;
}

/* Scrollbars */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb {
  background: var(--elevated);
  border-radius: 6px;
  border: 2px solid var(--bg);
}
::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

/* ----- Custom components ----- */

.ra-sidebar-brand {
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.25rem;
}
.ra-eyebrow {
  font-family: 'Geist Mono', monospace;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--text-subtle);
  margin-bottom: 0.5rem;
}
.ra-wordmark {
  font-family: 'Instrument Serif', serif;
  font-size: 2rem;
  line-height: 1;
  color: var(--text);
  margin: 0;
  letter-spacing: -0.01em;
}
.ra-wordmark-sub {
  font-family: 'Geist', sans-serif;
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-top: 0.5rem;
  line-height: 1.4;
}
.ra-sidebar-filters-label {
  font-family: 'Geist Mono', monospace;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
  margin-top: 0.5rem;
}
.ra-sidebar-footer {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
  font-family: 'Geist Mono', monospace;
  font-size: 0.68rem;
  color: var(--text-subtle);
  letter-spacing: 0.02em;
}

/* Metric card */
.ra-metric {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.125rem 1.25rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  min-height: 108px;
}
.ra-metric-label {
  font-family: 'Geist Mono', monospace;
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.425rem;
}
.ra-metric-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.ra-metric-dot.pos { background: var(--pos); box-shadow: 0 0 0 3px rgba(52,211,153,0.15); }
.ra-metric-dot.neu { background: var(--neu); box-shadow: 0 0 0 3px rgba(148,163,184,0.15); }
.ra-metric-dot.neg { background: var(--neg); box-shadow: 0 0 0 3px rgba(248,113,113,0.15); }
.ra-metric-value {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 2.15rem;
  font-weight: 400;
  line-height: 1;
  color: var(--text);
  font-feature-settings: "tnum";
  letter-spacing: -0.01em;
}
.ra-metric-value.compact {
  font-size: 1.1rem;
  font-family: 'Geist Mono', monospace;
  letter-spacing: 0;
}
.ra-metric-delta {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-family: 'Geist Mono', monospace;
  font-size: 0.72rem;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}
.ra-metric-delta.good { color: var(--pos); }
.ra-metric-delta.bad { color: var(--neg); }

/* Chart / container card header (used inside bordered container) */
.ra-card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin: -0.25rem 0 0.875rem 0;
  gap: 1rem;
}
.ra-card-title {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 1.2rem;
  color: var(--text);
  letter-spacing: -0.005em;
  line-height: 1.2;
}
.ra-card-subtitle {
  font-family: 'Geist', sans-serif;
  font-size: 0.78rem;
  color: var(--text-muted);
  text-align: right;
}

/* Section header (above chart groups) */
.ra-section {
  margin: 0.25rem 0 1rem 0;
}
.ra-section-eyebrow {
  font-family: 'Geist Mono', monospace;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--accent);
  margin-bottom: 0.45rem;
}
.ra-section-title {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 1.75rem;
  color: var(--text);
  line-height: 1.1;
  margin: 0;
  letter-spacing: -0.01em;
}
.ra-section-subtitle {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-top: 0.45rem;
  max-width: 68ch;
  line-height: 1.5;
}

/* Tab group labels (ANALYTICS | OPERATIONS) */
.ra-tab-group-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-family: 'Geist Mono', monospace;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--text-subtle);
  margin-top: 1.25rem;
  margin-bottom: 0.375rem;
  padding: 0 2px;
}
.ra-tab-group-header .right { color: var(--text-subtle); }

/* Filter bar (used above tab content filters) */
.ra-filter-bar {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.75rem 1rem 0.5rem;
  margin-bottom: 1rem;
}

/* Pipeline — step card */
.ra-step {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.875rem 1.125rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 0.625rem;
  transition: border-color 0.15s ease;
}
.ra-step:hover { border-color: var(--border-strong); }
.ra-step.done { border-color: rgba(52,211,153,0.18); }
.ra-step-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--text-subtle);
}
.ra-step-dot.done { background: var(--pos); box-shadow: 0 0 0 3px rgba(52,211,153,0.15); }
.ra-step-dot.waiting { background: var(--text-subtle); opacity: 0.5; }
.ra-step-num {
  font-family: 'Instrument Serif', serif;
  font-size: 1.35rem;
  color: var(--text-subtle);
  min-width: 1.5rem;
  text-align: center;
}
.ra-step-body { flex: 1; min-width: 0; }
.ra-step-name {
  font-family: 'Geist', sans-serif;
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--text);
  letter-spacing: -0.005em;
}
.ra-step-desc {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 0.125rem;
  line-height: 1.4;
}

/* Pipeline progress ribbon */
.ra-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0.875rem 1.125rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 1.125rem;
}
.ra-progress-dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--text-subtle);
  opacity: 0.35;
  flex-shrink: 0;
}
.ra-progress-dot.done {
  background: var(--pos);
  opacity: 1;
  box-shadow: 0 0 0 3px rgba(52,211,153,0.15);
}
.ra-progress-bar {
  flex: 1;
  height: 1px;
  background: var(--border);
  min-width: 10px;
}
.ra-progress-bar.done { background: rgba(52,211,153,0.4); }
.ra-progress-caption {
  margin-left: 1rem;
  font-family: 'Geist Mono', monospace;
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  white-space: nowrap;
}

/* Terminal card header */
.ra-terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}
.ra-terminal-title {
  font-family: 'Geist Mono', monospace;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--text-muted);
}
.ra-terminal-dots {
  display: inline-flex;
  gap: 5px;
}
.ra-terminal-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.ra-terminal-dots span:nth-child(1) { background: #F87171; opacity: 0.6; }
.ra-terminal-dots span:nth-child(2) { background: #FBBF24; opacity: 0.6; }
.ra-terminal-dots span:nth-child(3) { background: #34D399; opacity: 0.6; }

/* Keyword chip (used in deep dive / topic cards) */
.ra-chip {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: var(--elevated);
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-family: 'Geist Mono', monospace;
  font-size: 0.72rem;
  margin: 0.15rem 0.25rem 0.15rem 0;
}
</style>
"""


def inject_theme() -> None:
    """Inject the Google Fonts @import and full CSS theme. Call once at app startup.

    Uses `st.html` when available (Streamlit 1.33+) to bypass markdown sanitization
    which can strip or linearize <style> blocks.
    """
    if hasattr(st, "html"):
        st.html(_CSS)
    else:  # pragma: no cover — legacy Streamlit
        st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Reusable components
# ---------------------------------------------------------------------------


def metric_card(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_good: bool = True,
    dot: Optional[str] = None,
    compact: bool = False,
) -> None:
    """Render a styled metric tile. `dot` may be 'pos' | 'neu' | 'neg' | None."""
    label_esc = html.escape(str(label))
    value_esc = html.escape(str(value))
    dot_html = (
        f'<span class="ra-metric-dot {html.escape(dot)}"></span>' if dot else ""
    )
    value_class = "ra-metric-value compact" if compact else "ra-metric-value"
    if delta is not None:
        delta_cls = "good" if delta_good else "bad"
        delta_html = (
            f'<div class="ra-metric-delta {delta_cls}">{html.escape(str(delta))}</div>'
        )
    else:
        delta_html = ""
    st.markdown(
        f'<div class="ra-metric">'
        f'<div class="ra-metric-label">{dot_html}{label_esc}</div>'
        f'<div class="{value_class}">{value_esc}</div>'
        f"{delta_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def section_header(
    title: str,
    subtitle: Optional[str] = None,
    eyebrow: Optional[str] = None,
) -> None:
    """Render an eyebrow + serif title + subtitle block."""
    eyebrow_html = (
        f'<div class="ra-section-eyebrow">{html.escape(eyebrow)}</div>' if eyebrow else ""
    )
    subtitle_html = (
        f'<div class="ra-section-subtitle">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f'<div class="ra-section">'
        f"{eyebrow_html}"
        f'<div class="ra-section-title">{html.escape(title)}</div>'
        f"{subtitle_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


@contextmanager
def chart_card(
    title: str, subtitle: Optional[str] = None
) -> Iterator[None]:
    """Open a bordered container with a serif title header. Yields inside it."""
    try:
        container = st.container(border=True)  # Streamlit >= 1.29
    except TypeError:  # pragma: no cover — older Streamlit fallback
        container = st.container()
    with container:
        subtitle_html = (
            f'<div class="ra-card-subtitle">{html.escape(subtitle)}</div>'
            if subtitle
            else ""
        )
        st.markdown(
            f'<div class="ra-card-header">'
            f'<div class="ra-card-title">{html.escape(title)}</div>'
            f"{subtitle_html}"
            f"</div>",
            unsafe_allow_html=True,
        )
        yield


def tab_group_header(left: str = "Analytics", right: str = "Operations") -> None:
    """Render an eyebrow row that sits above st.tabs to hint at tab grouping."""
    st.markdown(
        f'<div class="ra-tab-group-header">'
        f"<span>{html.escape(left)}</span>"
        f'<span class="right">{html.escape(right)}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def sidebar_brand(
    title: str, subtitle: str, eyebrow: str = "Dashboard v1"
) -> None:
    """Render the sidebar wordmark with eyebrow + serif title + caption."""
    st.markdown(
        f'<div class="ra-sidebar-brand">'
        f'<div class="ra-eyebrow">{html.escape(eyebrow)}</div>'
        f'<div class="ra-wordmark">{html.escape(title)}</div>'
        f'<div class="ra-wordmark-sub">{html.escape(subtitle)}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def sidebar_eyebrow(text: str) -> None:
    """Small uppercase label used above sidebar filter groups."""
    st.markdown(
        f'<div class="ra-sidebar-filters-label">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def sidebar_footer(text: str) -> None:
    st.markdown(
        f'<div class="ra-sidebar-footer">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def terminal_header(title: str = "Output") -> None:
    """Header row for the pipeline output terminal — three status dots + title."""
    st.markdown(
        f'<div class="ra-terminal-header">'
        f'<div class="ra-terminal-title">{html.escape(title)}</div>'
        f'<div class="ra-terminal-dots"><span></span><span></span><span></span></div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def progress_ribbon(statuses: dict, caption: Optional[str] = None) -> None:
    """Render a horizontal progress dot-chain from a {step_num: bool_done} dict."""
    keys = sorted(statuses.keys())
    parts = []
    for i, k in enumerate(keys):
        done_cls = "done" if statuses[k] else ""
        parts.append(f'<div class="ra-progress-dot {done_cls}"></div>')
        if i < len(keys) - 1:
            next_done = "done" if (statuses[k] and statuses[keys[i + 1]]) else ""
            parts.append(f'<div class="ra-progress-bar {next_done}"></div>')
    caption_html = (
        f'<div class="ra-progress-caption">{html.escape(caption)}</div>'
        if caption
        else ""
    )
    st.markdown(
        f'<div class="ra-progress">{"".join(parts)}{caption_html}</div>',
        unsafe_allow_html=True,
    )


def step_card(
    step_num: int,
    name: str,
    description: str,
    state: str = "waiting",
) -> None:
    """Render the non-button portion of a pipeline step row.

    `state` ∈ {'done', 'waiting'}. The caller places a Run button next to this.
    """
    state_cls = "done" if state == "done" else "waiting"
    wrap_cls = "ra-step done" if state == "done" else "ra-step"
    st.markdown(
        f'<div class="{wrap_cls}">'
        f'<div class="ra-step-dot {state_cls}"></div>'
        f'<div class="ra-step-num">{int(step_num):02d}</div>'
        f'<div class="ra-step-body">'
        f'<div class="ra-step-name">{html.escape(name)}</div>'
        f'<div class="ra-step-desc">{html.escape(description)}</div>'
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
