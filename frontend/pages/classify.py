"""
Transaction classification page
"""

import streamlit as st
import pandas as pd
from frontend.i18n import t
from frontend.config import get_api_url, get_api_timeout


def render():
    """Render classification page"""
    st.markdown(f'<div class="main-header"><h1>{t("classify_title")}</h1></div>', unsafe_allow_html=True)

    # Check if there are imported transaction data
    if "transactions" not in st.session_state:
        st.warning(t("no_transactions_warning"))
        st.info(t("go_to_upload"))
        return

    transactions = st.session_state.transactions

    st.markdown(t("imported_count", count=len(transactions)))

    # Classification buttons
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        classify_button = st.button(t("ai_classify"), type="primary", use_container_width=True)

    with col2:
        if st.button(t("reclassify"), use_container_width=True):
            st.session_state.classifications = None
            st.rerun()

    # Execute classification
    if classify_button:
        with st.spinner(t("classifying")):
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

                    st.success(t("classify_complete", count=len(classifications)))

                    # Save to session state
                    st.session_state.classifications = classifications

                    # Merge transactions and classification results
                    st.session_state.merged_data = merge_transactions_and_classifications(
                        transactions, classifications
                    )

                    st.rerun()
                else:
                    st.error(t("classify_failed", error=response.text))

            except requests.exceptions.ConnectionError:
                st.error(t("backend_not_connected"))
            except Exception as e:
                st.error(t("classify_failed", error=str(e)))

    # Display classification results
    if "classifications" in st.session_state and st.session_state.classifications:
        st.markdown("---")
        st.subheader(t("classification_results"))

        # Merged data
        merged_data = st.session_state.get("merged_data", [])

        if merged_data:
            df = pd.DataFrame(merged_data)

            # Display editable table
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "peer": st.column_config.TextColumn(t("payee"), width="medium"),
                    "item": st.column_config.TextColumn(t("item_label"), width="medium"),
                    "amount": st.column_config.NumberColumn(t("amount"), format="%.2f"),
                    "account": st.column_config.SelectboxColumn(
                        t("account"),
                        options=parse_chart_of_accounts(
                            st.session_state.get("chart_of_accounts", "")
                        ),
                        required=True,
                        width="large",
                    ),
                    "confidence": st.column_config.ProgressColumn(
                        t("confidence"),
                        help=t("confidence_help"),
                        format="%.2f",
                        min_value=0,
                        max_value=1,
                        width="small",
                    ),
                    "source": st.column_config.TextColumn(t("source"), width="small"),
                },
                hide_index=True,
            )

            # Save changes
            if st.button(t("save_changes"), use_container_width=True):
                # TODO: Save changes to backend
                st.success(t("changes_saved"))

            # Generate Beancount file button
            st.markdown("---")
            st.subheader(t("generate_beancount"))

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button(t("generate_and_download"), type="primary", use_container_width=True):
                    with st.spinner(t("generating")):
                        try:
                            import requests

                            # Prepare request data
                            request_data = {
                                "transactions": edited_df.to_dict("records"),
                                "provider": st.session_state.get("provider", "alipay"),
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
                                    st.success(t("generate_success"))

                                    # Download button
                                    st.download_button(
                                        label=t("download_beancount"),
                                        data=result["beancount_file"],
                                        file_name="output.beancount",
                                        mime="text/plain",
                                        use_container_width=True,
                                    )
                                else:
                                    st.error(t("generate_failed", message=result['message']))
                            else:
                                st.error(t("generate_failed", message=response.text))

                        except requests.exceptions.ConnectionError:
                            st.error(t("backend_not_connected"))
                        except Exception as e:
                            st.error(t("generate_failed", message=str(e)))

            with col2:
                if st.button(t("preview"), use_container_width=True):
                    # Preview Beancount format
                    preview = generate_beancount_preview(edited_df)
                    st.code(preview, language="text")

    # Statistics
    if "classifications" in st.session_state and st.session_state.classifications:
        st.markdown("---")
        st.subheader(t("classification_stats"))

        classifications = st.session_state.classifications

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            ai_count = sum(1 for c in classifications if c["source"] == "ai")
            st.metric(t("ai_classified"), ai_count)

        with col2:
            rule_count = sum(1 for c in classifications if c["source"] == "rule")
            st.metric(t("rule_matched"), rule_count)

        with col3:
            avg_confidence = sum(c["confidence"] for c in classifications) / len(classifications)
            st.metric(t("avg_confidence"), f"{avg_confidence:.2f}")

        with col4:
            st.metric(t("total_classifications"), len(classifications))


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
        lines.append(f"  Assets:Bank:{row.get('provider', 'Alipay').capitalize()}  -{row.get('amount', 0):.2f} CNY")
        lines.append("")

    return "\n".join(lines)
