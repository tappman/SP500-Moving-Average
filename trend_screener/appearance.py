"""Shared presentation for the Streamlit workspace and Plotly figures."""
from html import escape

import streamlit as st

INK = "#16263D"
MUTED = "#5B6C80"
TEAL = "#0F766E"
GRID = "#EAF0F5"

LOGO = """<svg viewBox="0 0 40 40" class="brand-logo" aria-hidden="true">
<rect width="40" height="40" rx="12" fill="#16263D"/>
<path d="M9 29H31M9 11V29" stroke="#71849B" stroke-width="1.5" fill="none"/>
<path d="M11 25L17 21L22 23L30 13" stroke="#5EEAD4" stroke-width="2.5"
stroke-linecap="round" stroke-linejoin="round" fill="none"/>
<circle cx="30" cy="13" r="2.5" fill="#5EEAD4"/></svg>"""

CSS = """
<style>
:root {--lab-ink:#16263D; --lab-muted:#5B6C80; --lab-teal:#0F766E;
       --lab-border:#DCE5EE; --lab-surface:#FFFFFF;}
.stApp {background:#F5F7FB;}
.block-container {max-width:1560px; padding-inline:2.4rem; padding-bottom:3rem;}
h1,h2,h3 {color:var(--lab-ink); letter-spacing:-.025em;}
h2 {font-size:1.5rem;} h3 {font-size:1.15rem;}
[data-testid="stCaptionContainer"] {color:var(--lab-muted); line-height:1.55;}
[data-testid="stSidebar"] {background:#EDF2F7; border-right:1px solid var(--lab-border);}
[data-testid="stSidebar"] > div:first-child {padding-top:1rem;}
[data-testid="stSidebar"] h3 {font-size:1rem;}
[data-testid="stWidgetLabel"] p {font-size:.83rem; font-weight:600; color:var(--lab-ink);}
button, input, textarea {font-family:inherit;}
button {transition:background-color .15s ease, border-color .15s ease;}
button:focus-visible, a:focus-visible {outline:3px solid #0F766E !important; outline-offset:3px;}
[data-testid="stBaseButton-primary"] {border-radius:9px; font-weight:650; min-height:2.8rem;}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"]
 {border-radius:8px; border-color:var(--lab-border); font-weight:550;}
[data-testid="stMetric"] {background:white; border:1px solid var(--lab-border);
 border-radius:12px; padding:1rem 1.1rem; min-height:108px; box-shadow:0 2px 5px #16263D04;}
[data-testid="stMetricLabel"] {color:var(--lab-muted); font-size:.78rem;}
[data-testid="stMetricValue"] {color:var(--lab-ink); font-size:clamp(1.3rem,2.1vw,1.9rem);
 font-weight:650; font-variant-numeric:tabular-nums; letter-spacing:-.035em;}
[data-testid="stExpander"] {background:#FFFFFF; border-color:var(--lab-border); border-radius:10px;}
[data-testid="stExpander"] summary {font-size:.88rem; font-weight:600;}
[data-testid="stDataFrame"] {border-radius:10px;}
[data-baseweb="tab-list"] {gap:.2rem; border-bottom:1px solid var(--lab-border); padding-bottom:.3rem;
 overflow-x:auto; scrollbar-width:thin;}
[data-baseweb="tab"] {padding:.55rem .85rem; border-radius:8px; color:var(--lab-muted);
 font-size:.84rem; white-space:nowrap;}
[data-baseweb="tab"][aria-selected="true"] {color:var(--lab-teal); background:#E6F3F0; font-weight:650;}
[data-testid="stAlert"] {border-radius:10px;}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:var(--lab-border); border-radius:12px;}
.lab-header {display:flex; justify-content:space-between; gap:2rem; align-items:center;
 margin-bottom:1.4rem; padding:.2rem 0 1.1rem;}
.lab-brand {display:flex; align-items:center; gap:.9rem;}
.brand-logo {width:44px; height:44px; flex-shrink:0;}
.lab-eyebrow {color:var(--lab-teal); font-size:.68rem; font-weight:750; letter-spacing:.15em;
 text-transform:uppercase; margin:0 0 .3rem;}
.lab-header h1 {font-size:2.25rem; line-height:1.16; margin:0; padding:0; font-weight:700;}
.lab-subtitle {color:var(--lab-muted); margin:.65rem 0 0; font-size:.95rem; line-height:1.5;}
.lab-session {text-align:right; flex-shrink:0; font-size:.81rem; color:var(--lab-muted); line-height:1.65;}
.lab-session strong {display:block; color:var(--lab-ink); font-size:.95rem; font-weight:650;}
.lab-pill {display:inline-block; background:#E6F3F0; color:#086558; border:1px solid #C8E7E0;
 padding:.18rem .55rem; border-radius:999px; font-size:.67rem; font-weight:750; letter-spacing:.05em;}
.lab-pill.demo {background:#FFF4DB; color:#8A4B08; border-color:#F2DFB9;}
.lab-sidebar-brand {display:flex; gap:.7rem; align-items:center; padding:0 0 1.25rem;}
.lab-sidebar-brand strong {font-size:.95rem; color:var(--lab-ink);}
.lab-sidebar-brand small {display:block; font-size:.73rem; color:var(--lab-muted);}
.lab-sidebar-brand .brand-logo {width:36px; height:36px;}
.lab-context {display:flex; flex-wrap:wrap; gap:.7rem 1.8rem; margin:.6rem 0 1.3rem;
 padding:.85rem 1.1rem; background:white; border:1px solid var(--lab-border); border-radius:10px;}
.lab-context span {font-size:.78rem; color:var(--lab-muted);}
.lab-context strong {font-weight:650; color:var(--lab-ink); margin-left:.35rem;}
.lab-toolbar-title {font-size:.87rem; font-weight:650; color:var(--lab-ink); margin:.1rem 0;}
.lab-toolbar-copy {font-size:.79rem; color:var(--lab-muted); margin:0; line-height:1.5;}
.st-key-run_toolbar {background:white; margin-bottom:1rem;}
.lab-empty {background:white; border:1px dashed #C9D7E5; border-radius:14px; padding:2.7rem 2rem;
 margin-top:1rem; text-align:center;}
.lab-empty .brand-logo {width:46px; height:46px; margin:0 auto 1rem;}
.lab-empty h3 {font-size:1.12rem; font-weight:650; margin:0 0 .5rem;}
.lab-empty p {color:var(--lab-muted); font-size:.88rem; max-width:34rem; margin:auto; line-height:1.65;}
.lab-footer {color:var(--lab-muted); font-size:.73rem; border-top:1px solid var(--lab-border);
 padding-top:1rem; margin-top:2rem; line-height:1.6;}
@media (max-width:800px) {
 .block-container {padding-inline:1rem; padding-bottom:2rem;}
 .lab-header {align-items:flex-start; gap:1rem; flex-wrap:wrap;}
 .lab-header h1 {font-size:1.85rem;}
 .lab-session {text-align:left; padding-left:3.65rem;}
 .lab-context {gap:.6rem 1.1rem;}
}
@media (max-width:640px) {
 [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
 [data-testid="stColumn"] {min-width:100% !important; flex:1 1 100% !important;}
 [data-testid="stMetric"] {min-height:90px;}
 [data-baseweb="tab"] {padding:.5rem .65rem;}
}
@media (prefers-reduced-motion:reduce) {button {transition:none;}}
</style>
"""


