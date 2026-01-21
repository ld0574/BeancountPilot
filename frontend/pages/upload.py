"""
Upload file page
"""

import streamlit as st
import pandas as pd
import io
from frontend.i18n import t
from frontend.config import get_api_url, get_api_timeout


def render():
    """Render upload page"""
    st.markdown(f'<div class="main-header"><h1>{t("upload_title")}</h1></div>', unsafe_allow_html=True)

    st.markdown(t("upload_description"))

    # File upload
    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            t("select_csv_file"),
            type=["csv"],
            help=t("select_csv_file_help"),
        )

    with col2:
        provider = st.selectbox(
            t("data_source"),
            ["alipay", "wechat"],
            index=0,
        )

    if uploaded_file:
        # Display file info
        st.success(t("uploaded_success", filename=uploaded_file.name))

        # Read and preview CSV
        try:
            df = pd.read_csv(uploaded_file)

            st.subheader(t("file_preview"))
            st.dataframe(df.head(10), use_container_width=True)

            # Display statistics
            st.subheader(t("statistics"))
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(t("total_records"), len(df))

            with col2:
                st.metric(t("column_count"), len(df.columns))

            with col3:
                st.metric(t("file_size"), f"{uploaded_file.size / 1024:.2f} KB")

            with col4:
                st.metric(t("data_source_label"), provider)

            # Display column names
            st.subheader(t("column_names"))
            st.write(df.columns.tolist())

            # Confirm import button
            st.markdown("---")

            if st.button(t("import_data"), type="primary", use_container_width=True):
                with st.spinner(t("importing_data")):
                    # Call API to import data
                    try:
                        import requests

                        # Reset file pointer
                        uploaded_file.seek(0)

                        # Call API
                        response = requests.post(
                            get_api_url("/upload"),
                            files={"file": uploaded_file},
                            params={"provider": provider},
                            timeout=get_api_timeout(),
                        )

                        if response.status_code == 200:
                            transactions = response.json()
                            st.success(t("import_success", count=len(transactions)))

                            # Save to session state
                            st.session_state.transactions = transactions
                            st.session_state.provider = provider

                            # Prompt to navigate to classification page
                            st.info(t("go_to_classify"))
                        else:
                            st.error(t("import_failed", error=response.text))

                    except requests.exceptions.ConnectionError:
                        st.error(t("backend_not_connected"))
                    except Exception as e:
                        st.error(t("import_failed", error=str(e)))

        except Exception as e:
            st.error(t("file_parse_failed", error=str(e)))

    # Usage guide
    st.markdown("---")
    st.subheader(t("usage_guide"))

    st.markdown(f"""
    ### {t('supported_formats')}

    #### {t('alipay_csv')}
    - {t('transaction_time')}
    - {t('item_description')}
    - {t('income_expense')}
    - {t('amount')}
    - {t('counterparty')}
    - {t('transaction_status')}

    #### {t('wechat_csv')}
    - {t('transaction_time')}
    - {t('item')}
    - {t('income_expense')}
    - {t('amount')}
    - {t('transaction_type')}
    - {t('counterparty')}
    - {t('current_status')}

    ### {t('notes')}
    - {t('ensure_utf8')}
    - {t('first_line_column')}
    - {t('amount_format')}
    """)
