"""
Streamlit main application
"""

import streamlit as st
import pandas as pd
from pathlib import Path

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
        background-color: #f5f5f5;
    }
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("📊 BeancountPilot")
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