def apply_workspace_style():
    st.markdown(CSS, unsafe_allow_html=True)


def sidebar_brand():
    st.markdown(f"""<div class="lab-sidebar-brand">{LOGO}<div>
    <strong>MA Trend Lab</strong><small>Research workspace</small></div></div>""", unsafe_allow_html=True)


def workspace_header(run=None, *, demo=False):
    if run is None:
        session = '<span class="lab-pill">DAILY CLOSE RESEARCH</span><strong>Build your first screen</strong>Configure · Run · Explore'
    else:
        badge = '<span class="lab-pill demo">SYNTHETIC DEMO</span>' if demo else '<span class="lab-pill">SCREEN COMPLETE</span>'
        session = f'{badge}<strong>{escape(str(run.screen_date))}</strong>{len(run.table):,} symbols · {len(run.passing):,} matches'
    st.markdown(f"""<header class="lab-header"><div>
    <div class="lab-brand">{LOGO}<div><p class="lab-eyebrow">Market research, made clear</p>
    <h1>MA Trend Lab</h1></div></div>
    <p class="lab-subtitle">Screen trends. Compare risk. Inspect the evidence.</p></div>
    <div class="lab-session">{session}</div></header>""", unsafe_allow_html=True)


def context_strip(items):
    content = "".join(f"<span>{escape(str(label))}<strong>{escape(str(value))}</strong></span>"
                      for label, value in items)
    st.markdown(f'<div class="lab-context">{content}</div>', unsafe_allow_html=True)


def empty_state(title, description):
    st.markdown(f"""<section class="lab-empty">{LOGO}<h3>{escape(title)}</h3>
    <p>{escape(description)}</p></section>""", unsafe_allow_html=True)


def style_figure(fig, *, compact=False):
    """Apply consistent colors and typography without changing plotted data."""
    fig.update_layout(
        font={"family": "Inter, Segoe UI, -apple-system, sans-serif", "size": 11 if compact else 12, "color": INK},
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        title_font={"size": 16 if compact else 20, "color": INK},
        hoverlabel={"bgcolor": "#FFFFFF", "bordercolor": "#DCE5EE", "font": {"color": INK, "size": 12}},
        legend={"font": {"size": 10 if compact else 11}, "bgcolor": "rgba(0,0,0,0)"},
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor="#DCE5EE", tickfont={"color": MUTED}, automargin=True)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor="#DCE5EE", tickfont={"color": MUTED}, automargin=True)
    return fig


def show_figure(fig, *, key):
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", key=key,
                        config={"displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}})
