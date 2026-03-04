"""
Transaction classification page
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.i18n import init_i18n, t, label
from frontend.config import get_api_url, get_api_timeout


def render():
    """Render classification page"""
    imported_summary = label(
        "imported_count", count=len(st.session_state.get("transactions", []))
    ).replace("**", "")
    st.markdown(
        (
            f'<div class="main-header"><h1>{label("classify_title")}</h1>'
            f"<p>{imported_summary}</p></div>"
        ),
        unsafe_allow_html=True,
    )

    # Check if there are imported transaction data
    if "transactions" not in st.session_state:
        st.warning(label("no_transactions_warning"))
        st.info(label("go_to_upload"))
        if st.button(label("upload_files"), type="primary", width="stretch"):
            st.session_state.current_page = "upload"
            st.rerun()
        return

    transactions = st.session_state.transactions

    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        st.markdown(
            (
                '<div class="kpi-card">'
                f'<div class="kpi-label">{label("home_transactions_loaded")}</div>'
                f'<div class="kpi-value">{len(transactions)}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with top_col2:
        accounts_count = len(parse_chart_of_accounts(st.session_state.get("chart_of_accounts", "")))
        st.markdown(
            (
                '<div class="kpi-card">'
                '<div class="kpi-label">Available Accounts</div>'
                f'<div class="kpi-value">{accounts_count}</div>'
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

    # Classification buttons
    col1, col2, col3 = st.columns([1, 1, 1.6])

    with col1:
        classify_button = st.button(label("ai_classify"), type="primary", width="stretch")

    with col2:
        if st.button(label("reclassify"), width="stretch"):
            st.session_state.classifications = None
            st.rerun()
    with col3:
        st.markdown(
            (
                '<div class="section-card" style="margin-bottom:0;">'
                "Run AI classification to populate editable account mappings, then generate Beancount entries."
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    # Execute classification
    if classify_button:
        with st.spinner(label("classifying")):
            try:
                import requests

                # Prepare request data
                request_data = {
                    "transactions": transactions,
                    "chart_of_accounts": st.session_state.get("chart_of_accounts", ""),
                    "provider": st.session_state.get("provider", "deepseek"),
                }

                # Call API
                response = requests.post(
                    get_api_url("/classify"),
                    json=request_data,
                    params={"provider": st.session_state.get("provider", "deepseek")},
                    timeout=get_api_timeout(),
                )

                if response.status_code == 200:
                    result = response.json()
                    classifications = result["results"]

                    st.success(label("classify_complete", count=len(classifications)))

                    # Save to session state
                    st.session_state.classifications = classifications

                    # Merge transactions and classification results
                    st.session_state.merged_data = merge_transactions_and_classifications(
                        transactions, classifications
                    )

                    st.rerun()
                else:
                    st.error(label("classify_failed", error=response.text))

            except requests.exceptions.ConnectionError:
                st.error(label("backend_not_connected"))
            except Exception as e:
                st.error(label("classify_failed", error=str(e)))

    # Display classification results
    if "classifications" in st.session_state and st.session_state.classifications:
        st.markdown("---")
        st.subheader(label("classification_results"))

        # Merged data
        merged_data = st.session_state.get("merged_data", [])

        if merged_data:
            df = pd.DataFrame(merged_data)

            # Display editable table
            account_options = build_account_options(
                st.session_state.get("chart_of_accounts", ""),
                merged_data,
            )
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "peer": st.column_config.TextColumn(t("payee"), width="medium"),
                    "item": st.column_config.TextColumn(t("item_label"), width="medium"),
                    "amount": st.column_config.NumberColumn(t("amount"), format="%.2f"),
                    "account": st.column_config.SelectboxColumn(
                        label("account"),
                        options=account_options,
                        required=True,
                        width="large",
                    ),
                    "confidence": st.column_config.ProgressColumn(
                        label("confidence"),
                        help=t("confidence_help"),
                        format="%.2f",
                        min_value=0,
                        max_value=1,
                        width="small",
                    ),
                    "source": st.column_config.TextColumn(label("source"), width="small"),
                },
                hide_index=True,
            )

            # Save changes
            if st.button(label("save_changes"), width="stretch"):
                # TODO: Save changes to backend
                st.success(label("changes_saved"))

            # Generate Beancount file button
            st.markdown("---")
            st.subheader(label("generate_beancount"))

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button(label("generate_and_download"), type="primary", width="stretch"):
                    with st.spinner(label("generating")):
                        try:
                            import requests

                            # Prepare request data
                            request_data = {
                                "transactions": edited_df.to_dict("records"),
                                "provider": st.session_state.get("data_source", "alipay"),
                            }

                            # Call API
                            response = requests.post(
                                get_api_url("/generate"),
                                json=request_data,
                                timeout=get_api_timeout(),
                            )

                            if response.status_code == 200:
                                result = response.json()

                                if result["success"]:
                                    st.success(label("generate_success"))

                                    # Download button
                                    st.download_button(
                                        label=label("download_beancount"),
                                        data=result["beancount_file"],
                                        file_name="output.beancount",
                                        mime="text/plain",
                                        width="stretch",
                                    )
                                else:
                                    st.error(label("generate_failed", message=result['message']))
                            else:
                                st.error(label("generate_failed", message=response.text))

                        except requests.exceptions.ConnectionError:
                            st.error(label("backend_not_connected"))
                        except Exception as e:
                            st.error(label("generate_failed", message=str(e)))

            with col2:
                if st.button(label("preview"), width="stretch"):
                    # Preview Beancount format
                    preview = generate_beancount_preview(edited_df)
                    st.code(preview, language="text")

    # Statistics
    if "classifications" in st.session_state and st.session_state.classifications:
        st.markdown("---")
        st.subheader(label("classification_stats"))

        classifications = st.session_state.classifications

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            ai_count = sum(1 for c in classifications if c["source"] == "ai")
            st.metric(label("ai_classified"), ai_count)

        with col2:
            rule_count = sum(1 for c in classifications if c["source"] == "rule")
            st.metric(label("rule_matched"), rule_count)

        with col3:
            avg_confidence = sum(c["confidence"] for c in classifications) / len(classifications)
            st.metric(label("avg_confidence"), f"{avg_confidence:.2f}")

        with col4:
            st.metric(label("total_classifications"), len(classifications))


def merge_transactions_and_classifications(transactions, classifications):
    """Merge transactions and classification results"""
    # Create classification mapping
    classification_map = {c["transaction_id"]: c for c in classifications}

    merged = []
    for tx in transactions:
        tx_id = tx.get("id", "")
        classification = classification_map.get(tx_id, {})

        merged.append({
            "id": tx_id,
            "peer": tx.get("peer", ""),
            "item": tx.get("item", ""),
            "category": tx.get("category", ""),
            "type": tx.get("type", ""),
            "time": tx.get("time", ""),
            "amount": tx.get("amount", 0),
            "account": classification.get("account", "Expenses:Misc"),
            "confidence": classification.get("confidence", 0),
            "reasoning": classification.get("reasoning", ""),
            "source": classification.get("source", "ai"),
        })

    return merged


def parse_chart_of_accounts(chart_of_accounts):
    """Parse chart of accounts, return account list"""
    accounts = []
    for line in chart_of_accounts.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            accounts.append(line)
    return accounts


def build_account_options(chart_of_accounts, rows=None):
    """Build editor account options from chart + existing classified accounts."""
    options = []
    seen = set()

    for account in parse_chart_of_accounts(chart_of_accounts):
        key = str(account).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        options.append(key)

    for row in rows or []:
        account = str((row or {}).get("account", "")).strip()
        if not account or account in seen:
            continue
        seen.add(account)
        options.append(account)

    if not options:
        return ["Expenses:Misc"]
    return options

def generate_beancount_preview(df):
    """Generate Beancount format preview"""
    lines = []

    for _, row in df.iterrows():
        # Format time
        time_str = row.get("time", "")
        if time_str:
            try:
                from datetime import datetime

                # Try to parse time
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                date_str = dt.strftime("%Y-%m-%d")
            except:
                date_str = time_str.split()[0] if " " in time_str else time_str
        else:
            date_str = "2024-01-01"

        lines.append(f"{date_str} * \"{row.get('item', '')}\"")
        lines.append(f"  {row.get('account', 'Expenses:Misc')}  {row.get('amount', 0):.2f} CNY")
        provider = row.get("provider", st.session_state.get("data_source", "alipay"))
        lines.append(f"  Assets:Bank:{provider.capitalize()}  -{row.get('amount', 0):.2f} CNY")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    init_i18n()
    render()
