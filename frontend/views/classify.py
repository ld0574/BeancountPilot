"""
Transaction classification page
"""

import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.i18n import init_i18n, t, label
from frontend.config import get_api_url, get_api_timeout


def _run_classification(transactions) -> bool:
    """Run backend classification and sync session state."""
    request_data = {
        "transactions": transactions,
        "chart_of_accounts": st.session_state.get("chart_of_accounts", ""),
        "provider": st.session_state.get("provider", "deepseek"),
    }

    response = requests.post(
        get_api_url("/classify"),
        json=request_data,
        params={"provider": st.session_state.get("provider", "deepseek")},
        timeout=get_api_timeout(),
    )

    if response.status_code != 200:
        st.error(label("classify_failed", error=response.text))
        return False

    result = response.json()
    classifications = result["results"]
    st.session_state.classifications = classifications
    st.session_state.merged_data = merge_transactions_and_classifications(
        transactions,
        classifications,
    )
    st.session_state.auto_classify_pending = False
    st.success(label("classify_complete", count=len(classifications)))
    return True


def _account_issue(account: str) -> str:
    """Return account issue type: empty | other | ''."""
    text = str(account or "").strip()
    if not text or text == "/":
        return "empty"
    leaf = text.split(":")[-1].strip().lower()
    if leaf == "other":
        return "other"
    return ""


def _collect_invalid_account_rows(df: pd.DataFrame) -> list[dict]:
    """Collect rows where target/method account violate strict validation."""
    invalid_rows: list[dict] = []
    if df.empty:
        return invalid_rows

    for idx, row in df.iterrows():
        target = str(row.get("targetAccount", "")).strip()
        method = str(row.get("methodAccount", "")).strip()
        issues = {}
        target_issue = _account_issue(target)
        method_issue = _account_issue(method)
        if target_issue:
            issues["targetAccount"] = target_issue
        if method_issue:
            issues["methodAccount"] = method_issue
        if issues:
            invalid_rows.append(
                {
                    "index": idx + 1,
                    "id": row.get("id", ""),
                    "peer": row.get("peer", ""),
                    "item": row.get("item", ""),
                    "issues": issues,
                }
            )

    return invalid_rows


def _ensure_classification_df(merged_data):
    """Build stable dataframe for classification editor."""
    df = pd.DataFrame(merged_data or [])
    if df.empty:
        return df

    if "targetAccount" not in df.columns:
        df["targetAccount"] = df.get("account", "Expenses:Misc")
    if "methodAccount" not in df.columns:
        df["methodAccount"] = ""
    if "confidence" not in df.columns:
        df["confidence"] = 0.0
    if "source" not in df.columns:
        df["source"] = "ai"
    if "reasoning" not in df.columns:
        df["reasoning"] = ""

    if "id" not in df.columns:
        df["id"] = [str(i) for i in range(1, len(df) + 1)]

    if "account" in df.columns:
        df = df.drop(columns=["account"])

    return df


def _apply_classification_filters(df, focus_mode: str, ai_conf_threshold: float, keyword: str):
    """Apply review filters on classification results."""
    if df.empty:
        return df

    filtered = df.copy()
    source_series = filtered["source"].astype(str).str.lower()

    if focus_mode == "ai_only":
        filtered = filtered[source_series == "ai"]
    elif focus_mode == "rule_only":
        filtered = filtered[source_series == "rule"]
    elif focus_mode == "ai_review":
        confidence_series = pd.to_numeric(filtered.get("confidence", 0.0), errors="coerce").fillna(0.0)
        filtered = filtered[(source_series == "ai") & (confidence_series < ai_conf_threshold)]

    text = str(keyword or "").strip().lower()
    if text:
        search_fields = ["peer", "item", "category", "reasoning", "targetAccount", "methodAccount"]
        available_fields = [field for field in search_fields if field in filtered.columns]
        if available_fields:
            merged_text = (
                filtered[available_fields]
                .fillna("")
                .astype(str)
                .agg(" ".join, axis=1)
                .str.lower()
            )
            filtered = filtered[merged_text.str.contains(text, na=False)]

    return filtered


