"""
Streamlit main application
"""

import sys
from pathlib import Path

import streamlit as st
import requests

# Ensure project root is importable when launched from frontend/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRAND_LOGO_PATH = PROJECT_ROOT / "docs" / "beanlogo.png"
BRAND_ICON_PATH = PROJECT_ROOT / "docs" / "beanicon.png"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Initialize i18n
from frontend.i18n import init_i18n, set_language, get_language_options, label
from frontend.config import get_api_url, get_api_timeout
init_i18n()

# Page configuration
st.set_page_config(
    page_title="BeancountPilot",
    page_icon=str(BRAND_ICON_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize default session state
def _load_ai_runtime_state() -> tuple[str, list[dict]]:
    """Load active AI profile id and profile list from backend config."""
    try:
        timeout = min(get_api_timeout(), 3)
        response = requests.get(get_api_url("/ai/config"), timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            profiles = data.get("profiles") if isinstance(data.get("profiles"), list) else []
            default_provider = data.get("default_profile_id") or data.get("default_provider") or ""
            if (not default_provider) and profiles:
                default_provider = str(profiles[0].get("id", "")).strip()
            if isinstance(default_provider, str) and default_provider:
                return default_provider, profiles
    except Exception:
        pass
    return "deepseek", []


default_provider_id, loaded_ai_profiles = _load_ai_runtime_state()
if "provider" not in st.session_state:
    st.session_state.provider = default_provider_id
if "ai_profiles" not in st.session_state:
    st.session_state.ai_profiles = loaded_ai_profiles

if loaded_ai_profiles:
    valid_profile_ids = {
        str(profile.get("id", "")).strip()
        for profile in loaded_ai_profiles
        if str(profile.get("id", "")).strip()
    }
    if str(st.session_state.get("provider", "")).strip() not in valid_profile_ids:
        st.session_state.provider = default_provider_id
if "data_source" not in st.session_state:
    st.session_state.data_source = "alipay"
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
DEFAULT_CHART_OF_ACCOUNTS = """Assets:Bank:Alipay
Assets:Bank:WeChat
Assets:Bank:Cash
Expenses:Food:Dining
Expenses:Food:Groceries
Expenses:Transport:Taxi
Expenses:Transport:Subway
Expenses:Shopping:Clothing
Expenses:Shopping:Electronics
Expenses:Entertainment:Movies
Expenses:Entertainment:Games
Expenses:Utilities:Phone
Expenses:Utilities:Internet
Expenses:Utilities:Electricity
Expenses:Health:Medicine
Expenses:Health:Insurance
Expenses:Education:Books
Expenses:Education:Courses
Expenses:Travel:Hotels
Expenses:Travel:Transport
Expenses:Other
Liabilities:CreditCard:Bank:CMB:C1915
Equity:OpeningBalances
Income:Salary
Income:Investment
Income:Other"""


def _load_chart_of_accounts() -> str:
    """Load chart of accounts from backend; fallback to defaults."""
    try:
        timeout = min(get_api_timeout(), 3)
        response = requests.get(
            get_api_url("/config/chart-of-accounts"),
            timeout=timeout,
        )
        if response.status_code == 200:
            payload = response.json()
            value = payload.get("chart_of_accounts")
            if isinstance(value, str) and value.strip():
                return value
    except Exception:
        pass
    return DEFAULT_CHART_OF_ACCOUNTS


def _load_classification_progress() -> None:
    """Load persisted classification progress from backend."""
    try:
        timeout = min(get_api_timeout(), 3)
        response = requests.get(
            get_api_url("/progress/classification"),
            timeout=timeout,
        )
        if response.status_code == 200:
            payload = response.json()
            st.session_state.persisted_tx_count = int(payload.get("total_transactions", 0))
            st.session_state.persisted_classified_count = int(payload.get("classified_transactions", 0))
    except Exception:
        pass


if "chart_of_accounts" not in st.session_state:
    st.session_state.chart_of_accounts = _load_chart_of_accounts()

if "persisted_progress_loaded" not in st.session_state:
    _load_classification_progress()
    st.session_state.persisted_progress_loaded = True

# Custom CSS
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Lexend:wght@400;500;600;700&display=swap');

    :root {
        --bp-bg: #f8f4eb;
        --bp-bg-deep: #fdf9f0;
        --bp-surface: #fffdfa;
        --bp-surface-soft: #f7f1e5;
        --bp-primary: #c89a3c;
        --bp-primary-strong: #9e7426;
        --bp-accent: #233a75;
        --bp-text: #1f2a3d;
        --bp-muted: #5d6578;
        --bp-border: #e6d8bc;
        --bp-shadow: rgba(82, 62, 24, 0.14);
    }

    .stApp {
        font-family: "IBM Plex Sans", sans-serif;
        background:
            radial-gradient(1000px 420px at 0% -5%, rgba(200, 154, 60, 0.24) 0%, transparent 75%),
            radial-gradient(900px 430px at 100% 0%, rgba(35, 58, 117, 0.1) 0%, transparent 72%),
            linear-gradient(180deg, var(--bp-bg-deep) 0%, var(--bp-bg) 100%);
        color: var(--bp-text);
    }

    h1, h2, h3, h4, h5, h6 {
        font-family: "Lexend", sans-serif !important;
        color: var(--bp-text);
    }

    .block-container {
        padding-top: 0.95rem;
        padding-bottom: 1.25rem;
        max-width: 1260px;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f9f2e2 0%, #f4ead5 55%, #efe2c8 100%);
        border-right: 1px solid #dfcba0;
    }

    [data-testid="stSidebarHeader"] {
        display: none;
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0.6rem;
    }

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.65rem;
    }

    [data-testid="stSidebar"] .stElementContainer {
        margin: 0 !important;
    }

    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stButton,
    [data-testid="stSidebar"] .stSelectbox,
    [data-testid="stSidebar"] [data-testid="stImage"] {
        margin: 0 !important;
    }

    [data-testid="stSidebar"] hr {
        margin-top: 0.35rem;
        margin-bottom: 1.1rem;
    }

    [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        margin-top: 0.6rem;
    }

    .sidebar-lang-spacer {
        display: block;
        height: 0.6rem;
    }

    .sidebar-lang-label {
        color: #4e5f87;
        font-size: 0.88rem;
        font-weight: 600;
        padding-top: 0.35rem;
    }

    .sidebar-brand {
        font-size: 1.35rem;
        font-weight: 700;
        color: #8a6322;
        line-height: 1.2;
        margin-bottom: 0.25rem;
        letter-spacing: 0.01em;
    }

    .sidebar-subtitle {
        color: #4e5f87;
        font-size: 0.92rem;
        margin-bottom: 0.9rem;
    }

    .main-header {
        background: linear-gradient(130deg, #fefbf4 0%, #f8efdc 52%, #f6ead1 100%);
        border: 1px solid #dfc489;
        padding: 1rem 1.08rem;
        border-radius: 1rem;
        margin-bottom: 0.72rem;
        color: #1f2a3d;
        box-shadow: 0 10px 26px var(--bp-shadow);
        position: relative;
        overflow: hidden;
    }

    .main-header::after {
        content: "";
        position: absolute;
        inset: auto -15% -50% auto;
        width: 240px;
        height: 240px;
        background: radial-gradient(circle, rgba(200, 154, 60, 0.28) 0%, rgba(200, 154, 60, 0) 72%);
        pointer-events: none;
    }

    .main-header h1 {
        margin: 0;
        font-size: 1.45rem;
        letter-spacing: 0.01em;
        color: #24355f;
    }

    .main-header p {
        margin: 0.3rem 0 0;
        color: #5b6884;
        font-size: 0.9rem;
    }

    .section-card {
        background: var(--bp-surface);
        border: 1px solid var(--bp-border);
        border-radius: 0.95rem;
        padding: 0.78rem 0.86rem;
        box-shadow: 0 6px 18px rgba(109, 85, 35, 0.1);
        margin-bottom: 0.64rem;
    }

    .feature-card {
        background: linear-gradient(180deg, #fffefb 0%, #f8f2e7 100%);
        border: 1px solid #e7d8b7;
        border-radius: 0.9rem;
        padding: 1rem;
        min-height: 150px;
        box-shadow: 0 4px 14px rgba(128, 100, 42, 0.1);
    }

    .feature-card h3 {
        color: #8a6322;
        margin: 0 0 0.55rem;
        font-size: 1.1rem;
    }

    .feature-card p {
        margin: 0;
        color: var(--bp-muted);
        font-size: 0.98rem;
        line-height: 1.45;
    }

    .workflow-wrap {
        padding: 0.66rem 0.74rem;
    }

    .workflow-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
    }

    .workflow-title {
        margin: 0;
        font-family: "Lexend", sans-serif;
        font-size: 0.96rem;
        color: #2a3f72;
    }

    .workflow-progress-badge {
        border: 1px solid #dbc58d;
        background: #f9f2df;
        color: #7f5f20;
        border-radius: 999px;
        padding: 0.12rem 0.5rem;
        font-size: 0.75rem;
        white-space: nowrap;
        font-weight: 600;
    }

    .workflow-desc {
        margin: 0.18rem 0 0.45rem;
        color: var(--bp-muted);
        font-size: 0.82rem;
    }

    .workflow-grid {
        display: flex !important;
        align-items: stretch;
        gap: 0.28rem;
        flex-wrap: nowrap !important;
    }

    .workflow-step {
        flex: 1 1 0;
        min-width: 0;
        border: 1px solid #e2d3b0;
        background: linear-gradient(180deg, #fffdf9 0%, #f8f1e2 100%);
        border-radius: 0.82rem;
        padding: 0.52rem 0.54rem;
        box-shadow: 0 3px 9px rgba(102, 76, 26, 0.1);
    }

    .workflow-step-no {
        color: #99702b;
        font-family: "Lexend", sans-serif;
        font-weight: 700;
        font-size: 0.72rem;
        letter-spacing: 0.03em;
        margin-bottom: 0.16rem;
    }

    .workflow-step h4 {
        margin: 0 0 0.14rem;
        color: #324a80;
        font-size: 0.86rem;
    }

    .workflow-step p {
        margin: 0;
        color: #5e6679;
        font-size: 0.78rem;
        line-height: 1.3;
    }

    .workflow-arrow {
        display: flex !important;
        align-items: center;
        justify-content: center;
        flex: 0 0 14px;
        min-height: 100%;
        color: #9e7630;
        font-size: 0.84rem;
        font-weight: 700;
    }

    .kpi-card {
        background: var(--bp-surface);
        border: 1px solid #e3d2af;
        border-radius: 0.9rem;
        padding: 0.58rem 0.64rem;
        min-height: 72px;
        box-shadow: 0 5px 14px rgba(122, 95, 41, 0.1);
    }

    .kpi-label {
        color: #5f6a83;
        font-size: 0.78rem;
        margin-bottom: 0.14rem;
    }

    .kpi-value {
        font-family: "Lexend", sans-serif;
        color: #8a6322;
        font-size: 1.18rem;
        font-weight: 700;
        line-height: 1.2;
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 0.72rem;
        border: 1px solid #b88a33;
        background: linear-gradient(180deg, #ddbb70 0%, var(--bp-primary) 100%);
        color: #2d220e;
        box-shadow: 0 6px 14px rgba(130, 95, 30, 0.2);
        font-weight: 600;
        transition: background-color 180ms ease, box-shadow 180ms ease, border-color 180ms ease, transform 180ms ease;
        cursor: pointer;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        border-color: #9f7427;
        background: linear-gradient(180deg, #d6b062 0%, var(--bp-primary-strong) 100%);
        box-shadow: 0 8px 18px rgba(125, 90, 29, 0.24);
        transform: translateY(-1px);
    }

    .stButton > button:focus,
    .stDownloadButton > button:focus {
        outline: 2px solid rgba(35, 58, 117, 0.32);
        outline-offset: 2px;
    }

    .stTextInput > div > div > input,
    .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] > div,
    .stNumberInput input,
    .stMultiSelect div[data-baseweb="select"] > div {
        border: 1px solid var(--bp-border);
        border-radius: 0.7rem;
        background: #fffefd;
        color: #1f2a3d;
    }

    .stTextInput > div > div > input::placeholder,
    .stTextArea textarea::placeholder {
        color: #8b8fa1;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
    }

    .stTabs [data-baseweb="tab"] {
        cursor: pointer;
        border: 1px solid #ddccaa;
        border-radius: 0.62rem 0.62rem 0 0;
        background: #f8f1e3;
        color: #646f89;
        transition: background-color 180ms ease, color 180ms ease;
    }

    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: #fffdf9;
        color: #8a6322;
        border-bottom-color: #fffdf9;
    }

    .stDataFrame,
    .stTable,
    [data-testid="stExpander"],
    [data-testid="stDataEditor"] {
        border: 1px solid #e5d4b1;
        border-radius: 0.85rem;
        overflow: hidden;
        background: #fffefd;
    }

    [data-testid="stMetric"] {
        background: #fffdf9;
        border: 1px solid #e5d4b1;
        border-radius: 0.85rem;
        padding: 0.72rem 0.84rem;
        box-shadow: 0 3px 10px rgba(111, 85, 33, 0.11);
    }

    .stMarkdown,
    p,
    label,
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"],
    [data-baseweb="tab"] {
        color: var(--bp-text);
    }

    hr {
        border-color: #e6d8bc;
    }

    @media (max-width: 768px) {
        .main-header h1 {
            font-size: 1.24rem;
        }

        .kpi-value {
            font-size: 1.2rem;
        }

        .workflow-head {
            align-items: flex-start;
            flex-direction: column;
            gap: 0.2rem;
        }

        .workflow-grid {
            flex-wrap: wrap !important;
            gap: 0.4rem;
        }

        .workflow-step {
            flex: 1 1 calc(50% - 0.24rem);
        }

        .workflow-arrow {
            display: none !important;
        }
    }

    @media (max-width: 480px) {
        .workflow-step {
            flex: 1 1 100%;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        * {
            transition: none !important;
            animation: none !important;
        }
    }
</style>
""",
    unsafe_allow_html=True,
)

# Sidebar — navigation + language only
with st.sidebar:
    st.image(str(BRAND_LOGO_PATH), width=220)
    st.markdown("---")

    # Page navigation (button-based)
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"

    navigation_items = [
        ("home", label("app_home")),
        ("upload", label("upload_files")),
        ("classify", label("transaction_classification")),
        ("settings", label("settings")),
    ]

    for page_key, page_label in navigation_items:
        if st.button(
            page_label,
            width="stretch",
            type="primary" if st.session_state.current_page == page_key else "secondary",
            key=f"nav_{page_key}",
        ):
            if st.session_state.current_page != page_key:
                st.session_state.scroll_to_top_once = True
            st.session_state.current_page = page_key

    st.markdown("---")

    # Language switcher
    st.markdown('<div class="sidebar-lang-spacer"></div>', unsafe_allow_html=True)
    lang_options = get_language_options()
    lang_labels = [lang_label for _, lang_label in lang_options]
    current_lang_index = 0 if st.session_state.language == "en" else 1
    lang_label_col, lang_select_col = st.columns([1.1, 1.6])
    with lang_label_col:
        st.markdown(
            f'<div class="sidebar-lang-label">{label("language")}</div>',
            unsafe_allow_html=True,
        )
    with lang_select_col:
        selected_lang = st.selectbox(
            label("language"),
            lang_labels,
            index=current_lang_index,
            label_visibility="collapsed",
        )
    new_lang = lang_options[lang_labels.index(selected_lang)][0]
    if new_lang != st.session_state.language:
        set_language(new_lang)
        st.rerun()

# Main page routing
page = st.session_state.current_page

if page == "home":
    import frontend.views.home as home_page
    home_page.render()

elif page == "upload":
    import frontend.views.upload as upload_page
    upload_page.render()

elif page == "classify":
    import frontend.views.classify as classify_page
    classify_page.render()

elif page == "settings":
    import frontend.views.settings as settings_page
    settings_page.render()
