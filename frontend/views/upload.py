"""
Upload file page
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import io
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.i18n import init_i18n, t, label, get_current_language
from frontend.config import get_api_url, get_api_timeout
from src.utils.csv_table_parser import parse_csv_rows

FALLBACK_PROVIDER_CATALOG = [
    {"code": "alipay", "i18n_key": "deg_provider_alipay", "name_en": "Alipay", "name_zh": "支付宝"},
    {"code": "wechat", "i18n_key": "deg_provider_wechat", "name_en": "WeChat Pay", "name_zh": "微信支付"},
    {"code": "ccb", "i18n_key": "deg_provider_ccb", "name_en": "China Construction Bank", "name_zh": "建设银行"},
    {"code": "icbc", "i18n_key": "deg_provider_icbc", "name_en": "ICBC", "name_zh": "工商银行"},
    {"code": "citic", "i18n_key": "deg_provider_citic", "name_en": "CITIC Bank", "name_zh": "中信银行"},
    {"code": "hsbchk", "i18n_key": "deg_provider_hsbchk", "name_en": "HSBC Hong Kong", "name_zh": "汇丰银行香港"},
    {"code": "bmo", "i18n_key": "deg_provider_bmo", "name_en": "Bank of Montreal", "name_zh": "加拿大银行"},
    {"code": "td", "i18n_key": "deg_provider_td", "name_en": "TD Bank", "name_zh": "道明银行"},
    {"code": "cmb", "i18n_key": "deg_provider_cmb", "name_en": "China Merchants Bank", "name_zh": "招商银行"},
    {"code": "bocom_debit", "i18n_key": "deg_provider_bocom_debit", "name_en": "BoCom Debit", "name_zh": "交通银行储蓄卡"},
    {"code": "bocom_credit", "i18n_key": "deg_provider_bocom_credit", "name_en": "BoCom Credit", "name_zh": "交通银行信用卡"},
    {"code": "abc_debit", "i18n_key": "deg_provider_abc_debit", "name_en": "ABC Debit", "name_zh": "中国农业银行储蓄卡"},
    {"code": "htsec", "i18n_key": "deg_provider_htsec", "name_en": "Haitong Securities", "name_zh": "海通证券"},
    {"code": "hxsec", "i18n_key": "deg_provider_hxsec", "name_en": "Huaxi Securities", "name_zh": "华西证券"},
    {"code": "jd", "i18n_key": "deg_provider_jd", "name_en": "JD.com", "name_zh": "京东"},
    {"code": "mt", "i18n_key": "deg_provider_mt", "name_en": "Meituan", "name_zh": "美团"},
    {"code": "huobi", "i18n_key": "deg_provider_huobi", "name_en": "Huobi", "name_zh": "火币"},
]


def _provider_name(item: dict, lang: str) -> str:
    """Render provider display name by current language."""
    i18n_key = str(item.get("i18n_key", "")).strip()
    if i18n_key:
        localized = t(i18n_key)
        if localized and localized != i18n_key:
            return localized

    names = item.get("names") or {}
    if isinstance(names, dict):
        lang_key = (lang or "en").lower()
        base_key = lang_key.split("-", 1)[0]
        if names.get(lang_key):
            return str(names[lang_key]).strip()
        if names.get(base_key):
            return str(names[base_key]).strip()
        if names.get("en"):
            return str(names["en"]).strip()
        if names.get("zh"):
            return str(names["zh"]).strip()

    if str(lang).lower().startswith("zh"):
        return item.get("name_zh") or item.get("name_en") or item.get("code", "")
    return item.get("name_en") or item.get("name_zh") or item.get("code", "")


def _load_provider_catalog() -> list[dict]:
    """Load provider catalog (official + custom) from backend; fallback to local defaults."""
    try:
        resp = requests.get(get_api_url("/generate/provider-mapping"), timeout=min(get_api_timeout(), 3))
        if resp.status_code == 200:
            data = resp.json()
            official = data.get("official_providers") if isinstance(data.get("official_providers"), list) else []
            custom = data.get("custom_providers") if isinstance(data.get("custom_providers"), list) else []
            merged = []
            seen_codes = set()
            for item in [*official, *custom]:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code", "")).strip().lower()
                if not code or code in seen_codes:
                    continue
                seen_codes.add(code)
                merged.append(item)
            if merged:
                return merged
    except Exception:
        pass
    return FALLBACK_PROVIDER_CATALOG


def _read_table_with_fallback(uploaded_file, provider: str = "") -> pd.DataFrame:
    """
    Read uploaded CSV/XLS/XLSX with encoding fallback for CSV.
    """
    name = (uploaded_file.name or "").lower()
    raw = uploaded_file.getvalue()

    if name.endswith(".xls") or name.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(raw))

    rows = parse_csv_rows(raw, provider=provider)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def render():
    """Render upload page"""
    lang = get_current_language()

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
        provider_id = st.session_state.get("provider", "deepseek")
        provider_name = provider_id
        for profile in st.session_state.get("ai_profiles", []):
            if profile.get("id") == provider_id:
                provider_name = profile.get("name", provider_id)
                break
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_current_provider")}</div>'
                f'<div class="kpi-value" style="font-size:1.2rem;">'
                f"{provider_name}</div>"
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
            type=["csv", "xls", "xlsx"],
            help=t("select_csv_file_help"),
        )

    with col2:
        provider_catalog = _load_provider_catalog()
        provider_name_map = {
            item.get("code", ""): _provider_name(item, lang)
            for item in provider_catalog
            if item.get("code")
        }
        data_sources = list(provider_name_map.keys()) + ["custom"]

        current_source = st.session_state.get("data_source", "alipay")
        if current_source not in data_sources:
            current_source = data_sources[0] if data_sources else "alipay"
        source_index = data_sources.index(current_source) if current_source in data_sources else 0
        provider_selected = st.selectbox(
            label("data_source"),
            data_sources,
            index=source_index,
            format_func=lambda x: (
                label("custom_provider_option")
                if x == "custom"
                else provider_name_map.get(x, x)
            ),
        )
        if provider_selected == "custom":
            provider = st.text_input(
                label("custom_data_source_code"),
                value=st.session_state.get("custom_data_source_code", ""),
                help=t("custom_data_source_help"),
            ).strip().lower()
            if provider:
                st.session_state.custom_data_source_code = provider
        else:
            provider = provider_selected

    if uploaded_file:
        # Display file info
        st.success(label("uploaded_success", filename=uploaded_file.name))

        # Read and preview CSV
        try:
            df = _read_table_with_fallback(uploaded_file, provider=provider or provider_selected)

            st.subheader(label("file_preview"))
            st.dataframe(df.head(10), width="stretch")

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
                current_code = provider or provider_selected
                current_name = provider_name_map.get(current_code, current_code)
                st.metric(t("data_source_label"), current_name)

            # Display column names
            st.subheader(label("column_names"))
            st.markdown(f'<div class="section-card">{", ".join(df.columns.tolist())}</div>', unsafe_allow_html=True)

            # Confirm import button
            st.markdown("---")
            st.caption(t("upload_import_behavior_note"))

            if st.button(label("import_data"), type="primary", width="stretch"):
                with st.spinner(label("importing_data")):
                    # Call API to import data
                    try:
                        # Reset file pointer
                        uploaded_file.seek(0)

                        # Call API
                        response = requests.post(
                            get_api_url("/upload"),
                            files={"file": uploaded_file},
                            params={"provider": provider or provider_selected},
                            timeout=get_api_timeout(),
                        )

                        if response.status_code == 200:
                            transactions = response.json()
                            st.success(label("import_success", count=len(transactions)))

                            # Save to session state
                            st.session_state.transactions = transactions
                            st.session_state.data_source = provider or provider_selected
                            st.session_state.pop("classifications", None)
                            st.session_state.pop("merged_data", None)
                            st.session_state.current_page = "classify"
                            st.rerun()

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

    <h4>{label('ccb_xls')}</h4>
    - {t('transaction_time')} / {label('summary')}
    - {label('counterparty_account')}
    - {label('income_amount')} / {label('expense_amount')}
    - {label('debit_credit_flag')}

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
