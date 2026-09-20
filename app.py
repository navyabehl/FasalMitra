"""
FasalMitra — AI Mandi Price & Cold Storage Advisory
Built for: 1M1B AI for Sustainability Virtual Internship (IBM SkillsBuild & AICTE)
SDG Alignment: SDG 2 (Zero Hunger) — primary | SDG 12, SDG 1 — secondary

Run with:  streamlit run app.py
"""

import base64
from pathlib import Path

import streamlit as st
import pandas as pd

from utils.translations import t
from utils.data import STATES, CROPS, get_price_series, get_storage_facilities, get_state_cold_storage_gap
from utils.logic import analyze
from utils.rag import generate_explanation

# Guard the config import so a missing env var never crashes the whole
# app before Streamlit even renders a page.
try:
    from utils.config import GROQ_API_KEY
except Exception:
    GROQ_API_KEY = ""

# ----------------------------------------------------------------------
# Page config — no sidebar: navigation is a top tab bar (see below)
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="FasalMitra",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def html_block(s: str) -> str:
    """Strip per-line leading whitespace from a multi-line HTML string
    before passing it to st.markdown(..., unsafe_allow_html=True).

    Without this, Python's source indentation (each nested tag written
    a few spaces deeper than its parent) survives into the string, and
    Markdown's CommonMark parser treats any line indented 4+ spaces as
    a literal code block, rendering the HTML as visible tag text
    instead of parsing it as markup.

    For *static* strings (no f-string interpolation) call this once at
    module load and assign to a constant rather than calling per-render.
    Dynamic f-strings (containing result data) still call it inline.
    """
    return "\n".join(line.strip() for line in s.strip("\n").split("\n"))


# ----------------------------------------------------------------------
# Crop background images (real photos, provided for this build) —
# read once per file and base64-cached, so the per-page <style>
# background can just embed a data: URI with no extra Streamlit static-
# file configuration needed.
# ----------------------------------------------------------------------
ASSETS_DIR = Path(__file__).parent / "assets"
CROP_IMAGE_FILES = {
    "Onion": "onion.jpg", "Tomato": "tomato.jpg", "Wheat": "wheat.jpg",
    "Potato": "potato.jpg", "Garlic": "garlic.jpg", "Mustard": "mustard.jpg",
}


@st.cache_data
def _b64_image(filename: str):
    path = ASSETS_DIR / filename
    if not filename or not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


# ----------------------------------------------------------------------
# Session state defaults
# ----------------------------------------------------------------------
DEFAULT_STATE = list(STATES.keys())[0]
DEFAULT_CROP = list(CROPS.keys())[0]

