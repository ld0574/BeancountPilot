"""
Streamlit main application
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is importable when launched from frontend/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Initialize i18n
from frontend.i18n import init_i18n, set_language, get_language_options, t
init_i18n()

# Page configuration
st.set_page_config(
    page_title="BeancountPilot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background: #f4efe6;
        color: #2f261d;
    }

    [data-testid="stSidebar"] {
        background: #ede3d2;
        border-right: 1px solid #d4c5ae;
    }

    .main-header {
        background: #c6b094;
        border: 1px solid #b39a7a;
        padding: 1rem 1.15rem;
        border-radius: 0.8rem;
        margin-bottom: 1rem;
        color: #2b231b;
        box-shadow: 0 1px 8px rgba(73, 53, 33, 0.07);
    }

    .main-header h1 {
        margin: 0;
        font-size: 1.5rem;
        letter-spacing: 0.01em;
    }

    .sidebar-brand {
        font-size: 1.1rem;
        font-weight: 600;
        color: #4a3a2a;
        margin-bottom: 0.35rem;
    }

    .nav-hint {
        font-size: 0.78rem;
        color: #7c664f;
        margin-bottom: 0.35rem;
        letter-spacing: 0.01em;
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 0.6rem;
        border: 1px solid #b39a7a;
        background: #ccb89d;
        color: #2f261d;
        box-shadow: 0 1px 3px rgba(73, 53, 33, 0.08);
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        background: #c2ac90;
        border-color: #a68968;
    }

    .stTextInput > div > div > input,
    .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] > div,
    .stNumberInput input {
        border: 1px solid #bca78b;
        border-radius: 0.55rem;
        background: #f8f4ed;
    }

    .stDataFrame,
    .stTable {
        border: 1px solid #d2c3af;
        border-radius: 0.6rem;
        overflow: hidden;
    }

    hr {
        border-color: #d1c1ab;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown('<div class="sidebar-brand">📊 BeancountPilot</div>', unsafe_allow_html=True)
    st.markdown("---")

    # Language switcher
    lang_options = get_language_options()
    current_lang_index = 0 if st.session_state.language == "en" else 1
    selected_lang = st.selectbox(
        t("language"),
        [label for _, label in lang_options],
        index=current_lang_index,
    )
    # Update language
    new_lang = lang_options[[label for _, label in lang_options].index(selected_lang)][0]
    if new_lang != st.session_state.language:
        set_language(new_lang)
        st.rerun()

    st.markdown("---")

    # Page navigation
    st.markdown(f'<div class="nav-hint">{t("navigation")}</div>', unsafe_allow_html=True)
    page = st.radio(
        t("navigation"),
        [t("upload_files"), t("transaction_classification"), t("settings")],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # AI configuration
    st.subheader(t("ai_config"))

    # Provider selection
    provider = st.selectbox(
        t("ai_provider"),
        ["deepseek", "openai", "ollama", "custom"],
        index=0,
        help="Select 'custom' for OpenAI-compatible API"
    )

    # API key input
    api_key = st.text_input(
        t("api_key"),
        type="password",
        placeholder=t("api_key_placeholder"),
    )

    st.markdown("---")

    # Chart of accounts configuration
    st.subheader(t("chart_of_accounts"))

    chart_of_accounts = st.text_area(
        t("account_table"),
        value="""Assets:Bank:Alipay
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
Expenses:Misc
Income:Salary
Income:Investment
Income:Other""",
        height=300,
    )

    # Save configuration to session state
    st.session_state.provider = provider
    st.session_state.api_key = api_key
    st.session_state.chart_of_accounts = chart_of_accounts

# Main page
if page == t("upload_files"):
    import frontend.pages.upload as upload_page
    upload_page.render()

elif page == t("transaction_classification"):
    import frontend.pages.classify as classify_page
    classify_page.render()

elif page == t("settings"):
    import frontend.pages.settings as settings_page
    settings_page.render()
