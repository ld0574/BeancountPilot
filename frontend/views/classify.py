"""
Transaction classification page
"""

import sys
import uuid
from pathlib import Path

import streamlit as st
import pandas as pd
import requests
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.i18n import init_i18n, t, label, get_current_language
from frontend.config import get_api_url, get_api_timeout


def _localize_reasoning_text(reasoning: str) -> str:
    """Localize built-in/system reasoning phrases to current i18n language."""
    text = str(reasoning or "").strip()
    if not text:
        return ""

    exact_map = {
        "Matched DEG rule": label("reason_matched_deg_rule"),
        "Matched DEG prefill": label("reason_matched_deg_prefill"),
    }
    if text in exact_map:
        return exact_map[text]

    fallback_prefix = "Matched DEG rule but account fields were incomplete; used AI fallback"
    if text.startswith(fallback_prefix):
        tail = text[len(fallback_prefix):].strip()
        localized = label("reason_deg_fallback_ai")
        if tail.startswith("."):
            tail = tail[1:].strip()
        return f"{localized}. {tail}" if tail else localized

    parse_failed_prefix = "Parse failed:"
    if text.startswith(parse_failed_prefix):
        detail = text[len(parse_failed_prefix):].strip()
        return label("reason_parse_failed", message=detail)

    return text


