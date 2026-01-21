"""
Settings page
"""

import streamlit as st
import pandas as pd
from frontend.i18n import t
from frontend.config import get_api_url, get_health_check_url, get_api_timeout


def render():
    """Render settings page"""
    st.markdown(f'<div class="main-header"><h1>{t("settings_title")}</h1></div>', unsafe_allow_html=True)

    st.markdown(t("settings_description"))

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([t("ai_settings"), t("chart_of_accounts_config"), t("rule_management"), t("system_info")])

    # AI Settings
    with tab1:
        st.subheader(t("ai_provider_config"))

        # Provider selection
        provider = st.selectbox(
            t("select_ai_provider"),
            ["deepseek", "openai", "ollama"],
            index=0,
        )

        st.markdown("---")

        # Provider configuration
        if provider == "deepseek":
            st.markdown(t("deepseek_config"))

            api_base = st.text_input(
                t("api_base"),
                value="https://api.deepseek.com/v1",
            )

            api_key = st.text_input(
                t("api_key"),
                type="password",
                placeholder="Enter DeepSeek API Key",
            )

            model = st.selectbox(
                t("model"),
                ["deepseek-chat", "deepseek-coder"],
                index=0,
            )

        elif provider == "openai":
            st.markdown(t("openai_config"))

            api_base = st.text_input(
                t("api_base"),
                value="https://api.openai.com/v1",
            )

            api_key = st.text_input(
                t("api_key"),
                type="password",
                placeholder="Enter OpenAI API Key",
            )

            model = st.selectbox(
                t("model"),
                ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
                index=0,
            )

        elif provider == "ollama":
            st.markdown(t("ollama_config"))

            api_base = st.text_input(
                t("api_base"),
                value="http://localhost:11434/v1",
            )

            api_key = st.text_input(
                t("api_key"),
                value="ollama",
                disabled=True,
            )

            model = st.text_input(
                t("model"),
                value="llama3.2:3b",
                placeholder="Enter Ollama model name",
            )

        elif provider == "custom":
            st.markdown(t("custom_provider_config"))
            st.info(t("custom_provider_help"))

            api_base = st.text_input(
                t("api_base"),
                placeholder="e.g., https://api.example.com/v1",
                help=t("api_base_help"),
            )

            api_key = st.text_input(
                t("api_key"),
                type="password",
                placeholder=t("api_key_custom"),
            )

            model = st.text_input(
                t("model"),
                placeholder=t("model_custom"),
                help=t("model_help"),
            )

        # Common parameters
        st.markdown("---")
        st.subheader(t("common_parameters"))

        temperature = st.slider(
            t("temperature"),
            min_value=0.0,
            max_value=1.0,
            value=0.3,
            step=0.1,
            help=t("temperature_help"),
        )

        timeout = st.number_input(
            t("timeout"),
            min_value=10,
            max_value=120,
            value=30,
        )

        # Save button
        if st.button(t("save_config"), type="primary", use_container_width=True):
            st.success(t("config_saved"))

    # Chart of Accounts
    with tab2:
        st.subheader(t("chart_of_accounts_config_title"))

        chart_of_accounts = st.text_area(
            t("chart_of_accounts"),
            value=st.session_state.get("chart_of_accounts", ""),
            height=400,
            help=t("chart_of_accounts_help"),
        )

        # Validate chart of accounts
        if st.button(t("validate_chart"), use_container_width=True):
            accounts = []
            for line in chart_of_accounts.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    accounts.append(line)

            st.success(t("total_accounts", count=len(accounts)))

            # Display account list
            st.dataframe(
                pd.DataFrame({"Account": accounts}),
                use_container_width=True,
            )

    # Rule Management
    with tab3:
        st.subheader(t("rule_management_title"))

        # Rule list
        try:
            import requests

            response = requests.get(get_api_url("/rules"), timeout=get_api_timeout())

            if response.status_code == 200:
                rules = response.json()

                if rules:
                    # Display rule list
                    for rule in rules:
                        with st.expander(f"📌 {rule['name']}"):
                            st.write(f"**Account**: {rule['account']}")
                            st.write(f"**Confidence**: {rule['confidence']}")
                            st.write(f"**Conditions**: {rule['conditions']}")
                            st.write(f"**Source**: {rule['source']}")
                else:
                    st.info(t("no_rules"))
            else:
                st.warning(t("failed_load_rules"))

        except requests.exceptions.ConnectionError:
            st.error(t("backend_not_connected"))

        # Create new rule
        st.markdown("---")
        st.subheader(t("create_new_rule"))

        with st.form("create_rule"):
            rule_name = st.text_input(t("rule_name"))

            st.markdown(f"**{t('conditions')}**")

            col1, col2 = st.columns(2)

            with col1:
                peer = st.text_input(t("peer"))
                category = st.text_input(t("category"))

            with col2:
                item = st.text_input(t("item_rule"))

            account = st.text_input(t("target_account"))

            confidence = st.slider(
                t("confidence"),
                min_value=0.0,
                max_value=1.0,
                value=1.0,
                step=0.1,
            )

            if st.form_submit_button(t("create_rule"), type="primary", use_container_width=True):
                st.success(t("rule_created"))

        # Export rules
        st.markdown("---")
        st.subheader(t("export_rules"))

        if st.button(t("export_format"), use_container_width=True):
            st.info(t("rules_exported"))

    # System Information
    with tab4:
        st.subheader(t("system_info_title"))

        # Backend status
        st.markdown(f"### {t('backend_status')}")

        try:
            import requests

            response = requests.get(get_health_check_url(), timeout=2)

            if response.status_code == 200:
                st.success(t("backend_running"))
            else:
                st.error(t("backend_abnormal"))
        except requests.exceptions.ConnectionError:
            st.error(t("backend_not_connected"))
        except Exception as e:
            st.error(t("backend_check_failed", error=str(e)))

        # DEG status
        st.markdown(f"### {t('deg_status')}")

        try:
            response = requests.get(get_api_url("/generate/check"), timeout=2)

            if response.status_code == 200:
                result = response.json()
                if result["installed"]:
                    st.success(t("deg_installed", message=result['message']))
                else:
                    st.warning(t("deg_warning", message=result['message']))
        except Exception as e:
            st.error(t("backend_check_failed", error=str(e)))

        # Database information
        st.markdown(f"### {t('database_info')}")

        st.info(f"""
        - **{t('db_path')}**: {t('db_path_value')}
        - **{t('db_type')}**: {t('db_type_value')}
        - **{t('db_status')}**: {t('db_status_value')}
        """)

        # Version information
        st.markdown(f"### {t('version_info')}")

        st.info(f"""
        - **{t('beancountpilot')}**: v0.1.0
        - **{t('python')}**: 3.11+
        - **{t('streamlit')}**: {t('latest')}
        - **{t('fastapi')}**: {t('latest')}
        """)
