"""
Visual theme for Lab Inventory — PrivaSI Lab design identity.
Call apply_styles() once per page render (in main()).
"""

import streamlit as st

# ── Design tokens ──────────────────────────────────────────────────────────────
# Modify only these values to update the entire theme.
_TOKENS = {
    "navy":       "#001A4B",   # primary text, headings
    "dark_teal":  "#002E3B",   # sidebar, header bar
    "sky_blue":   "#6EC1E4",   # accent, buttons, links
    "steel_blue": "#5BC0DE",   # button hover
    "mid_blue":   "#476ABC",   # active nav, active tab
    "muted_teal": "#80A9B5",   # captions, sidebar secondary text
    "off_white":  "#F8F8F8",   # alternating section bg, metric cards
    "hero":       "#071632",   # dark hero/banner sections
    "border":     "#EFEFEF",   # card/input borders
    "divider":    "#E0E0E0",   # hr dividers
}

_CSS = """
<style>
/* ── Google Fonts ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Karla:wght@300;400;500;600;700&family=Roboto:wght@300;400;500;700&display=swap');

/* ── CSS custom properties (design tokens) ───────────────────────────────── */
:root {{
  --c-navy:       {navy};
  --c-dark-teal:  {dark_teal};
  --c-sky:        {sky_blue};
  --c-steel:      {steel_blue};
  --c-mid-blue:   {mid_blue};
  --c-muted:      {muted_teal};
  --c-off-white:  {off_white};
  --c-hero:       {hero};
  --c-border:     {border};
  --c-divider:    {divider};
  --font-primary:   'Karla', sans-serif;
  --font-secondary: 'Roboto', sans-serif;
}}

/* ── Global ──────────────────────────────────────────────────────────────── */
html, body, .stApp {{
  font-family: var(--font-primary);
  background-color: #FFFFFF;
  color: var(--c-navy);
}}

/* ── Top toolbar (hamburger bar) ─────────────────────────────────────────── */
[data-testid="stHeader"] {{
  background-color: #FFFFFF !important;
  border-bottom: 1px solid var(--c-border);
}}
[data-testid="stHeader"] button svg {{
  fill: var(--c-navy) !important;
}}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
  background-color: var(--c-navy) !important;
  border-right: none;
}}
[data-testid="stSidebar"] * {{
  color: #FFFFFF !important;
}}
/* Sidebar title */
[data-testid="stSidebar"] h1 {{
  font-family: var(--font-primary) !important;
  font-size: 1.25rem !important;
  font-weight: 600 !important;
  color: #FFFFFF !important;
  border-bottom: none !important;
  padding-bottom: 0 !important;
  margin-bottom: 0 !important;
  letter-spacing: 0.5px;
}}
/* Sidebar caption / signed-in text */
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] small {{
  color: var(--c-muted) !important;
  font-size: 13px !important;
  font-weight: 300 !important;
}}
/* Sidebar radio nav items */
[data-testid="stSidebar"] [data-testid="stRadio"] label p {{
  font-family: var(--font-primary) !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  color: rgba(255,255,255,0.85) !important;
  transition: color 0.15s;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover p {{
  color: var(--c-sky) !important;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] [data-checked="true"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p {{
  color: var(--c-sky) !important;
  font-weight: 700 !important;
}}
/* Sidebar dividers */
[data-testid="stSidebar"] hr {{
  border-color: rgba(110,193,228,0.2) !important;
  margin: 0.6rem 0 !important;
}}
/* Sidebar logout button — must override the global button rule */
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] [data-testid="baseButton-secondary"],
[data-testid="stSidebar"] [data-testid="baseButton-primary"] {{
  background-color: transparent !important;
  border: 1px solid rgba(110,193,228,0.6) !important;
  color: var(--c-sky) !important;
  font-family: var(--font-primary) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  padding: 6px 14px !important;
  width: 100%;
  margin-top: 2px;
  border-radius: 4px !important;
  box-shadow: none !important;
}}
[data-testid="stSidebar"] .stButton > button:hover,
[data-testid="stSidebar"] [data-testid="baseButton-secondary"]:hover,
[data-testid="stSidebar"] [data-testid="baseButton-primary"]:hover {{
  background-color: var(--c-sky) !important;
  color: #FFFFFF !important;
  border-color: var(--c-sky) !important;
}}

/* ── Main block container ─────────────────────────────────────────────────── */
.main .block-container,
[data-testid="stMainBlockContainer"] {{
  background-color: #FFFFFF;
  padding-top: 2rem;
  padding-bottom: 3rem;
}}

/* ── Typography ──────────────────────────────────────────────────────────── */
h1 {{
  font-family: var(--font-primary) !important;
  font-size: 1.85rem !important;
  font-weight: 600 !important;
  color: var(--c-navy) !important;
  letter-spacing: -0.4px;
  line-height: 1.2;
  border-bottom: 2px solid var(--c-sky);
  padding-bottom: 0.35rem;
  margin-bottom: 1.2rem;
}}
h2 {{
  font-family: var(--font-secondary) !important;
  font-size: 1.35rem !important;
  font-weight: 500 !important;
  color: var(--c-navy) !important;
  line-height: 1.2;
  margin-top: 1rem;
}}
h3 {{
  font-family: var(--font-primary) !important;
  font-size: 1.05rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.3px;
  color: var(--c-navy) !important;
}}
p, li {{
  font-family: var(--font-primary);
  font-weight: 300;
  line-height: 1.6;
  color: var(--c-navy);
}}

/* ── Buttons (main area) ─────────────────────────────────────────────────── */
/* Base — all buttons start with an outline style */
.stButton > button,
[data-testid="baseButton-secondary"] {{
  font-family: var(--font-primary) !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  background-color: #FFFFFF !important;
  color: var(--c-sky) !important;
  border: 1.5px solid var(--c-sky) !important;
  border-radius: 4px !important;
  padding: 8px 20px !important;
  transition: background-color 0.18s ease, color 0.18s ease !important;
  box-shadow: none !important;
}}
.stButton > button:hover,
[data-testid="baseButton-secondary"]:hover {{
  background-color: var(--c-sky) !important;
  color: #FFFFFF !important;
  border-color: var(--c-sky) !important;
}}
/* Primary buttons — filled sky blue */
[data-testid="baseButton-primary"],
button[kind="primaryFormSubmit"] {{
  background-color: var(--c-sky) !important;
  color: #FFFFFF !important;
  border: 1.5px solid var(--c-sky) !important;
  border-radius: 4px !important;
  font-family: var(--font-primary) !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  padding: 8px 20px !important;
  box-shadow: none !important;
  transition: background-color 0.18s ease !important;
}}
[data-testid="baseButton-primary"]:hover,
button[kind="primaryFormSubmit"]:hover {{
  background-color: var(--c-mid-blue) !important;
  border-color: var(--c-mid-blue) !important;
  color: #FFFFFF !important;
}}

/* ── Input fields ────────────────────────────────────────────────────────── */
.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stDateInput input {{
  font-family: var(--font-primary);
  font-weight: 300;
  border: 1px solid var(--c-border) !important;
  border-radius: 4px !important;
  color: var(--c-navy) !important;
  background-color: #FFFFFF !important;
}}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {{
  border-color: var(--c-sky) !important;
  box-shadow: 0 0 0 2px rgba(110,193,228,0.18) !important;
}}
/* Field labels */
.stTextInput label,
.stNumberInput label,
.stSelectbox label,
.stMultiSelect label,
.stTextArea label,
.stDateInput label,
.stRadio > label,
.stCheckbox > label,
.stToggle > label {{
  font-family: var(--font-primary) !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  color: var(--c-navy) !important;
}}
/* Selectbox */
.stSelectbox > div > div {{
  border: 1px solid var(--c-border) !important;
  border-radius: 4px !important;
  font-family: var(--font-primary);
  color: var(--c-navy) !important;
}}

/* ── Metric cards ────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
  background-color: var(--c-off-white);
  border: 1px solid var(--c-border);
  border-radius: 6px;
  padding: 18px 22px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
[data-testid="stMetricLabel"] p {{
  font-family: var(--font-primary) !important;
  font-size: 13px !important;
  font-weight: 400 !important;
  color: var(--c-navy) !important;
  text-transform: uppercase;
  letter-spacing: 0.6px;
}}
[data-testid="stMetricValue"] {{
  font-family: var(--font-primary) !important;
  font-size: 2rem !important;
  font-weight: 600 !important;
  color: var(--c-navy) !important;
}}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
  border-bottom: 2px solid var(--c-border);
  gap: 0;
  background-color: transparent;
}}
.stTabs [data-baseweb="tab"] {{
  font-family: var(--font-primary) !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  color: var(--c-navy) !important;
  border-radius: 4px 4px 0 0;
  padding: 8px 18px;
  background-color: transparent !important;
  border: none !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
  color: var(--c-sky) !important;
  background-color: var(--c-off-white) !important;
}}
.stTabs [aria-selected="true"] {{
  color: var(--c-mid-blue) !important;
  border-bottom: 2px solid var(--c-mid-blue) !important;
  background-color: var(--c-off-white) !important;
}}

/* ── Expander ─────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
  border: 1px solid var(--c-border) !important;
  border-radius: 6px !important;
  background-color: #FFFFFF;
}}
[data-testid="stExpander"] summary {{
  font-family: var(--font-primary) !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  color: var(--c-navy) !important;
  background-color: var(--c-off-white);
  border-radius: 6px;
  padding: 10px 14px;
}}
[data-testid="stExpander"] summary:hover {{
  color: var(--c-sky) !important;
}}

/* ── Alerts / info boxes ─────────────────────────────────────────────────── */
[data-testid="stAlert"] {{
  border-radius: 4px !important;
  font-family: var(--font-primary) !important;
  font-weight: 300 !important;
}}

/* ── Caption / small text ────────────────────────────────────────────────── */
[data-testid="stCaptionContainer"] p,
.stMarkdown small {{
  font-family: var(--font-primary) !important;
  font-size: 13px !important;
  color: var(--c-muted) !important;
}}

/* ── Dataframe / table ───────────────────────────────────────────────────── */
[data-testid="stDataFrame"] > div {{
  border: 1px solid var(--c-border);
  border-radius: 6px;
  overflow: hidden;
}}

/* ── Toggle ──────────────────────────────────────────────────────────────── */
[data-testid="stToggleSwitch"] {{
  accent-color: var(--c-sky);
}}

/* ── Multiselect tags ────────────────────────────────────────────────────── */
[data-baseweb="tag"] {{
  background-color: var(--c-sky) !important;
  color: #FFFFFF !important;
  border-radius: 3px !important;
}}

/* ── Dividers ────────────────────────────────────────────────────────────── */
hr {{
  border-color: var(--c-divider) !important;
  margin: 1rem 0 !important;
}}

/* ── Success / warning / error message text ──────────────────────────────── */
[data-testid="stAlert"] p {{
  font-family: var(--font-primary) !important;
  font-size: 14px !important;
  font-weight: 300 !important;
}}

/* ── Checkbox ────────────────────────────────────────────────────────────── */
.stCheckbox span[data-testid="stWidgetLabel"] p {{
  font-family: var(--font-primary) !important;
  font-weight: 400 !important;
  font-size: 14px !important;
  color: var(--c-navy) !important;
}}

/* ── Form submit border ──────────────────────────────────────────────────── */
[data-testid="stForm"] {{
  border: 1px solid var(--c-border) !important;
  border-radius: 6px !important;
  padding: 1.2rem 1.4rem !important;
  background-color: #FFFFFF;
}}
</style>
"""


def apply_styles() -> None:
    """Inject PrivaSI Lab theme CSS. Call once at the top of main()."""
    st.markdown(_CSS.format(**_TOKENS), unsafe_allow_html=True)
