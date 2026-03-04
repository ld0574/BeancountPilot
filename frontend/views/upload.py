"""
Upload file page
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import io

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.i18n import init_i18n, t, label
from frontend.config import get_api_url, get_api_timeout


def _read_csv_with_fallback_encoding(uploaded_file) -> pd.DataFrame:
    """
    Read uploaded CSV using common encodings used by payment/bank exports.
    """
    raw = uploaded_file.getvalue()

    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(encoding)
            return pd.read_csv(io.StringIO(text))
        except UnicodeDecodeError:
            continue

    raise ValueError("Unsupported file encoding. Please export CSV as UTF-8 or GBK.")


def render():
    """Render upload page"""
    st.markdown(
        (
            f'<div class="main-header"><h1>{label("upload_title")}</h1>'
            f"<p>{t('upload_description')}</p></div>"
        ),
        unsafe_allow_html=True,
    )

    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_transactions_loaded")}</div>'
                f'<div class="kpi-value">{len(st.session_state.get("transactions", []))}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with top_col2:
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_classified")}</div>'
                f'<div class="kpi-value">{len(st.session_state.get("classifications") or [])}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with top_col3:
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_current_provider")}</div>'
                f'<div class="kpi-value" style="font-size:1.2rem;text-transform:uppercase;">'
                f'{st.session_state.get("provider", "deepseek")}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    st.subheader(label("select_csv_file"))

    # File upload
    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            label("select_csv_file"),
            type=["csv"],
            help=t("select_csv_file_help"),
        )

    with col2:
        data_sources = ["alipay", "wechat", "banks"]
        current_source = st.session_state.get("data_source", "alipay")
        source_index = data_sources.index(current_source) if current_source in data_sources else 0
        provider = st.selectbox(
            label("data_source"),
            data_sources,
            index=source_index,
        )

    if uploaded_file:
        # Display file info
        st.success(label("uploaded_success", filename=uploaded_file.name))

        # Read and preview CSV
        try:
            df = _read_csv_with_fallback_encoding(uploaded_file)

            st.subheader(label("file_preview"))
            st.dataframe(df.head(10), use_container_width=True)

            # Display statistics
            st.subheader(label("statistics"))
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
            st.subheader(label("column_names"))
            st.markdown(f'<div class="section-card">{", ".join(df.columns.tolist())}</div>', unsafe_allow_html=True)

            # Confirm import button
            st.markdown("---")

            if st.button(label("import_data"), type="primary", use_container_width=True):
                with st.spinner(label("importing_data")):
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
                            st.success(label("import_success", count=len(transactions)))

                            # Save to session state
                            st.session_state.transactions = transactions
                            st.session_state.data_source = provider

                            # Prompt to navigate to classification page
                            st.info(label("go_to_classify"))
                        else:
                            st.error(label("import_failed", error=response.text))

                    except requests.exceptions.ConnectionError:
                        st.error(label("backend_not_connected"))
                    except Exception as e:
                        st.error(label("import_failed", error=str(e)))

        except Exception as e:
            st.error(label("file_parse_failed", error=str(e)))

    # Usage guide
    st.markdown("---")
    st.subheader(label("usage_guide"))
    st.markdown(
        f"""
    <div class="section-card">
    <h3 style="margin-top:0;">{label('supported_formats')}</h3>

    <h4>{label('alipay_csv')}</h4>
    - {t('transaction_time')}
    - {t('item_description')}
    - {t('income_expense')}
    - {t('amount')}
    - {t('counterparty')}
    - {t('transaction_status')}

    <h4>{label('wechat_csv')}</h4>
    - {t('transaction_time')}
    - {t('item')}
    - {t('income_expense')}
    - {t('amount')}
    - {t('transaction_type')}
    - {t('counterparty')}
    - {t('current_status')}

    <h4>{label('banks_csv')}</h4>
    - {t('transaction_time')}
    - {label('summary')}
    - {label('counterparty_account')}
    - {t('amount')} / {label('income_amount')} / {label('expense_amount')}
    - {label('debit_credit_flag')} / {t('income_expense')}

    <h4>{label('notes')}</h4>
    - {t('ensure_utf8')}
    - {t('first_line_column')}
    - {t('amount_format')}
    </div>
    """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    init_i18n()
    render()