def _merge_filtered_edits(full_df: pd.DataFrame, edited_df: pd.DataFrame) -> pd.DataFrame:
    """Merge edited filtered rows back into full dataframe by id."""
    if full_df.empty or edited_df.empty or "id" not in full_df.columns or "id" not in edited_df.columns:
        return full_df

    updated = full_df.copy()
    edited = edited_df.set_index("id", drop=False)
    editable_columns = [col for col in edited.columns if col in updated.columns]

    for row_index, row in updated.iterrows():
        row_id = row.get("id")
        if row_id not in edited.index:
            continue
        for col in editable_columns:
            updated.at[row_index, col] = edited.at[row_id, col]

    return updated


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
            st.session_state.merged_data = None
            st.session_state.auto_classify_pending = True
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

    # Auto-run classification after upload/import.
    if st.session_state.get("auto_classify_pending", False):
        with st.spinner(label("classifying")):
            try:
                if _run_classification(transactions):
                    st.rerun()
                st.session_state.auto_classify_pending = False
            except requests.exceptions.ConnectionError:
                st.error(label("backend_not_connected"))
                st.session_state.auto_classify_pending = False
            except Exception as e:
                st.error(label("classify_failed", error=str(e)))
                st.session_state.auto_classify_pending = False

    # Execute classification
    if classify_button:
        with st.spinner(label("classifying")):
            try:
                if _run_classification(transactions):
                    st.rerun()

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
            full_df = _ensure_classification_df(merged_data)

            filter_col1, filter_col2, filter_col3 = st.columns([1.2, 1, 1.4])
            with filter_col1:
                focus_mode = st.selectbox(
                    label("classify_review_focus"),
                    ["all", "ai_only", "ai_review", "rule_only"],
                    format_func=lambda mode: {
                        "all": label("classify_focus_all"),
                        "ai_only": label("classify_focus_ai_only"),
                        "ai_review": label("classify_focus_ai_review"),
                        "rule_only": label("classify_focus_rule_only"),
                    }.get(mode, mode),
                    key="classify_review_focus_mode",
                )
            with filter_col2:
                ai_conf_threshold = st.slider(
                    label("classify_ai_review_threshold"),
                    min_value=0.0,
                    max_value=1.0,
                    value=0.8,
                    step=0.05,
                    key="classify_ai_review_threshold",
                )
            with filter_col3:
                keyword = st.text_input(
                    label("classify_filter_keyword"),
                    value="",
                    key="classify_filter_keyword",
                )

            filtered_df = _apply_classification_filters(
                full_df,
                focus_mode=focus_mode,
                ai_conf_threshold=ai_conf_threshold,
                keyword=keyword,
            )
            visible_ai_count = (
                filtered_df["source"].astype(str).str.lower().eq("ai").sum()
                if not filtered_df.empty else 0
            )
            st.caption(
                label(
                    "classify_filter_summary",
                    visible=len(filtered_df),
                    total=len(full_df),
                    ai=visible_ai_count,
                )
            )

            # Display editable table
            account_options = build_account_options(
                st.session_state.get("chart_of_accounts", ""),
                full_df.to_dict("records"),
            )
            edited_df = st.data_editor(
                filtered_df,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "id": None,
                    "peer": st.column_config.TextColumn(t("payee"), width="medium"),
                    "item": st.column_config.TextColumn(t("item_label"), width="medium"),
                    "amount": st.column_config.NumberColumn(t("amount"), format="%.2f"),
                    "targetAccount": st.column_config.SelectboxColumn(
                        label("target_account"),
                        options=account_options,
                        required=True,
                        width="large",
                    ),
                    "methodAccount": st.column_config.SelectboxColumn(
                        label("method_account"),
                        options=account_options,
                        required=True,
                        width="medium",
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
                key="classification_results_editor",
            )
            full_df = _merge_filtered_edits(full_df, edited_df)
            st.session_state.merged_data = full_df.to_dict("records")
            invalid_rows = _collect_invalid_account_rows(full_df)

            # Save changes
            if st.button(label("save_changes"), width="stretch"):
                # TODO: Save changes to backend
                st.success(label("changes_saved"))

            # Generate Beancount file button
            st.markdown("---")
            st.subheader(label("generate_beancount"))

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button(
                    label("generate_and_download"),
                    type="primary",
                    width="stretch",
                    disabled=bool(invalid_rows),
                ):
                    with st.spinner(label("generating")):
                        try:
                            import requests
                            generate_df = full_df.copy()
                            generate_df["account"] = generate_df.get("targetAccount", "Expenses:Misc")

                            # Prepare request data
                            request_data = {
                                "transactions": generate_df.to_dict("records"),
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
                elif invalid_rows:
                    st.error(label("classify_account_validation_error", count=len(invalid_rows)))
                    has_empty = any(
                        issue == "empty"
                        for row in invalid_rows
                        for issue in row.get("issues", {}).values()
                    )
                    has_other = any(
                        issue == "other"
                        for row in invalid_rows
                        for issue in row.get("issues", {}).values()
                    )
                    if has_empty:
                        st.info(label("classify_empty_accounts_hint"))
                    if has_other:
                        st.warning(label("classify_other_accounts_hint"))
                    preview = invalid_rows[:5]
                    details = " | ".join(
                        (
                            f"#{row['index']} {row.get('peer', '')}/{row.get('item', '')}: "
                            + ",".join(
                                f"{field}({reason})"
                                for field, reason in row.get("issues", {}).items()
                            )
                        )
                        for row in preview
                    )
                    st.caption(
                        label(
                            "classify_account_invalid_rows_preview",
                            rows=details,
                        )
                    )

            with col2:
                if st.button(label("preview"), width="stretch"):
                    # Preview Beancount format
                    preview = generate_beancount_preview(full_df)
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
            "targetAccount": classification.get(
                "targetAccount",
                classification.get("account", "Expenses:Misc"),
            ),
            "methodAccount": classification.get("methodAccount", ""),
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
        for key in ("account", "targetAccount", "methodAccount"):
            account = str((row or {}).get(key, "")).strip()
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
        lines.append(
            f"  {row.get('targetAccount', row.get('account', 'Expenses:Misc'))}  "
            f"{row.get('amount', 0):.2f} CNY"
        )
        provider = row.get("provider", st.session_state.get("data_source", "alipay"))
        lines.append(f"  Assets:Bank:{provider.capitalize()}  -{row.get('amount', 0):.2f} CNY")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    init_i18n()
    render()