_DEFAULTS = {
    "lang": "English",
    "page": "home",
    "result": None,
    "groq_api_key": GROQ_API_KEY,
    "sb_state": DEFAULT_STATE,
    "sb_district": STATES[DEFAULT_STATE][0],
    "sb_crop": DEFAULT_CROP,
    "sl_qty": 20,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# If the state selection changed since last run, the stored district
# may no longer be valid for it — fix that up before the district
# selectbox renders further down, rather than letting Streamlit error.
if st.session_state.sb_district not in STATES.get(st.session_state.sb_state, []):
    st.session_state.sb_district = STATES[st.session_state.sb_state][0]

LANGS = [
    "English", "हिंदी", "ਪੰਜਾਬੀ", "বাংলা", "मराठी", "ગુજરાતী",
    "தமிழ்", "తెలుగు", "ಕನ್ನಡ", "മലയാളം", "ଓଡ଼ିଆ", "অসমীয়া", "اردو",
]
PAGES = ["home", "check", "storage", "about"]
NEXT_PAGE = {"home": "check", "check": "storage", "storage": "about", "about": "home"}


def go_to(page_name: str):
    """Navigate. No widget is bound to "page" (there's no sidebar radio
    anymore — the nav is plain buttons), so this can just set it
    directly and rerun, no pending-navigation workaround needed."""
    st.session_state.page = page_name
    st.rerun()


def reset_app():
    """So the next person can use the app without manually clearing
    out the previous person's selections and results."""
    st.session_state.result = None
    for k in ("sb_state", "sb_district", "sb_crop", "sl_qty"):
        st.session_state[k] = _DEFAULTS[k]
    st.session_state.page = "home"
    st.rerun()


def render_result_summary(r: dict, lang: str, show_disclaimer: bool = True):
    """Renders the price metrics, chart, recommendation card, RAG
    explanation, cost-benefit breakdown and loss-gap context. Shared
    between the check page (sell case, shown inline) and the storage
    page recap (wait case, shown after auto-redirect) so both pages
    stay in sync from one implementation."""
    a = r["analysis"]
    rtl = lang == "اردو"
    align_style = "direction:rtl;text-align:right;" if rtl else ""

    st.write("")
    window_days = a.get("window_days", 90)
    m1, m2 = st.columns(2)
    with m1:
        st.markdown(html_block(f"""<div class="fm-metric-box">
            <div class="fm-muted" style="font-size:0.85rem;">{t('today_price', lang)}</div>
            <div style="font-size:1.6rem;font-weight:700;color:#4CAF50;">₹{a['today_price']}</div>
            </div>"""), unsafe_allow_html=True)
    with m2:
        # Label reflects the actual window so it never contradicts the chart
        avg_label = t('avg_price', lang).replace("90", str(window_days))
        st.markdown(html_block(f"""<div class="fm-metric-box">
            <div class="fm-muted" style="font-size:0.85rem;">{avg_label}</div>
            <div style="font-size:1.6rem;font-weight:700;">₹{a['avg_price']}</div>
            </div>"""), unsafe_allow_html=True)

    st.write("")
    st.markdown(f"**{t('price_trend', lang)}** _(last {window_days} days)_")
    df = pd.DataFrame(r["prices"]).set_index("date")
    st.line_chart(df, height=220, color="#4CAF50")
    st.caption("📡 Source: Government of India Open Data API (data.gov.in / AGMARKNET), "
               "resource 9ef84268-d588-465a-a308-a864a43d0070 — live where reachable, "
               "otherwise a verified recent snapshot or a clearly-labelled simulated series.")

    icon = "⏳" if a["should_wait"] else "✅"
    rec_class = "fm-rec-card-wait" if a["should_wait"] else "fm-rec-card-sell"
    rec_text = t("rec_wait", lang) if a["should_wait"] else t("rec_sell", lang)
    # For WAIT, append the number of days directly to the card so the farmer
    # sees the actionable number at a glance without scrolling further down.
    if a["should_wait"] and a.get("suggested_days"):
        rec_text = f"{rec_text} — {a['suggested_days']} days"
    st.markdown(f'<div class="{rec_class}"><span class="fm-rec-icon">{icon}</span>{rec_text}</div>',
                unsafe_allow_html=True)

    with st.expander("📊 Market signal (percentile / volatility / trend)"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Price percentile", f"{a['percentile_rank']}", help="0 = lowest seen in the window, 100 = highest")
        c2.metric("Volatility z-score", f"{a['z_score']}", help="Standard deviations below (-) or above (+) the mean")
        c3.metric("Recent trend", f"{'📈 rising' if a['trend_slope'] > 0 else '📉 falling/flat'}",
                   help=f"{a['trend_slope']} ₹/quintal per day, over the last ~21 days")

    st.markdown(f"**{t('why_title', lang)}**")
    st.markdown(f'<div style="{align_style}">{r["rag"]["explanation"]}</div>', unsafe_allow_html=True)
    st.markdown(html_block(f"""<div class="fm-source-box">📚 <b>Source:</b> {r['rag']['source_snippet']}</div>"""),
                unsafe_allow_html=True)

    llm_status = r["rag"].get("llm_status")
    if llm_status is not None:
        provider_name = {"groq": "Groq", "anthropic": "Claude"}.get(llm_status.get("provider"), "the AI provider")
        if llm_status["used_llm"]:
            st.caption(f"🤖 This explanation was generated live by {provider_name}.")
        else:
            st.caption(f"⚠️ Couldn't get a live {provider_name} response, so the built-in template "
                       f"was used instead. Reason: {llm_status['error']}")

    if a["should_wait"]:
        st.write("")
        st.markdown(f"**{t('cost_benefit', lang)}**")
        b1, b2, b3 = st.columns(3)
        b1.metric(t("storage_cost", lang), f"₹{a['storage_cost']}")
        b2.metric(t("potential_gain", lang), f"₹{a['potential_gain']}")
        b3.metric(t("net_benefit", lang), f"₹{a['net_benefit']}", delta=f"{a['net_benefit']}")

    if r["gap_mt"]:
        st.markdown(html_block(f"""<div class="fm-metric-box" style="margin-top:1rem;">
            <div class="fm-muted" style="font-size:0.85rem;">{t('district_loss', lang)}</div>
            <div style="font-size:1.3rem;font-weight:700;color:#FF9800;">{r['gap_mt']:,} MT</div>
            <div class="fm-muted" style="font-size:0.75rem;">govt-assessed cold storage capacity gap, {r['state']} state
            (NABCONS 2015 study, via Lok Sabha PQ 266) — state-level, not district-specific</div>
            </div>"""), unsafe_allow_html=True)

    if show_disclaimer:
        st.markdown(f'<div class="fm-disclaimer">{t("disclaimer", lang)}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Custom CSS — theme-aware (light + dark), card styling, animations,
# top nav bar. Per-page background gradients/photos are injected
# separately below (after we know which page we're on).
# Pre-processed once at module load so html_block() is not called on
# every Streamlit rerun for this static string.
# ----------------------------------------------------------------------
_GLOBAL_CSS = html_block("""
<style>
    .fm-header {
        display: flex; justify-content: space-between; align-items: center;
        padding: 0.5rem 0 1rem 0; margin-bottom: 0.5rem;
    }
    .fm-logo { font-size: 1.8rem; font-weight: 800; color: #4CAF50; }
    /* Use a neutral mid-grey that works on both dark and light Streamlit
       themes — opacity: 0.65 on var(--text-color) becomes invisible in
       light mode where --text-color is near-black on a white background. */
    .fm-tagline { color: #888; font-size: 0.9rem; }

    /* Top nav tabs: plain buttons, styled to look like an Instagram-
       style segmented switcher — active tab is a filled pill,
       inactive tabs are flat text. */
    div[data-testid="stHorizontalBlock"] .stButton > button {
        border-radius: 999px !important;
    }

    .fm-hero {
        border-radius: 18px; padding: 2.2rem; color: white; margin-bottom: 1.5rem;
        position: relative; overflow: hidden;
        animation: fadeInUp 0.6s ease-out;
        background: linear-gradient(135deg, rgba(11,46,19,0.0), rgba(11,46,19,0.0));
    }
    .fm-hero h1 { font-size: 2.1rem; margin-bottom: 0.5rem; text-shadow: 0 2px 10px rgba(0,0,0,0.35); }
    .fm-hero p { font-size: 1.05rem; opacity: 0.95; max-width: 80%; text-shadow: 0 1px 6px rgba(0,0,0,0.3); }
    .fm-hero-illustration { position: absolute; right: 1rem; top: 50%;
        transform: translateY(-50%); width: 110px; height: 110px; opacity: 0.9; }
    @keyframes fadeInUp {
        0% { opacity: 0; transform: translateY(16px); }
        100% { opacity: 1; transform: translateY(0); }
    }

    .fm-step-icon { font-size: 2.6rem; margin-bottom: 0.3rem; animation: float 3s ease-in-out infinite; }
    @keyframes float {
        0% { transform: translateY(0px) rotate(0deg); }
        50% { transform: translateY(-8px) rotate(-3deg); }
        100% { transform: translateY(0px) rotate(0deg); }
    }
    @keyframes sway {
        0%, 100% { transform: rotate(-4deg); }
        50% { transform: rotate(4deg); }
    }
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.08); }
    }

    div[data-testid="column"] .stButton > button {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 14px; padding: 2.2rem 1rem; width: 100%; min-height: 140px;
        white-space: pre-line; line-height: 2; font-weight: 700; font-size: 1.15rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    div[data-testid="column"] .stButton > button:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        border-color: #4CAF50;
    }
    .stButton > button {
        font-size: 1.05rem;
        padding-top: 0.7rem;
        padding-bottom: 0.7rem;
    }
    .stButton > button[kind="primary"] {
        font-size: 1.2rem;
        padding-top: 0.9rem;
        padding-bottom: 0.9rem;
        font-weight: 700;
    }
    .stSelectbox label, .stSlider label, .stRadio label {
        font-size: 1.05rem !important;
        font-weight: 600;
    }

    .fm-rec-card-sell {
        background: linear-gradient(135deg, #43A047, #2E7D32); color: white;
        border-radius: 16px; padding: 1.8rem; text-align: center; font-size: 1.6rem;
        font-weight: 700; margin: 1rem 0; box-shadow: 0 4px 14px rgba(46,125,50,0.35);
        animation: pop 0.5s ease-out;
    }
    .fm-rec-card-wait {
        background: linear-gradient(135deg, #FFA726, #FB8C00); color: white;
        border-radius: 16px; padding: 1.8rem; text-align: center; font-size: 1.6rem;
        font-weight: 700; margin: 1rem 0; box-shadow: 0 4px 14px rgba(251,140,0,0.35);
        animation: pop 0.5s ease-out;
    }
    .fm-rec-icon { display: inline-block; font-size: 1.8rem; margin-right: 0.4rem; }
    .fm-rec-card-sell .fm-rec-icon { animation: pulse 1.4s ease-in-out infinite; }
    .fm-rec-card-wait .fm-rec-icon { animation: sway 1.6s ease-in-out infinite; transform-origin: top center; display:inline-block; }
    @keyframes pop {
        0% { transform: scale(0.92); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
    }

    .fm-metric-box {
        background: var(--secondary-background-color); border-radius: 12px; padding: 1rem;
        border: 1px solid rgba(128,128,128,0.2); text-align: center;
    }
    .fm-source-box {
        background: rgba(104,159,56,0.12); border-left: 4px solid #689F38; border-radius: 6px;
        padding: 0.8rem 1rem; font-size: 0.85rem; color: var(--text-color); margin-top: 0.8rem;
    }
    .fm-storage-card {
        background: var(--secondary-background-color); border-radius: 12px; padding: 1.1rem;
        margin-bottom: 0.8rem; border: 1px solid rgba(128,128,128,0.2);
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        animation: fadeInUp 0.4s ease-out;
        transition: transform 0.15s;
    }
    .fm-storage-card:hover { transform: translateX(4px); }
    .fm-disclaimer {
        background: rgba(255,179,0,0.12); border-left: 4px solid #FFB300; border-radius: 6px;
        padding: 0.9rem 1.1rem; font-size: 0.85rem; color: var(--text-color); margin-top: 1.5rem;
    }
    .fm-muted { color: var(--text-color); opacity: 0.65; }

    /* Frosted-glass card variant used on the Check page, where cards
       sit on top of a real photo background rather than the plain
       app background — plain var(--secondary-background-color) cards
       would be illegible against a busy photo, so these use a
       blurred, semi-opaque panel instead. */
    .fm-glass-panel {
        background: rgba(10, 20, 10, 0.55);
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
        border-radius: 16px; padding: 1.2rem; border: 1px solid rgba(255,255,255,0.15);
    }
</style>
""")
st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

HERO_SVG = """
<svg class="fm-hero-illustration" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <circle cx="60" cy="30" r="16" fill="#FFF176" opacity="0.9">
    <animate attributeName="opacity" values="0.7;1;0.7" dur="2.5s" repeatCount="indefinite"/>
  </circle>
  <path d="M60 60 C 55 75, 55 90, 60 105" stroke="#A5D6A7" stroke-width="4" fill="none" stroke-linecap="round"/>
  <path d="M60 75 C 45 70, 35 78, 32 88" stroke="#81C784" stroke-width="5" fill="none" stroke-linecap="round">
    <animateTransform attributeName="transform" type="rotate" values="-3 60 75;3 60 75;-3 60 75" dur="3s" repeatCount="indefinite"/>
  </path>
  <path d="M60 88 C 75 83, 85 90, 88 100" stroke="#66BB6A" stroke-width="5" fill="none" stroke-linecap="round">
    <animateTransform attributeName="transform" type="rotate" values="3 60 88;-3 60 88;3 60 88" dur="3.2s" repeatCount="indefinite"/>
  </path>
</svg>
"""

# ----------------------------------------------------------------------
# Header: logo/tagline, language switcher, reset button
# ----------------------------------------------------------------------
col_logo, col_lang, col_reset = st.columns([5, 2, 1.2])
with col_logo:
    st.markdown(
        html_block(f"""<div class="fm-logo">🌾 {t('app_name', st.session_state.lang)}</div>
        <div class="fm-tagline">{t('tagline', st.session_state.lang)}</div>"""),
        unsafe_allow_html=True,
    )
with col_lang:
    st.session_state.lang = st.selectbox(
        "🌐", LANGS, index=LANGS.index(st.session_state.lang), label_visibility="collapsed"
    )
with col_reset:
    if st.button("🔄 Reset", use_container_width=True,
                 help="Clear everything so the next person can start fresh"):
        reset_app()

lang = st.session_state.lang

# ----------------------------------------------------------------------
# Top nav tabs — replaces the sidebar. Plain buttons; the active page
# renders as a filled "primary" pill, inactive ones as flat buttons.
# ----------------------------------------------------------------------
nav_labels = {
    "home": t("nav_home", lang), "check": t("nav_check", lang),
    "storage": t("nav_storage", lang), "about": t("nav_about", lang),
}
nav_cols = st.columns(4)
for i, p in enumerate(PAGES):
    with nav_cols[i]:
        is_active = st.session_state.page == p
        if st.button(nav_labels[p], key=f"navtab_{p}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            if not is_active:
                go_to(p)

st.markdown("<hr style='margin-top:0.3rem;opacity:0.2;'>", unsafe_allow_html=True)

current_page = st.session_state.page

# ----------------------------------------------------------------------
# Per-page background
# ----------------------------------------------------------------------
if current_page == "home":
    st.markdown(html_block("""
    <style>
    .stApp {
        background: linear-gradient(160deg, #04150a 0%, #0b3d1e 30%, #1b5e20 55%, #388e3c 78%, #66bb6a 100%);
        background-attachment: fixed;
    }
    </style>
    """), unsafe_allow_html=True)
elif current_page == "check":
    _crop_for_bg = st.session_state.get("sb_crop", DEFAULT_CROP)
    _img_b64 = _b64_image(CROP_IMAGE_FILES.get(_crop_for_bg, ""))
    if _img_b64:
        st.markdown(html_block(f"""
        <style>
        .stApp {{
            background-image: linear-gradient(rgba(8,18,8,0.72), rgba(8,18,8,0.72)),
                               url('data:image/jpeg;base64,{_img_b64}');
            background-size: cover;
            background-position: center 35%;
            background-attachment: fixed;
        }}
        </style>
        """), unsafe_allow_html=True)

# ========================================================================
# PAGE: HOME
# ========================================================================
if current_page == "home":
    st.markdown(html_block(f"""
    <div class="fm-hero">
        {HERO_SVG}
        <h1>🌱 {t('home_hero_title', lang)}</h1>
        <p>{t('home_hero_sub', lang)}</p>
    </div>
    """), unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button(f"💰\n\n1. {t('step1', lang)}", use_container_width=True, key="step1_btn"):
            go_to("check")
    with c2:
        if st.button(f"🤖\n\n2. {t('step2', lang)}", use_container_width=True, key="step2_btn"):
            go_to("check")
    with c3:
        if st.button(f"🏬\n\n3. {t('step3', lang)}", use_container_width=True, key="step3_btn"):
            go_to("storage")

    st.write("")
    st.write("")
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        if st.button(t("start_btn", lang), use_container_width=True, type="primary", key="start_btn"):
            go_to("check")

# ========================================================================
# PAGE: CHECK MY CROP
# ========================================================================
elif current_page == "check":
    st.markdown('<div class="fm-glass-panel">', unsafe_allow_html=True)
    st.subheader(t("nav_check", lang))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.session_state.sb_state = st.selectbox(
            t("select_state", lang), list(STATES.keys()),
            index=list(STATES.keys()).index(st.session_state.sb_state), key="sel_state",
        )
    with c2:
        district_options = STATES[st.session_state.sb_state]
        if st.session_state.sb_district not in district_options:
            st.session_state.sb_district = district_options[0]
        st.session_state.sb_district = st.selectbox(
            t("select_district", lang), district_options,
            index=district_options.index(st.session_state.sb_district), key="sel_district",
        )
    with c3:
        crop_options = list(CROPS.keys())
        st.session_state.sb_crop = st.selectbox(
            t("select_crop", lang), crop_options,
            index=crop_options.index(st.session_state.sb_crop), key="sel_crop",
            format_func=lambda c: f"{CROPS[c]['icon']} {c}",
        )

    state = st.session_state.sb_state
    district = st.session_state.sb_district
    crop = st.session_state.sb_crop

    st.session_state.sl_qty = st.slider(
        t("enter_qty", lang), min_value=1, max_value=200, value=st.session_state.sl_qty, key="sl_qty_widget",
    )
    quantity = st.session_state.sl_qty

    if st.button(t("get_advice_btn", lang), type="primary"):
        # Only re-run the full fetch + analysis if the inputs actually
        # changed since the last run — avoids redundant API calls and
        # LLM requests when the user clicks the button twice in a row.
        prev = st.session_state.result
        inputs_changed = (
            prev is None
            or prev.get("crop") != crop
            or prev.get("district") != district
            or prev.get("quantity") != quantity
        )
        if inputs_changed:
            with st.spinner("🌱 Fetching latest mandi prices and analyzing..."):
                prices = get_price_series(crop, district)
                facilities, facilities_source_district = get_storage_facilities(district)
                analysis = analyze(crop, prices, quantity, facilities)
                rag_result = generate_explanation(
                    crop, analysis, lang,
                    provider="groq",
                    api_key=st.session_state.groq_api_key,
                )
                gap_mt = get_state_cold_storage_gap(district)

                st.session_state.result = {
                    "crop": crop, "district": district, "state": state,
                    "quantity": quantity, "prices": prices, "facilities": facilities,
                    "facilities_source_district": facilities_source_district,
                    "analysis": analysis, "rag": rag_result, "gap_mt": gap_mt,
                }

    if st.session_state.result:
        st.markdown("<hr style='margin:1.5rem 0 0.5rem 0;opacity:0.2;'>", unsafe_allow_html=True)
        render_result_summary(st.session_state.result, lang)

    st.write("")
    if st.button(f"Next: {t('nav_storage', lang)} ➜", key="next_from_check"):
        go_to(NEXT_PAGE["check"])
    st.markdown('</div>', unsafe_allow_html=True)

# ========================================================================
# PAGE: FIND STORAGE
# ========================================================================
elif current_page == "storage":
    st.subheader(t("storage_page_title", lang))

    if st.session_state.result:
        r = st.session_state.result
        facilities = r["facilities"]
        fallback_district = r.get("facilities_source_district")
        if not facilities:
            st.info("No verified NHB (National Horticulture Board) facility record has been "
                     "located for this district — or anywhere else in its state — in this build "
                     "yet. Rather than invent one, we're leaving this honest. See the About page "
                     "for which districts have verified records.")
        elif fallback_district:
            st.warning(f"No verified record for {r['district']} itself yet — showing another "
                       f"verified district in the same state: **{fallback_district}**. "
                       f"No distance calculation is done; confirm locally before relying on these.")
        for f in facilities:
            st.markdown(html_block(f"""
            <div class="fm-storage-card">
                <b>🏬 {f['name']}</b><br>
                <span style="color:#777;">{f['address']}</span><br>
                <span style="font-size:0.85rem;">{t('capacity', lang)}: {f['capacity_mt']:,} MT &nbsp;|&nbsp;
                {t('est_rate', lang)}: ₹{f['rate_per_qtl_day']}/quintal/day (estimated — NHB does not publish rates)</span><br>
                <span style="font-size:0.75rem;color:#999;">Source: {f['source']}</span>
            </div>
            """), unsafe_allow_html=True)
    else:
        # Avoid a hardcoded English fragment mixed with a translated string,
        # and use a direction-neutral pointer (→) instead of 👈 which points
        # the wrong way for RTL languages like Urdu.
        st.info("→ " + t("nav_check", lang) + " — " + (
            "check your crop first to see storage options for your district."
            if lang == "English" else
            "पहले फसल जांचें, फिर स्टोरेज विकल्प दिखेंगे।"
            if lang == "हिंदी" else
            "ਪਹਿਲਾਂ ਫਸਲ ਜਾਂਚੋ, ਫਿਰ ਸਟੋਰੇਜ ਵਿਕਲਪ ਦਿਖਾਏ ਜਾਣਗੇ।"
            if lang == "ਪੰਜਾਬੀ" else
            "আগে ফসল যাচাই করুন, তারপর স্টোরেজ বিকল্প দেখা যাবে।"
            if lang == "বাংলা" else
            "प्रथम पीक तपासा, नंतर साठवण पर्याय दिसतील."
            if lang == "मराठी" else
            "پہلے اپنی فصل چیک کریں، پھر اسٹوریج کے اختیارات دکھائے جائیں گے۔"
            if lang == "اردو" else
            "first check your crop to see storage options."
        ))

    st.write("")
    if st.button(f"Next: {t('nav_about', lang)} ➜", key="next_from_storage"):
        go_to(NEXT_PAGE["storage"])

# ========================================================================
# PAGE: ABOUT
# ========================================================================
elif current_page == "about":
    st.subheader(t("about_title", lang))

    st.markdown("""
**Project:** FasalMitra — AI Mandi Price & Cold Storage Advisory
**SDG Alignment:** SDG 2 (Zero Hunger) — primary · SDG 12 (Responsible Consumption & Production), SDG 1 (No Poverty) — secondary

FasalMitra helps smallholder farmers decide whether to sell their produce
now or hold it in cold storage for a few days, by combining mandi price
trends with a transparent cost-benefit calculation and a district-level
post-harvest loss signal.
    """)

    st.markdown(f"#### {t('data_sources', lang)}")
    st.markdown("""
- **Mandi prices:** Live call to the official Government of India Open Data API
  (data.gov.in / AGMARKNET, resource `9ef84268-d588-465a-a308-a864a43d0070`),
  Ministry of Agriculture & Farmers Welfare, over a 90-day window. If the live
  call isn't reachable (e.g. no internet in a given environment, API rate
  limit), the app falls back first to a verified real snapshot bundled for
  that crop/district, and only as a last resort to a clearly-labelled
  simulated series — never presented as live when it isn't.
- **Cold storage facilities:** Real, named facility records — company name,
  address, and government-sanctioned capacity — pulled directly from the
  National Horticulture Board's official state-wise CISS (Capital Investment
  Subsidy Scheme) PDFs at `nhb.gov.in/doc/<state>.pdf`. Verified for 16
  districts across UP, Maharashtra, Haryana, Karnataka, Odisha, and Madhya
  Pradesh; other districts fall back to the nearest verified district in the
  same state, or show an honest empty state if none exists yet — see the
  "Find Storage" page.
- **Storage rates:** NHB's public records don't include rental rates, so
  these are indicative estimates only, clearly marked as such in the app.
- **Cold storage capacity gap:** Government-assessed figures (NABCONS 2015
  study), published at state level via a December 2024 Lok Sabha reply
  (PQ 266) — shown as a state-level figure, not a district-specific one,
  since no district-level breakdown is publicly available.
    """)

    st.markdown("#### Sell-or-wait model")
    st.markdown("""
The recommendation isn't a fixed percentage-off-average rule — it requires
three independent signals to agree, computed over a 90-day price window:
1. **Percentile rank** — today's price must be in the bottom quartile of
   the last 90 days (not just below a flat average).
2. **Volatility-normalized deviation (z-score)** — at least half a standard
   deviation below the mean, using each crop's *own* historical volatility
   (so the bar means the same thing for low-swing wheat as for high-swing
   tomato, instead of one fixed percentage for both).
3. **Regression trend** — a proper least-squares slope over the most recent
   ~21 days must be positive (genuinely recovering), not just a noisy
   two-point comparison.

Only when all three agree, and the projected gain exceeds the estimated
storage cost, does the app recommend waiting.
    """)

    st.markdown(f"#### {t('responsible_ai', lang)}")
    st.markdown("""
- **Fairness:** Recommendations are based on price/storage data only, not farmer identity or any protected attribute.
- **Transparency:** Every recommendation shows its source snippet and the underlying percentile/volatility/trend numbers (see "Why this advice?" and "Market signal"), so the reasoning is auditable, not a black box.
- **Ethics:** The tool frames outputs as *advisory*, not instructions — final selling decisions remain with the farmer.
- **Privacy:** No personal or farmer-identifying data is collected or stored by this prototype. API keys, if you provide one, are used only for that session's request and never logged or saved by the app.
- **Known limitations:** Storage rental rates are indicative estimates, not live quotes, since NHB doesn't publish them; several districts have no verified cold storage record yet; the tool doesn't account for a farmer's individual liquidity constraints.
    """)

    st.markdown(f'<div class="fm-disclaimer">{t("disclaimer", lang)}</div>', unsafe_allow_html=True)

    st.write("")
    if st.button(f"Next: {t('nav_home', lang)} ➜", key="next_from_about"):
        go_to(NEXT_PAGE["about"])