def _run_classification(transactions) -> bool:
    """Run backend classification and sync session state."""
    request_data = {
        "transactions": transactions,
        "chart_of_accounts": st.session_state.get("chart_of_accounts", ""),
        "provider": st.session_state.get("provider", "deepseek"),
        "language": get_current_language(),
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
    if "provider" not in df.columns:
        df["provider"] = ""

    if "id" not in df.columns:
        df["id"] = [str(i) for i in range(1, len(df) + 1)]

    if "account" in df.columns:
        df = df.drop(columns=["account"])

    return df


def _split_rule_ai_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into rule-matched and AI-classified groups."""
    if df.empty:
        return df.copy(), df.copy()

    source_series = df["source"].astype(str).str.lower()
    rule_df = df[source_series == "rule"].copy()
    ai_df = df[source_series != "rule"].copy()
    return rule_df, ai_df


def _filter_ai_review_rows(df: pd.DataFrame, review_mode: str, threshold: float, keyword: str) -> pd.DataFrame:
    """Filter AI review queue."""
    if df.empty:
        return df

    filtered = df.copy()
    confidence_series = pd.to_numeric(filtered.get("confidence", 0.0), errors="coerce").fillna(0.0)

    if review_mode == "low_conf":
        filtered = filtered[confidence_series < threshold]
    elif review_mode == "missing_accounts":
        mask = []
        for _, row in filtered.iterrows():
            target_issue = _account_issue(row.get("targetAccount", ""))
            method_issue = _account_issue(row.get("methodAccount", ""))
            mask.append(bool(target_issue or method_issue))
        filtered = filtered[pd.Series(mask, index=filtered.index)]

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


def _pick_suggestion_matcher(row: dict) -> tuple[str, str]:
    """Pick one stable matcher field for suggested DEG rule."""
    peer = str(row.get("peer", "")).strip()
    item = str(row.get("item", "")).strip()
    category = str(row.get("category", "")).strip()
    if peer and item and peer == item:
        item = ""
    if peer:
        return "peer", peer
    if item:
        return "item", item
    if category:
        return "category", category
    return "", ""


def _rule_suggestion_signature(
    provider: str,
    match_field: str,
    match_value: str,
    target_account: str,
    method_account: str,
) -> str:
    """Build comparable signature for rule suggestion de-dup."""
    parts = [
        str(provider or "").strip().lower(),
        str(match_field or "").strip().lower(),
        str(match_value or "").strip().lower(),
        str(target_account or "").strip().lower(),
        str(method_account or "").strip().lower(),
    ]
    return "||".join(parts)


def _build_ai_rule_suggestions(ai_df: pd.DataFrame, min_confidence: float) -> pd.DataFrame:
    """Create rule suggestions from AI results without persisting."""
    if ai_df.empty:
        return pd.DataFrame()

    rows = []
    seen: set[str] = set()
    for _, row in ai_df.iterrows():
        target_account = str(row.get("targetAccount", "")).strip()
        method_account = str(row.get("methodAccount", "")).strip()
        if _account_issue(target_account) or _account_issue(method_account):
            continue

        confidence_value = pd.to_numeric(row.get("confidence", 0.0), errors="coerce")
        confidence = 0.0 if pd.isna(confidence_value) else float(confidence_value)
        if confidence < min_confidence:
            continue

        match_field, match_value = _pick_suggestion_matcher(row.to_dict())
        if not match_field or not match_value:
            continue

        provider = str(row.get("provider", "")).strip().lower()
        signature = _rule_suggestion_signature(
            provider,
            match_field,
            match_value,
            target_account,
            method_account,
        )
        if signature in seen:
            continue
        seen.add(signature)
        rows.append(
            {
                "select": False,
                "id": str(row.get("id", "")),
                "provider": provider,
                "matchField": match_field,
                "matchValue": match_value,
                "targetAccount": target_account,
                "methodAccount": method_account,
                "confidence": max(0.0, min(confidence, 1.0)),
                "reasoning": str(row.get("reasoning", "")).strip(),
                "signature": signature,
            }
        )

    return pd.DataFrame(rows)


def _load_existing_rule_signatures() -> set[str]:
    """Load signatures of existing rules for de-dup in suggestion UI."""
    signatures: set[str] = set()
    try:
        response = requests.get(
            get_api_url("/rules"),
            params={"skip": 0, "limit": 2000},
            timeout=get_api_timeout(),
        )
    except Exception:
        return signatures

    if response.status_code != 200:
        return signatures

    for rule in response.json():
        account = str(rule.get("account", "")).strip()
        if not account:
            continue

        conditions = rule.get("conditions", {}) or {}
        provider_values: list[str] = [""]
        raw_provider = conditions.get("provider")
        if isinstance(raw_provider, str) and raw_provider.strip():
            provider_values = [raw_provider.strip().lower()]
        elif isinstance(raw_provider, list):
            normalized = [str(item).strip().lower() for item in raw_provider if str(item).strip()]
            provider_values = normalized or [""]

        method_account = str(conditions.get("methodAccount", "")).strip()

        for key in ("peer", "item", "category"):
            raw_value = conditions.get(key)
            tokens: list[str] = []
            if isinstance(raw_value, str):
                tokens = [raw_value]
            elif isinstance(raw_value, list):
                tokens = [str(item) for item in raw_value]
            for token in [str(item).strip() for item in tokens if str(item).strip() and str(item).strip() != "/"]:
                for provider in provider_values:
                    signatures.add(
                        _rule_suggestion_signature(
                            provider,
                            key,
                            token,
                            account,
                            method_account,
                        )
                    )
    return signatures


def _build_rule_payload_from_suggestion(row: dict) -> tuple[dict, str]:
    """Convert one suggestion row to RuleCreate payload."""
    provider = str(row.get("provider", "")).strip().lower()
    match_field = str(row.get("matchField", "")).strip()
    match_value = str(row.get("matchValue", "")).strip()
    target_account = str(row.get("targetAccount", "")).strip()
    method_account = str(row.get("methodAccount", "")).strip()
    confidence_value = pd.to_numeric(row.get("confidence", 0.0), errors="coerce")
    confidence = 0.0 if pd.isna(confidence_value) else float(confidence_value)
    confidence = max(0.0, min(confidence, 1.0))

    conditions = {match_field: [match_value]}
    if provider:
        conditions["provider"] = provider
    if method_account:
        conditions["methodAccount"] = method_account

    provider_part = provider or "global"
    rule_name = f"ai-{provider_part}-{match_field}-{uuid.uuid4().hex[:8]}"
    payload = {
        "name": rule_name,
        "conditions": conditions,
        "account": target_account,
        "confidence": confidence,
        "source": "user",
    }
    signature = _rule_suggestion_signature(
        provider,
        match_field,
        match_value,
        target_account,
        method_account,
    )
    return payload, signature


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
    if st.session_state.get("scroll_to_top_once", False):
        components.html(
            """
            <script>
            try {
              const parentDoc = window.parent.document;
              window.parent.scrollTo(0, 0);
              const main = parentDoc.querySelector("section.main");
              if (main) { main.scrollTo(0, 0); }
            } catch (e) {}
            </script>
            """,
            height=0,
        )
        st.session_state.scroll_to_top_once = False

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

        merged_data = st.session_state.get("merged_data", [])
        if merged_data:
            full_df = _ensure_classification_df(merged_data)
            account_options = build_account_options(
                st.session_state.get("chart_of_accounts", ""),
                full_df.to_dict("records"),
            )
            rule_df, ai_df = _split_rule_ai_rows(full_df)

            summary_col1, summary_col2 = st.columns(2)
            with summary_col1:
                st.metric(label("classify_ai_review_section"), len(ai_df))
            with summary_col2:
                st.metric(label("classify_rule_matched_section"), len(rule_df))

            st.markdown("#### " + label("classify_ai_review_section"))
            filter_col1, filter_col2, filter_col3 = st.columns([1.1, 1, 1.5])
            with filter_col1:
                review_mode = st.selectbox(
                    label("classify_ai_review_mode"),
                    ["all", "low_conf", "missing_accounts"],
                    format_func=lambda mode: {
                        "all": label("classify_ai_review_mode_all"),
                        "low_conf": label("classify_ai_review_mode_low_conf"),
                        "missing_accounts": label("classify_ai_review_mode_missing"),
                    }.get(mode, mode),
                    key="classify_ai_review_mode",
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

            filtered_ai_df = _filter_ai_review_rows(
                ai_df,
                review_mode=review_mode,
                threshold=ai_conf_threshold,
                keyword=keyword,
            )
            st.caption(
                label(
                    "classify_ai_review_summary",
                    visible=len(filtered_ai_df),
                    total=len(ai_df),
                )
            )

            if filtered_ai_df.empty:
                st.info(label("classify_ai_review_empty"))
            else:
                edited_ai_df = st.data_editor(
                    filtered_ai_df,
                    num_rows="fixed",
                    width="stretch",
                    column_config={
                        "id": None,
                        "provider": None,
                        "peer": st.column_config.TextColumn(t("payee"), width="medium"),
                        "item": st.column_config.TextColumn(t("item_label"), width="medium"),
                        "category": st.column_config.TextColumn(label("classify_category"), width="small"),
                        "time": st.column_config.TextColumn(t("transaction_time"), width="small"),
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
                        "reasoning": st.column_config.TextColumn(label("reasoning"), width="large"),
                    },
                    disabled=[
                        "peer",
                        "item",
                        "category",
                        "time",
                        "amount",
                        "confidence",
                        "source",
                        "reasoning",
                    ],
                    hide_index=True,
                    key="classification_ai_editor",
                )
                full_df = _merge_filtered_edits(full_df, edited_ai_df)

            # Persist edits immediately.
            st.session_state.merged_data = full_df.to_dict("records")

            # Recompute split after edits.
            rule_df, ai_df = _split_rule_ai_rows(full_df)
            invalid_rows = _collect_invalid_account_rows(full_df)

            if st.button(label("save_changes"), width="stretch"):
                st.success(label("changes_saved"))

            st.markdown("#### " + label("classify_ai_rule_suggestions_title"))
            suggestion_col1, suggestion_col2 = st.columns([1, 2])
            with suggestion_col1:
                suggestion_min_confidence = st.slider(
                    label("classify_suggestion_conf_threshold"),
                    min_value=0.0,
                    max_value=1.0,
                    value=0.9,
                    step=0.05,
                    key="classify_suggestion_conf_threshold",
                )
            with suggestion_col2:
                st.caption(label("classify_ai_rule_suggestions_hint"))

            suggestions_df = _build_ai_rule_suggestions(
                ai_df,
                min_confidence=suggestion_min_confidence,
            )
            if suggestions_df.empty:
                st.info(label("classify_ai_rule_suggestions_empty"))
            else:
                created_signatures = st.session_state.get("classify_created_rule_signatures", set())
                if not isinstance(created_signatures, set):
                    created_signatures = set()
                existing_signatures = _load_existing_rule_signatures()
                known_signatures = existing_signatures.union(created_signatures)
                suggestions_df["exists"] = suggestions_df["signature"].isin(list(known_signatures))
                suggestions_df["existsLabel"] = suggestions_df["exists"].map(
                    lambda flag: (
                        label("classify_rule_suggestion_existing")
                        if bool(flag)
                        else label("classify_rule_suggestion_new")
                    )
                )

                suggestion_editor_df = st.data_editor(
                    suggestions_df,
                    num_rows="fixed",
                    width="stretch",
                    column_config={
                        "select": st.column_config.CheckboxColumn(
                            label("classify_rule_suggestion_select"),
                            default=False,
                        ),
                        "id": None,
                        "signature": None,
                        "exists": None,
                        "provider": st.column_config.TextColumn(t("provider_code"), width="small"),
                        "matchField": st.column_config.TextColumn(
                            label("classify_rule_suggestion_match_field"),
                            width="small",
                        ),
                        "matchValue": st.column_config.TextColumn(
                            label("classify_rule_suggestion_match_value"),
                            width="large",
                        ),
                        "targetAccount": st.column_config.TextColumn(label("target_account"), width="large"),
                        "methodAccount": st.column_config.TextColumn(label("method_account"), width="medium"),
                        "confidence": st.column_config.ProgressColumn(
                            label("confidence"),
                            format="%.2f",
                            min_value=0.0,
                            max_value=1.0,
                            width="small",
                        ),
                        "existsLabel": st.column_config.TextColumn(
                            label("classify_rule_suggestion_status"),
                            width="small",
                        ),
                        "reasoning": st.column_config.TextColumn(label("reasoning"), width="large"),
                    },
                    disabled=[
                        "id",
                        "provider",
                        "matchField",
                        "matchValue",
                        "targetAccount",
                        "methodAccount",
                        "confidence",
                        "reasoning",
                        "existsLabel",
                    ],
                    hide_index=True,
                    key="classification_ai_rule_suggestions_editor",
                )

                if st.button(label("classify_confirm_add_selected_rules"), type="primary", width="stretch"):
                    selected_df = suggestion_editor_df[suggestion_editor_df["select"] == True]
                    success_count = 0
                    duplicate_count = 0
                    error_count = 0

                    for _, row in selected_df.iterrows():
                        payload, signature = _build_rule_payload_from_suggestion(row.to_dict())
                        if signature in known_signatures:
                            duplicate_count += 1
                            continue
                        try:
                            response = requests.post(
                                get_api_url("/rules"),
                                json=payload,
                                timeout=get_api_timeout(),
                            )
                            if response.status_code in (200, 201):
                                success_count += 1
                                known_signatures.add(signature)
                                created_signatures.add(signature)
                            else:
                                error_count += 1
                        except Exception:
                            error_count += 1

                    st.session_state.classify_created_rule_signatures = created_signatures
                    if success_count:
                        st.success(
                            label(
                                "classify_rule_suggestion_add_result",
                                success=success_count,
                                duplicates=duplicate_count,
                                failed=error_count,
                            )
                        )
                        st.rerun()
                    elif duplicate_count or error_count:
                        st.warning(
                            label(
                                "classify_rule_suggestion_add_result",
                                success=success_count,
                                duplicates=duplicate_count,
                                failed=error_count,
                            )
                        )

            st.markdown("#### " + label("classify_rule_matched_section"))
            if rule_df.empty:
                st.info(label("classify_rule_match_empty"))
            else:
                st.caption(label("classify_rule_match_summary", count=len(rule_df)))
                st.dataframe(
                    rule_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "id": None,
                        "provider": None,
                        "peer": st.column_config.TextColumn(t("payee"), width="medium"),
                        "item": st.column_config.TextColumn(t("item_label"), width="medium"),
                        "category": st.column_config.TextColumn(label("classify_category"), width="small"),
                        "time": st.column_config.TextColumn(t("transaction_time"), width="small"),
                        "amount": st.column_config.NumberColumn(t("amount"), format="%.2f"),
                        "targetAccount": st.column_config.TextColumn(label("target_account"), width="large"),
                        "methodAccount": st.column_config.TextColumn(label("method_account"), width="medium"),
                        "confidence": st.column_config.ProgressColumn(
                            label("confidence"),
                            format="%.2f",
                            min_value=0.0,
                            max_value=1.0,
                            width="small",
                        ),
                        "source": st.column_config.TextColumn(label("source"), width="small"),
                        "reasoning": st.column_config.TextColumn(label("reasoning"), width="large"),
                    },
                )

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
                            generate_df = full_df.copy()
                            generate_df["account"] = generate_df.get("targetAccount", "Expenses:Misc")

                            request_data = {
                                "transactions": generate_df.to_dict("records"),
                                "provider": st.session_state.get("data_source", "alipay"),
                            }

                            response = requests.post(
                                get_api_url("/generate"),
                                json=request_data,
                                timeout=get_api_timeout(),
                            )

                            if response.status_code == 200:
                                result = response.json()

                                if result["success"]:
                                    st.success(label("generate_success"))
                                    st.download_button(
                                        label=label("download_beancount"),
                                        data=result["beancount_file"],
                                        file_name="output.beancount",
                                        mime="text/plain",
                                        width="stretch",
                                    )
                                else:
                                    st.error(label("generate_failed", message=result["message"]))
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
            "provider": tx.get("provider", ""),
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
            "reasoning": _localize_reasoning_text(classification.get("reasoning", "")),
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
