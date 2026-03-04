"""
Settings page
"""

import json
import sys
import uuid
import html
from pathlib import Path

import streamlit as st
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.i18n import init_i18n, t, label, get_current_language
from frontend.config import get_api_url, get_health_check_url, get_api_timeout
from src.db.init import DEFAULT_LEDGER_FILES


LEDGER_FILES = [
    "assets.bean",
    "equity.bean",
    "expenses.bean",
    "income.bean",
    "liabilities.bean",
]

AI_PROVIDER_TYPES = ["deepseek", "openai", "ollama", "custom"]

DEFAULT_AI_PROFILE_TEMPLATE = {
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.3,
        "timeout": 30,
    },
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
        "temperature": 0.3,
        "timeout": 30,
    },
    "ollama": {
        "api_base": "http://localhost:11434/v1",
        "api_key": "ollama",
        "model": "llama3.2:3b",
        "temperature": 0.3,
        "timeout": 60,
    },
    "custom": {
        "api_base": "",
        "api_key": "",
        "model": "",
        "temperature": 0.3,
        "timeout": 30,
    },
}


def _get_ledger_data_dir() -> Path:
    """Get default local data directory for Beancount template files."""
    return Path.home() / ".beancountpilot" / "data"


def _provider_label(provider: str) -> str:
    labels = {
        "deepseek": "DeepSeek",
        "openai": "OpenAI",
        "ollama": "Ollama",
        "custom": "Custom",
    }
    return labels.get(provider, provider)


def _build_profile(provider: str, name: str = "", profile_id: str = "") -> dict:
    """Build a default profile structure."""
    provider = provider if provider in AI_PROVIDER_TYPES else "custom"
    defaults = DEFAULT_AI_PROFILE_TEMPLATE[provider]
    return {
        "id": profile_id.strip() or f"profile-{uuid.uuid4().hex[:8]}",
        "name": name.strip() or f"{_provider_label(provider)} Profile",
        "provider": provider,
        "api_base": defaults["api_base"],
        "api_key": defaults["api_key"],
        "model": defaults["model"],
        "temperature": defaults["temperature"],
        "timeout": defaults["timeout"],
    }


def _normalize_ai_profiles(raw_profiles: list[dict] | None) -> list[dict]:
    """Normalize profile list for UI editing."""
    profiles = []
    raw_profiles = raw_profiles or []
    seen_ids = set()

    for raw in raw_profiles:
        provider = str(raw.get("provider", "deepseek")).lower()
        if provider not in AI_PROVIDER_TYPES:
            provider = "custom"

        defaults = DEFAULT_AI_PROFILE_TEMPLATE[provider]

        profile_id = str(raw.get("id", "")).strip()
        if not profile_id or profile_id in seen_ids:
            profile_id = f"profile-{uuid.uuid4().hex[:8]}"
        seen_ids.add(profile_id)

        profile = {
            "id": profile_id,
            "name": str(raw.get("name", "")).strip() or f"{_provider_label(provider)} Profile",
            "provider": provider,
            "api_base": str(raw.get("api_base", defaults["api_base"])),
            "api_key": str(raw.get("api_key", defaults["api_key"])),
            "model": str(raw.get("model", defaults["model"])),
            "temperature": float(raw.get("temperature", defaults["temperature"])),
            "timeout": int(raw.get("timeout", defaults["timeout"])),
        }
        profiles.append(profile)

    if not profiles:
        profiles.append(_build_profile("deepseek", "DeepSeek Profile", "deepseek-default"))

    return profiles


def _resolve_default_profile_id(profiles: list[dict], ref: str) -> str:
    """Resolve active profile id."""
    if not profiles:
        return ""
    ids = [p["id"] for p in profiles]
    if ref in ids:
        return ref
    if ref in AI_PROVIDER_TYPES:
        for profile in profiles:
            if profile["provider"] == ref:
                return profile["id"]
    return profiles[0]["id"]


def _load_ai_config() -> tuple[str, list[dict]]:
    """Load AI config from backend; fallback to defaults on failure."""
    fallback_profiles = _normalize_ai_profiles([])
    fallback_default = fallback_profiles[0]["id"]

    try:
        timeout = min(get_api_timeout(), 3)
        response = requests.get(get_api_url("/ai/config"), timeout=timeout)
        if response.status_code != 200:
            return fallback_default, fallback_profiles

        data = response.json()
        profiles = _normalize_ai_profiles(data.get("profiles"))
        default_profile_id = _resolve_default_profile_id(
            profiles,
            str(data.get("default_profile_id") or data.get("default_provider") or ""),
        )
        return default_profile_id, profiles
    except Exception:
        return fallback_default, fallback_profiles


def _decode_uploaded_file(content: bytes) -> str:
    """Decode uploaded text file with common encodings."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unsupported file encoding. Please upload UTF-8 or GBK text.")


def _render_deg_mapping_text(mappings: dict[str, str]) -> str:
    """Render provider mapping as editable lines."""
    if not mappings:
        return ""
    lines = [f"{k}={v}" for k, v in sorted(mappings.items(), key=lambda x: x[0])]
    return "\n".join(lines)


def _parse_deg_mapping_text(text: str) -> dict[str, str]:
    """
    Parse mapping text lines:
    source=provider
    source->provider
    source:provider
    """
    mapping = {}
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        delimiter = None
        for candidate in ("->", "=", ":"):
            if candidate in line:
                delimiter = candidate
                break

        if delimiter is None:
            raise ValueError(f"Line {idx}: expected one of '->', '=', ':'")

        src, target = line.split(delimiter, 1)
        src = src.strip().lower()
        target = target.strip().lower()
        if not src or not target:
            raise ValueError(f"Line {idx}: source and target cannot be empty")
        mapping[src] = target

    return mapping


def _normalize_custom_provider_rows(raw_items: list[dict] | None) -> list[dict]:
    """Normalize custom provider rows for UI display/edit."""
    rows = []
    seen_codes = set()
    for item in raw_items or []:
        code = str(item.get("code", "")).strip().lower()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        rows.append(
            {
                "code": code,
                "name_en": str(item.get("name_en", "")).strip(),
                "name_zh": str(item.get("name_zh", "")).strip(),
                "names": item.get("names", {}) if isinstance(item.get("names"), dict) else {},
                "i18n_key": str(item.get("i18n_key", "")).strip(),
            }
        )
    return sorted(rows, key=lambda x: x["code"])


def _provider_display_name(item: dict, lang: str) -> str:
    """Render provider name with i18n-key first, then names fallback."""
    i18n_key = str(item.get("i18n_key", "")).strip()
    if i18n_key:
        localized = t(i18n_key)
        if localized and localized != i18n_key:
            return localized

    names = item.get("names") or {}
    if isinstance(names, dict):
        lang_key = (lang or "en").lower()
        base_key = lang_key.split("-", 1)[0]
        for key in (lang_key, base_key, "en", "zh"):
            value = names.get(key)
            if value:
                return str(value).strip()

    name_en = str(item.get("name_en", "")).strip()
    name_zh = str(item.get("name_zh", "")).strip()
    if lang.startswith("zh"):
        return name_zh or name_en or str(item.get("code", ""))
    return name_en or name_zh or str(item.get("code", ""))


def _parse_chart_accounts(chart_of_accounts: str) -> list[str]:
    """Parse chart_of_accounts text to account list."""
    accounts = []
    seen = set()
    for line in chart_of_accounts.split("\n"):
        account = line.strip()
        if not account or account.startswith("#"):
            continue
        if account in seen:
            continue
        seen.add(account)
        accounts.append(account)
    return accounts


def _parse_keyword_list(text: str) -> list[str]:
    """Parse comma/newline separated keywords."""
    tokens = []
    for part in str(text or "").replace("\n", ",").split(","):
        token = part.strip()
        if token:
            tokens.append(token)
    return tokens


def _extract_open_accounts_from_bean(content: str) -> list[str]:
    """Extract account names from Beancount open directives."""
    accounts = []
    seen = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue

        parts = line.split()
        if len(parts) < 3:
            continue
        if parts[1].lower() != "open":
            continue

        account = parts[2].strip()
        if ":" not in account:
            continue
        if account in seen:
            continue
        seen.add(account)
        accounts.append(account)
    return accounts


def _sync_chart_from_ledger_files(ledger_dir: Path) -> list[str]:
    """Read all ledger template files and produce a merged account list."""
    merged_accounts = []
    seen = set()
    for filename in LEDGER_FILES:
        file_path = ledger_dir / filename
        if not file_path.exists():
            continue
        content = file_path.read_text(encoding="utf-8")
        for account in _extract_open_accounts_from_bean(content):
            if account in seen:
                continue
            seen.add(account)
            merged_accounts.append(account)
    return merged_accounts


def _render_open_lines(accounts: list[str]) -> list[str]:
    """Render accounts to default open lines."""
    return [f"2010-01-01 open {account} CNY" for account in accounts]


def _sync_ledger_files_from_chart_accounts(ledger_dir: Path, accounts: list[str]) -> None:
    """Write accounts from chart_of_accounts into ledger template files by prefix."""
    grouped = {
        "assets.bean": [],
        "equity.bean": [],
        "expenses.bean": [],
        "income.bean": [],
        "liabilities.bean": [],
    }

    for account in accounts:
        if account.startswith("Assets:"):
            grouped["assets.bean"].append(account)
        elif account.startswith("Equity:"):
            grouped["equity.bean"].append(account)
        elif account.startswith("Expenses:"):
            grouped["expenses.bean"].append(account)
        elif account.startswith("Income:"):
            grouped["income.bean"].append(account)
        elif account.startswith("Liabilities:"):
            grouped["liabilities.bean"].append(account)

    for filename in LEDGER_FILES:
        header = DEFAULT_LEDGER_FILES.get(filename, "").splitlines()[0] or f"; {filename}"
        open_lines = _render_open_lines(grouped.get(filename, []))
        content = "\n".join([header, *open_lines]).rstrip() + "\n"
        (ledger_dir / filename).write_text(content, encoding="utf-8")


def render():
    """Render settings page"""
    st.markdown(
        (
            f'<div class="main-header"><h1>{label("settings_title")}</h1>'
            f"<p>{t('settings_description')}</p></div>"
        ),
        unsafe_allow_html=True,
    )

    def _clear_ai_dialog_state() -> None:
        """Clear AI settings dialog state."""
        st.session_state.pop("ai_profile_edit_id", None)
        st.session_state.pop("ai_profile_delete_id", None)

    def _clear_rule_dialog_state() -> None:
        """Clear Rules tab dialog state."""
        active_rule_id = str(st.session_state.get("rule_edit_dialog_id", "")).strip()
        if active_rule_id:
            st.session_state.pop(f"rule_edit_scope_{active_rule_id}", None)
            st.session_state.pop(f"rule_edit_provider_{active_rule_id}", None)
            st.session_state.pop(f"rule_edit_provider_text_{active_rule_id}", None)
            st.session_state.pop(f"rule_edit_payload_json_{active_rule_id}", None)
            st.session_state.pop(f"rule_edit_payload_yaml_{active_rule_id}", None)
            st.session_state.pop(f"rule_edit_payload_yaml_normalized_{active_rule_id}", None)
        st.session_state.pop("rule_edit_dialog_id", None)
        st.session_state.pop("rule_delete_confirm_id", None)
        st.session_state.pop("rule_add_dialog_open", None)
        st.session_state.pop("rule_cleanup_dialog_open", None)
        st.session_state.pop("rule_cleanup_scope", None)
        st.session_state.pop("rule_cleanup_provider", None)
        st.session_state.pop("rule_import_dialog_open", None)
        st.session_state.pop("rule_import_dialog_provider", None)

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            label("ai_settings"),
            label("chart_of_accounts_config"),
            label("rule_management"),
            label("system_info"),
            label("deg_mapping_tab"),
        ]
    )

    # AI Settings
    with tab1:
        st.subheader(label("ai_provider_config"))

        def _show_toast_warning(message: str) -> None:
            """Show warning in toast when available; fallback to inline warning."""
            if hasattr(st, "toast"):
                st.toast(message, icon="⚠️")
            else:
                st.warning(message)

        if "ai_config_loaded" not in st.session_state:
            default_profile_id, profiles = _load_ai_config()
            st.session_state.ai_profiles = profiles
            st.session_state.provider = default_profile_id
            st.session_state.ai_config_loaded = True

        profiles = _normalize_ai_profiles(st.session_state.get("ai_profiles"))
        current_profile_id = _resolve_default_profile_id(
            profiles, str(st.session_state.get("provider", ""))
        )
        st.session_state.provider = current_profile_id

        profile_options = [profile["id"] for profile in profiles]
        profile_by_id = {profile["id"]: profile for profile in profiles}

        def format_profile(profile_id: str) -> str:
            profile = profile_by_id[profile_id]
            return f"{profile['name']} ({_provider_label(profile['provider'])})"

        st.markdown("---")
        st.subheader(label("add_profile"))
        add_col1, add_col2, add_col3 = st.columns([1.6, 1.2, 0.8])
        with add_col1:
            new_profile_name = st.text_input(
                label("profile_name"),
                key="new_ai_profile_name",
                placeholder=label("profile_name_placeholder"),
            )
        with add_col2:
            new_profile_type = st.selectbox(
                label("profile_type"),
                AI_PROVIDER_TYPES,
                key="new_ai_profile_type",
                format_func=_provider_label,
            )
        with add_col3:
            st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
            add_clicked = st.button(label("add_profile"), width="stretch")

        if add_clicked:
            profile = _build_profile(
                provider=new_profile_type,
                name=new_profile_name,
            )
            profiles.append(profile)
            st.session_state.ai_profiles = profiles
            st.session_state.provider = profile["id"]
            st.rerun()

        def _persist_ai_profiles(remaining_profiles: list[dict], selected_profile_id: str) -> None:
            payload = {
                "default_profile_id": selected_profile_id,
                "profiles": remaining_profiles,
            }
            try:
                response = requests.put(
                    get_api_url("/ai/config"),
                    json=payload,
                    timeout=get_api_timeout(),
                )
                if response.status_code == 200:
                    st.session_state.ai_profiles = remaining_profiles
                    st.session_state.provider = selected_profile_id

                    selected = next(
                        (p for p in remaining_profiles if p["id"] == selected_profile_id),
                        remaining_profiles[0],
                    )
                    st.session_state.api_key = selected.get("api_key", "")
                    st.session_state.api_base = selected.get("api_base", "")
                    st.session_state.model = selected.get("model", "")
                    st.session_state.temperature = selected.get("temperature", 0.3)
                    st.session_state.timeout = selected.get("timeout", 30)
                    st.success(label("config_saved"))
                else:
                    st.error(label("config_save_failed", error=response.text))
            except requests.exceptions.ConnectionError:
                st.error(label("backend_not_connected"))
            except Exception as e:
                st.error(label("config_save_failed", error=str(e)))

        active_col1, active_col2 = st.columns([3.2, 1.0])
        with active_col1:
            active_profile_id = st.selectbox(
                label("active_ai_provider"),
                profile_options,
                index=profile_options.index(current_profile_id),
                format_func=format_profile,
                key="active_ai_profile_select",
            )
            st.caption(label("active_ai_provider_help"))
        with active_col2:
            st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
            save_active_clicked = st.button(
                label("save_config"),
                type="primary",
                width="stretch",
                key="save_active_ai_profile_btn",
            )

        if save_active_clicked:
            _persist_ai_profiles(profiles, active_profile_id)
            st.rerun()

        st.markdown("---")
        st.subheader(label("multi_provider_config"))

        st.markdown(
            """
            <style>
            .ai-profile-cell {
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                line-height: 1.2;
                font-size: 0.86rem;
            }
            .ai-profile-header {
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                line-height: 1.05;
                font-size: 0.8rem;
            }
            div[data-testid="stButton"] button[kind="tertiary"] {
                white-space: nowrap;
                font-size: 0.76rem;
                line-height: 1.0;
                padding: 0.1rem 0.38rem;
                min-height: 1.55rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        def _compact_profile_text(value: str, max_len: int = 48) -> tuple[str, str]:
            text = str(value or "").strip()
            if not text:
                return "-", "-"
            if len(text) <= max_len:
                return text, text
            return text[: max_len - 1] + "…", text

        def _render_profile_cell(col, value: str, max_len: int = 48):
            short_text, full_text = _compact_profile_text(value, max_len=max_len)
            col.markdown(
                (
                    "<div class='ai-profile-cell' title='{full}'>"
                    "{short}"
                    "</div>"
                ).format(
                    full=html.escape(full_text, quote=True),
                    short=html.escape(short_text),
                ),
                unsafe_allow_html=True,
            )

        table_header_cols = st.columns([2.1, 1.0, 2.6, 1.8, 0.9, 1.6])
        table_headers = [
            label("profile_name"),
            label("profile_type"),
            label("api_base"),
            label("model"),
            label("temperature"),
            label("rule_col_actions"),
        ]
        for idx, header in enumerate(table_headers):
            table_header_cols[idx].markdown(
                f"<div class='ai-profile-header'><strong>{html.escape(header)}</strong></div>",
                unsafe_allow_html=True,
            )
        st.markdown("---")

        for profile_id in profile_options:
            profile = profile_by_id[profile_id]
            row_cols = st.columns([2.1, 1.0, 2.6, 1.8, 0.9, 1.6])
            _render_profile_cell(row_cols[0], profile.get("name", ""), max_len=42)
            _render_profile_cell(row_cols[1], _provider_label(profile.get("provider", "")), max_len=18)
            _render_profile_cell(row_cols[2], profile.get("api_base", ""), max_len=52)
            _render_profile_cell(row_cols[3], profile.get("model", ""), max_len=28)
            _render_profile_cell(row_cols[4], f"{float(profile.get('temperature', 0.3)):.1f}", max_len=6)
            with row_cols[5]:
                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    if st.button(
                        label("ai_profile_modify_button"),
                        key=f"ai_profile_modify_btn_{profile_id}",
                        type="tertiary",
                        width="content",
                    ):
                        _clear_rule_dialog_state()
                        st.session_state.pop("ai_profile_delete_id", None)
                        st.session_state.ai_profile_edit_id = profile_id
                        st.rerun()
                with action_col2:
                    if st.button(
                        label("ai_profile_delete_button"),
                        key=f"ai_profile_delete_btn_{profile_id}",
                        type="tertiary",
                        width="content",
                    ):
                        _clear_rule_dialog_state()
                        st.session_state.pop("ai_profile_edit_id", None)
                        st.session_state.ai_profile_delete_id = profile_id
                        st.rerun()

        edit_profile_id = str(st.session_state.get("ai_profile_edit_id", "")).strip()
        if edit_profile_id and edit_profile_id in profile_by_id:
            editing_profile = profile_by_id[edit_profile_id]
            if hasattr(st, "dialog"):
                @st.dialog(
                    label("ai_profile_edit_dialog_title"),
                    on_dismiss=lambda: st.session_state.pop("ai_profile_edit_id", None),
                )
                def _render_ai_profile_edit_dialog():
                    with st.form(f"ai_profile_edit_form_{edit_profile_id}"):
                        edited_name = st.text_input(
                            label("profile_name"),
                            value=editing_profile.get("name", ""),
                        )
                        edited_type = st.selectbox(
                            label("profile_type"),
                            AI_PROVIDER_TYPES,
                            index=AI_PROVIDER_TYPES.index(editing_profile.get("provider", "custom"))
                            if editing_profile.get("provider", "custom") in AI_PROVIDER_TYPES
                            else AI_PROVIDER_TYPES.index("custom"),
                            format_func=_provider_label,
                        )
                        type_defaults = DEFAULT_AI_PROFILE_TEMPLATE[edited_type]
                        edited_api_base = st.text_input(
                            label("api_base"),
                            value=editing_profile.get("api_base", "") or type_defaults["api_base"],
                        )
                        edited_api_key = st.text_input(
                            label("api_key"),
                            value=editing_profile.get("api_key", ""),
                            type="password",
                        )
                        edited_model = st.text_input(
                            label("model"),
                            value=editing_profile.get("model", "") or type_defaults["model"],
                        )
                        edited_temperature = st.slider(
                            label("temperature"),
                            min_value=0.0,
                            max_value=1.0,
                            value=float(editing_profile.get("temperature", 0.3)),
                            step=0.1,
                            help=t("temperature_help"),
                        )
                        edited_timeout = st.number_input(
                            label("timeout"),
                            min_value=10,
                            max_value=600,
                            value=int(editing_profile.get("timeout", 30)),
                        )

                        save_col, cancel_col = st.columns(2)
                        with save_col:
                            save_edit_clicked = st.form_submit_button(
                                label("save_config"),
                                type="primary",
                                width="stretch",
                            )
                        with cancel_col:
                            cancel_edit_clicked = st.form_submit_button(
                                label("cancel_edit_rule"),
                                width="stretch",
                            )

                    if cancel_edit_clicked:
                        st.session_state.pop("ai_profile_edit_id", None)
                        st.rerun()

                    if save_edit_clicked:
                        updated_profiles = []
                        for profile in profiles:
                            if profile["id"] == edit_profile_id:
                                updated_profiles.append(
                                    {
                                        "id": edit_profile_id,
                                        "name": edited_name.strip() or f"{_provider_label(edited_type)} Profile",
                                        "provider": edited_type,
                                        "api_base": edited_api_base.strip(),
                                        "api_key": edited_api_key.strip(),
                                        "model": edited_model.strip(),
                                        "temperature": float(edited_temperature),
                                        "timeout": int(edited_timeout),
                                    }
                                )
                            else:
                                updated_profiles.append(profile)

                        selected_profile_id = active_profile_id
                        if selected_profile_id not in [p["id"] for p in updated_profiles]:
                            selected_profile_id = updated_profiles[0]["id"]
                        _persist_ai_profiles(updated_profiles, selected_profile_id)
                        st.session_state.pop("ai_profile_edit_id", None)
                        st.rerun()

                _render_ai_profile_edit_dialog()
            else:
                st.warning(label("rule_edit_dialog_not_supported"))

        delete_profile_id = str(st.session_state.get("ai_profile_delete_id", "")).strip()
        if delete_profile_id and delete_profile_id in profile_by_id:
            deleting_profile = profile_by_id[delete_profile_id]
            if hasattr(st, "dialog"):
                @st.dialog(
                    label("ai_profile_delete_confirm_title"),
                    on_dismiss=lambda: st.session_state.pop("ai_profile_delete_id", None),
                )
                def _render_ai_profile_delete_confirm_dialog():
                    st.warning(
                        label(
                            "ai_profile_delete_confirm_text",
                            name=deleting_profile.get("name", delete_profile_id),
                        )
                    )
                    confirm_col, cancel_col = st.columns(2)
                    with confirm_col:
                        confirm_delete_clicked = st.button(
                            label("ai_profile_delete_button"),
                            type="primary",
                            width="stretch",
                            key=f"confirm_ai_profile_delete_btn_{delete_profile_id}",
                        )
                    with cancel_col:
                        cancel_delete_clicked = st.button(
                            label("cancel_edit_rule"),
                            width="stretch",
                            key=f"cancel_ai_profile_delete_btn_{delete_profile_id}",
                        )

                    if cancel_delete_clicked:
                        st.session_state.pop("ai_profile_delete_id", None)
                        st.rerun()

                    if confirm_delete_clicked:
                        if len(profiles) <= 1:
                            _show_toast_warning(label("at_least_one_profile"))
                        else:
                            remaining_profiles = [
                                profile for profile in profiles
                                if profile["id"] != delete_profile_id
                            ]
                            selected_profile_id = active_profile_id
                            if selected_profile_id == delete_profile_id:
                                selected_profile_id = remaining_profiles[0]["id"]
                            _persist_ai_profiles(remaining_profiles, selected_profile_id)
                        st.session_state.pop("ai_profile_delete_id", None)
                        st.rerun()

                _render_ai_profile_delete_confirm_dialog()
            else:
                st.warning(label("rule_edit_dialog_not_supported"))

    # Chart of Accounts
    with tab2:
        st.subheader(label("chart_of_accounts_config_title"))
        ledger_dir = _get_ledger_data_dir()
        ledger_dir.mkdir(parents=True, exist_ok=True)

        chart_of_accounts = st.text_area(
            label("chart_of_accounts"),
            value=st.session_state.get("chart_of_accounts", ""),
            height=400,
            help=t("chart_of_accounts_help"),
        )

        # Auto-save to session state
        st.session_state.chart_of_accounts = chart_of_accounts

        action_col1, action_col2, action_col3 = st.columns(3)

        # Validate chart of accounts
        with action_col1:
            validate_clicked = st.button(label("validate_chart"), width="stretch")

        with action_col2:
            sync_from_ledger_clicked = st.button(
                label("sync_from_ledger_files"), width="stretch"
            )

        with action_col3:
            sync_to_ledger_clicked = st.button(
                label("sync_to_ledger_files"), width="stretch"
            )

        if validate_clicked:
            accounts = []
            for line in chart_of_accounts.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    accounts.append(line)

            st.success(label("total_accounts", count=len(accounts)))

            # Display account list
            st.dataframe(
                pd.DataFrame({"Account": accounts}),
                width="stretch",
            )

        if sync_from_ledger_clicked:
            accounts = _sync_chart_from_ledger_files(ledger_dir)
            if accounts:
                st.session_state.chart_of_accounts = "\n".join(accounts)
                st.success(label("synced_from_ledger_files", count=len(accounts)))
                st.rerun()
            else:
                st.warning(label("no_accounts_in_ledger_files"))

        if sync_to_ledger_clicked:
            accounts = _parse_chart_accounts(chart_of_accounts)
            _sync_ledger_files_from_chart_accounts(ledger_dir, accounts)
            st.success(label("synced_to_ledger_files", count=len(accounts)))

        st.markdown("---")
        st.subheader(label("ledger_files_manager"))

        selected_ledger_file = st.selectbox(
            label("ledger_file"),
            LEDGER_FILES,
            key="settings_selected_ledger_file",
        )
        selected_ledger_path = ledger_dir / selected_ledger_file

        if not selected_ledger_path.exists():
            default_content = DEFAULT_LEDGER_FILES.get(selected_ledger_file, "")
            selected_ledger_path.write_text(default_content.rstrip() + "\n", encoding="utf-8")

        st.caption(f"{label('ledger_file_path')}: `{selected_ledger_path}`")

        editor_key = f"ledger_editor__{selected_ledger_file}"
        if editor_key not in st.session_state:
            st.session_state[editor_key] = selected_ledger_path.read_text(encoding="utf-8")

        st.text_area(
            label("ledger_file_content"),
            key=editor_key,
            height=260,
        )

        action_col1, action_col2 = st.columns(2)
        with action_col1:
            if st.button(label("save_ledger_file"), width="stretch"):
                selected_ledger_path.write_text(st.session_state.get(editor_key, ""), encoding="utf-8")
                synced_accounts = _sync_chart_from_ledger_files(ledger_dir)
                st.session_state.chart_of_accounts = "\n".join(synced_accounts)
                st.success(label("ledger_file_saved", filename=selected_ledger_file))

        with action_col2:
            if st.button(label("reload_ledger_file"), width="stretch"):
                st.session_state[editor_key] = selected_ledger_path.read_text(encoding="utf-8")
                st.rerun()

        uploaded_ledger_file = st.file_uploader(
            label("import_ledger_file"),
            type=["bean", "beancount", "txt"],
            key=f"ledger_upload__{selected_ledger_file}",
            help=label("import_ledger_file_help"),
        )
        if uploaded_ledger_file is not None and st.button(
            label("import_to_selected_file"), width="stretch"
        ):
            try:
                imported_content = _decode_uploaded_file(uploaded_ledger_file.read())
                selected_ledger_path.write_text(imported_content, encoding="utf-8")
                st.session_state[editor_key] = imported_content
                synced_accounts = _sync_chart_from_ledger_files(ledger_dir)
                st.session_state.chart_of_accounts = "\n".join(synced_accounts)
                st.success(label("ledger_file_imported", filename=selected_ledger_file))
            except Exception as e:
                st.error(label("ledger_file_import_failed", error=str(e)))

    # Rule Management
    with tab3:
        st.subheader(label("rule_management_title"))
        st.caption(
            t("rule_pipeline_note")
        )

        provider_options: list[tuple[str, str]] = [("", label("scope_global"))]
        provider_catalog: list[tuple[str, str]] = []
        mapping_data: dict = {}
        try:
            mapping_resp = requests.get(get_api_url("/generate/provider-mapping"), timeout=3)
            if mapping_resp.status_code == 200:
                mapping_data = mapping_resp.json()
                seen_codes = set()
                for catalog_key in ("official_providers", "custom_providers"):
                    for item in mapping_data.get(catalog_key, []):
                        code = str(item.get("code", "")).strip().lower()
                        if not code or code in seen_codes:
                            continue
                        seen_codes.add(code)
                        display_name = _provider_display_name(item, get_current_language())
                        provider_catalog.append((code, display_name))
                        provider_options.append((code, display_name))
        except Exception:
            pass

        st.markdown("---")

        provider_field_map = {
            "alipay": ["category", "method"],
            "wechat": ["status"],
            "ccb": ["txType", "status"],
        }

        # Rule table + filter + edit
        table_title_col, table_add_col, table_cleanup_col = st.columns([5.2, 1.2, 1.6])
        with table_title_col:
            st.subheader(label("rule_table_title"))
        with table_add_col:
            if st.button(label("rule_add_open_modal"), type="primary", width="stretch"):
                _clear_ai_dialog_state()
                st.session_state.rule_add_dialog_open = True
                st.rerun()
        with table_cleanup_col:
            if st.button(label("rule_cleanup_auto_open_modal"), width="stretch"):
                _clear_ai_dialog_state()
                selected_scope = str(st.session_state.get("rule_filter_scope", "all")).strip().lower()
                if selected_scope not in {"all", "global", "provider"}:
                    selected_scope = "all"
                selected_provider = str(st.session_state.get("rule_filter_provider", "all")).strip().lower() or "all"
                st.session_state.rule_cleanup_scope = selected_scope
                st.session_state.rule_cleanup_provider = selected_provider
                st.session_state.rule_cleanup_dialog_open = True
                st.rerun()

        def _rule_provider_list(conditions: dict) -> list[str]:
            cond_provider = (conditions or {}).get("provider")
            if isinstance(cond_provider, str):
                cond_provider = [cond_provider]
            if isinstance(cond_provider, list):
                return [str(v).strip().lower() for v in cond_provider if str(v).strip()]
            return []

        def _rule_target_method(rule: dict) -> tuple[str, str]:
            """Split stored rule fields into targetAccount and methodAccount for UI."""
            conditions = (rule or {}).get("conditions", {}) or {}
            has_target = bool(conditions.get("_deg_has_target", True))
            target_account = str((rule or {}).get("account", "")).strip() if has_target else ""
            method_raw = conditions.get("methodAccount", "")
            if isinstance(method_raw, list):
                method_account = next((str(v).strip() for v in method_raw if str(v).strip()), "")
            else:
                method_account = str(method_raw or "").strip()

            # Legacy/imported method-only rules may store method in `account`.
            if not has_target and not method_account:
                method_account = str((rule or {}).get("account", "")).strip()
            return target_account, method_account

        scope_col, provider_col, source_col, keyword_col = st.columns([1, 1, 1, 1.4])
        with scope_col:
            scope_filter = st.selectbox(
                label("rule_filter_scope"),
                ["all", "global", "provider"],
                format_func=lambda x: (
                    label("rule_filter_scope_all")
                    if x == "all"
                    else (label("scope_global") if x == "global" else label("scope_provider_specific"))
                ),
                key="rule_filter_scope",
            )
        with provider_col:
            provider_filter_options = ["all"] + [code for code, _ in provider_options if code]
            provider_filter = st.selectbox(
                label("rule_filter_provider"),
                provider_filter_options,
                format_func=lambda x: (
                    label("rule_filter_provider_all")
                    if x == "all"
                    else next((n for c, n in provider_options if c == x), x)
                ),
                key="rule_filter_provider",
            )
        with source_col:
            source_filter = st.selectbox(
                label("rule_filter_source"),
                ["all", "user", "auto"],
                format_func=lambda x: label("rule_filter_source_all") if x == "all" else x,
                key="rule_filter_source",
            )
        with keyword_col:
            keyword_filter = st.text_input(
                label("rule_filter_keyword"),
                key="rule_filter_keyword",
            ).strip().lower()

        filtered_rules = []
        try:
            def _clear_rule_edit_state():
                active_rule_id = str(st.session_state.get("rule_edit_dialog_id", "")).strip()
                if active_rule_id:
                    st.session_state.pop(f"rule_edit_scope_{active_rule_id}", None)
                    st.session_state.pop(f"rule_edit_provider_{active_rule_id}", None)
                    st.session_state.pop(f"rule_edit_provider_text_{active_rule_id}", None)
                    st.session_state.pop(f"rule_edit_payload_json_{active_rule_id}", None)
                    st.session_state.pop(f"rule_edit_payload_yaml_{active_rule_id}", None)
                    st.session_state.pop(f"rule_edit_payload_yaml_normalized_{active_rule_id}", None)
                st.session_state.pop("rule_edit_dialog_id", None)

            response = requests.get(
                get_api_url("/rules"),
                params={"skip": 0, "limit": 1000},
                timeout=get_api_timeout(),
            )

            if response.status_code != 200:
                st.warning(label("failed_load_rules"))
            else:
                rules = response.json()
                for rule in rules:
                    conditions = rule.get("conditions", {}) or {}
                    providers = _rule_provider_list(conditions)
                    is_provider_rule = bool(providers)

                    if scope_filter == "global" and is_provider_rule:
                        continue
                    if scope_filter == "provider" and not is_provider_rule:
                        continue
                    if provider_filter != "all" and provider_filter not in providers:
                        continue
                    if source_filter != "all" and str(rule.get("source", "")).lower() != source_filter:
                        continue

                    if keyword_filter:
                        target_text, method_text = _rule_target_method(rule)
                        haystack = " ".join(
                            [
                                str(rule.get("name", "")),
                                target_text,
                                method_text,
                                str(rule.get("account", "")),
                                str(rule.get("source", "")),
                                " ".join(providers),
                                json.dumps(conditions, ensure_ascii=False),
                            ]
                        ).lower()
                        if keyword_filter not in haystack:
                            continue

                    filtered_rules.append(rule)

                if filtered_rules:
                    filtered_rules = sorted(
                        filtered_rules,
                        key=lambda r: (str(r.get("updated_at", "")), str(r.get("created_at", ""))),
                        reverse=True,
                    )
                    rule_index = {
                        str(rule.get("id", "")): rule
                        for rule in filtered_rules
                        if str(rule.get("id", "")).strip()
                    }

                    pager_col1, pager_col2, pager_col3, pager_col4 = st.columns([1, 1, 1.2, 1.2])
                    with pager_col1:
                        page_size_options = [20, 50, 100, 200]
                        default_page_size = 20
                        current_page_size = st.session_state.get("rule_page_size", default_page_size)
                        if current_page_size not in page_size_options:
                            st.session_state.rule_page_size = default_page_size
                        page_size = st.selectbox(
                            label("rule_page_size"),
                            page_size_options,
                            index=page_size_options.index(st.session_state.get("rule_page_size", default_page_size)),
                            key="rule_page_size",
                        )
                    total_rules = len(filtered_rules)
                    total_pages = max(1, (total_rules + page_size - 1) // page_size)
                    current_page = int(st.session_state.get("rule_page_number", 1))
                    current_page = min(max(current_page, 1), total_pages)

                    with pager_col2:
                        st.caption(label("rule_total_records", count=total_rules))
                    with pager_col3:
                        st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
                        if st.button(label("rule_prev_page"), width="stretch"):
                            st.session_state.rule_page_number = max(1, current_page - 1)
                            st.rerun()
                    with pager_col4:
                        st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
                        if st.button(label("rule_next_page"), width="stretch"):
                            st.session_state.rule_page_number = min(total_pages, current_page + 1)
                            st.rerun()

                    st.session_state.rule_page_number = current_page
                    st.caption(label("rule_page_indicator", current=current_page, total=total_pages))

                    start = (current_page - 1) * page_size
                    end = start + page_size
                    page_rules = filtered_rules[start:end]

                    provider_name_map = {code: name for code, name in provider_options if code}

                    st.markdown(
                        """
                        <style>
                        .rule-cell-wrap {
                            white-space: normal;
                            overflow-wrap: anywhere;
                            line-height: 1.15;
                            font-size: 0.86rem;
                        }
                        .rule-header-nowrap {
                            white-space: nowrap;
                            font-size: 0.8rem;
                            line-height: 1.05;
                        }
                        div[data-testid="stButton"] button[kind="tertiary"] {
                            white-space: nowrap;
                            font-size: 0.76rem;
                            line-height: 1.0;
                            padding: 0.1rem 0.38rem;
                            min-height: 1.55rem;
                        }
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )

                    def _compact_text(value: str, max_len: int = 100) -> tuple[str, str]:
                        text = str(value or "").strip()
                        if not text:
                            return "-", "-"
                        if len(text) <= max_len:
                            return text, text
                        return text[: max_len - 1] + "…", text

                    def _render_wrap_cell(col, value: str, max_len: int = 100):
                        short_text, full_text = _compact_text(value, max_len=max_len)
                        col.markdown(
                            (
                                "<div class='rule-cell-wrap' title='{full}'>"
                                "{short}"
                                "</div>"
                            ).format(
                                full=html.escape(full_text, quote=True),
                                short=html.escape(short_text),
                            ),
                            unsafe_allow_html=True,
                        )

                    header_cols = st.columns([0.8, 0.9, 1.8, 1.8, 0.8, 0.8, 2.8, 1.8])
                    header_titles = [
                        label("rule_col_scope"),
                        label("rule_col_provider"),
                        label("target_account"),
                        label("method_account"),
                        label("rule_col_confidence"),
                        label("rule_col_source"),
                        label("rule_col_conditions"),
                        label("rule_col_actions"),
                    ]
                    for idx, title in enumerate(header_titles):
                        if title:
                            header_cols[idx].markdown(
                                f"<div class='rule-header-nowrap'><strong>{html.escape(title)}</strong></div>",
                                unsafe_allow_html=True,
                            )
                    st.markdown("---")

                    for rule in page_rules:
                        rule_id = str(rule.get("id", ""))
                        conditions = rule.get("conditions", {}) or {}
                        target_account_text, method_account_text = _rule_target_method(rule)
                        providers = _rule_provider_list(conditions)
                        provider_display = (
                            ", ".join(provider_name_map.get(code, code) for code in providers)
                            if providers
                            else "-"
                        )
                        cond_parts = []
                        for key in ("regexp", "peer", "item", "category", "transactionType", "txType"):
                            value = conditions.get(key)
                            if value is None:
                                continue
                            if isinstance(value, list):
                                value = ",".join(str(v) for v in value[:3])
                            text = str(value).strip()
                            if text:
                                cond_parts.append(f"{key}:{text}")
                        if not cond_parts:
                            for key, value in conditions.items():
                                if key in {"provider", "skip", "_deg_only", "_deg_has_target"}:
                                    continue
                                text = str(value).strip()
                                if text:
                                    cond_parts.append(f"{key}:{text}")
                                if len(cond_parts) >= 2:
                                    break
                        cond_summary = " | ".join(cond_parts) if cond_parts else "-"
                        if len(cond_summary) > 96:
                            cond_summary = cond_summary[:95] + "…"

                        row_cols = st.columns([0.8, 0.9, 1.8, 1.8, 0.8, 0.8, 2.8, 1.8])
                        _render_wrap_cell(
                            row_cols[0],
                            label("scope_provider_specific") if providers else label("scope_global")
                        )
                        _render_wrap_cell(row_cols[1], provider_display, max_len=40)
                        _render_wrap_cell(row_cols[2], target_account_text, max_len=50)
                        _render_wrap_cell(row_cols[3], method_account_text, max_len=50)
                        _render_wrap_cell(row_cols[4], f"{float(rule.get('confidence', 1.0)):.2f}", max_len=8)
                        _render_wrap_cell(row_cols[5], str(rule.get("source", "")), max_len=10)
                        _render_wrap_cell(row_cols[6], cond_summary, max_len=96)

                        with row_cols[7]:
                            action_col1, action_col2 = st.columns(2)
                            with action_col1:
                                if st.button(
                                    label("rule_edit_button_compact"),
                                    key=f"rule_edit_btn_{rule_id}",
                                    type="tertiary",
                                    width="content",
                                ):
                                    _clear_ai_dialog_state()
                                    st.session_state.pop("rule_delete_confirm_id", None)
                                    st.session_state.rule_edit_dialog_id = rule_id
                                    st.rerun()
                            with action_col2:
                                if st.button(
                                    label("rule_delete_button_compact"),
                                    key=f"rule_delete_btn_{rule_id}",
                                    type="tertiary",
                                    width="content",
                                ):
                                    _clear_ai_dialog_state()
                                    _clear_rule_edit_state()
                                    st.session_state.rule_delete_confirm_id = rule_id
                                    st.rerun()

                    dialog_rule_id = str(st.session_state.get("rule_edit_dialog_id", "")).strip()
                    if (
                        dialog_rule_id
                        and dialog_rule_id in rule_index
                        and not str(st.session_state.get("rule_delete_confirm_id", "")).strip()
                    ):
                        dialog_rule = rule_index[dialog_rule_id]
                        current_conditions = dialog_rule.get("conditions", {}) or {}

                        if not isinstance(current_conditions, dict):
                            current_conditions = {}

                        if hasattr(st, "dialog"):
                            @st.dialog(
                                label("rule_edit_dialog_title"),
                                width="large",
                                on_dismiss=lambda: _clear_rule_edit_state(),
                            )
                            def _render_rule_edit_dialog():
                                edit_scope_key = f"rule_edit_scope_{dialog_rule_id}"
                                edit_provider_key = f"rule_edit_provider_{dialog_rule_id}"
                                edit_provider_text_key = f"rule_edit_provider_text_{dialog_rule_id}"
                                edit_json_key = f"rule_edit_payload_json_{dialog_rule_id}"

                                def _condition_to_text(value) -> str:
                                    if isinstance(value, list):
                                        return ", ".join(str(v) for v in value)
                                    if value is None:
                                        return ""
                                    return str(value)

                                providers = _rule_provider_list(current_conditions)
                                scope_default = "provider" if providers else "global"
                                provider_default = providers[0] if providers else ""
                                regexp_default = str(current_conditions.get("regexp", "")).strip()
                                peer_default = _condition_to_text(current_conditions.get("peer", ""))
                                item_default = _condition_to_text(current_conditions.get("item", ""))
                                category_default = _condition_to_text(current_conditions.get("category", ""))
                                has_target_default = bool(current_conditions.get("_deg_has_target", True))
                                target_default = (
                                    str(dialog_rule.get("account", "")).strip()
                                    if has_target_default else ""
                                )
                                method_default = _condition_to_text(current_conditions.get("methodAccount", ""))
                                if not method_default and not has_target_default:
                                    method_default = str(dialog_rule.get("account", "")).strip()
                                tx_type_key = (
                                    "txType"
                                    if ("txType" in current_conditions and "transactionType" not in current_conditions)
                                    else "transactionType"
                                )
                                tx_type_default = str(current_conditions.get(tx_type_key, "")).strip()

                                internal_preserve_keys = {"skip", "_deg_only", "_deg_has_target", "sep"}
                                editable_base_keys = {
                                    "provider",
                                    "regexp",
                                    "peer",
                                    "item",
                                    "category",
                                    "transactionType",
                                    "txType",
                                }
                                extra_candidates = [
                                    key for key in current_conditions.keys()
                                    if key not in editable_base_keys and key not in internal_preserve_keys
                                ]
                                existing_extra_key = extra_candidates[0] if extra_candidates else ""
                                existing_extra_value = _condition_to_text(
                                    current_conditions.get(existing_extra_key, "")
                                ) if existing_extra_key else ""
                                preserved_extra_items = {
                                    key: current_conditions.get(key)
                                    for key in extra_candidates[1:]
                                }

                                default_payload = {
                                    "targetAccount": target_default,
                                    "methodAccount": method_default,
                                    "account": target_default,
                                    "confidence": float(dialog_rule.get("confidence", 1.0)),
                                    "source": str(dialog_rule.get("source", "user")),
                                    "conditions": current_conditions,
                                }
                                if edit_scope_key not in st.session_state:
                                    st.session_state[edit_scope_key] = scope_default
                                if (
                                    edit_json_key not in st.session_state
                                    or not str(st.session_state.get(edit_json_key, "")).strip()
                                ):
                                    st.session_state[edit_json_key] = json.dumps(
                                        default_payload,
                                        ensure_ascii=False,
                                        indent=2,
                                    )

                                def _clear_edit_session_state():
                                    _clear_rule_edit_state()
                                    st.session_state.pop(edit_scope_key, None)
                                    st.session_state.pop(edit_provider_key, None)
                                    st.session_state.pop(edit_provider_text_key, None)
                                    st.session_state.pop(edit_json_key, None)

                                def _save_rule(
                                    target_account_value: str,
                                    method_account_value: str,
                                    source_value: str,
                                    confidence_value: float,
                                    new_conditions: dict,
                                ):
                                    if source_value not in {"user", "auto"}:
                                        raise ValueError("`source` must be `user` or `auto`")
                                    if not isinstance(new_conditions, dict):
                                        raise ValueError("`conditions` must be an object")

                                    target_clean = str(target_account_value or "").strip()
                                    method_clean = str(method_account_value or "").strip()
                                    normalized_conditions = dict(new_conditions)
                                    if method_clean:
                                        normalized_conditions["methodAccount"] = method_clean
                                    else:
                                        normalized_conditions.pop("methodAccount", None)

                                    if target_clean:
                                        normalized_conditions.pop("_deg_only", None)
                                        normalized_conditions.pop("_deg_has_target", None)
                                    elif method_clean:
                                        normalized_conditions["_deg_only"] = True
                                        normalized_conditions["_deg_has_target"] = False
                                    else:
                                        raise ValueError("At least one of targetAccount or methodAccount is required")

                                    existing_name = str(dialog_rule.get("name", "")).strip()
                                    if not existing_name:
                                        short_id = dialog_rule_id[:8] if dialog_rule_id else uuid.uuid4().hex[:8]
                                        existing_name = f"rule-{short_id}"

                                    payload = {
                                        "name": existing_name,
                                        "account": target_clean or method_clean,
                                        "confidence": max(0.0, min(1.0, float(confidence_value))),
                                        "source": source_value,
                                        "conditions": normalized_conditions,
                                    }

                                    update_resp = requests.put(
                                        get_api_url(f"/rules/{dialog_rule_id}"),
                                        json=payload,
                                        timeout=get_api_timeout(),
                                    )
                                    if update_resp.status_code == 200:
                                        _clear_edit_session_state()
                                        st.success(label("rule_updated"))
                                        st.rerun()
                                    else:
                                        st.error(label("rule_update_failed", error=update_resp.text))

                                tab_json, tab_form = st.tabs(
                                    [label("rule_edit_mode_json"), label("rule_edit_mode_form")]
                                )

                                with tab_json:
                                    st.caption(label("rule_edit_json_help"))
                                    reload_json_col, _ = st.columns([1.4, 4.6])
                                    with reload_json_col:
                                        if st.button(
                                            label("rule_reload_json_from_current"),
                                            key=f"rule_reload_json_btn_{dialog_rule_id}",
                                            width="stretch",
                                        ):
                                            st.session_state[edit_json_key] = json.dumps(
                                                default_payload,
                                                ensure_ascii=False,
                                                indent=2,
                                            )
                                            st.rerun()
                                    with st.form(f"rule_edit_dialog_form_json_{dialog_rule_id}"):
                                        edit_payload_text = st.text_area(
                                            label("rule_payload_json"),
                                            key=edit_json_key,
                                            height=560,
                                        )
                                        json_save_col, json_cancel_col = st.columns(2)
                                        with json_save_col:
                                            json_save = st.form_submit_button(
                                                label("save_rule_changes"),
                                                type="primary",
                                                width="stretch",
                                            )
                                        with json_cancel_col:
                                            json_cancel = st.form_submit_button(
                                                label("cancel_edit_rule"),
                                                width="stretch",
                                            )

                                    if json_cancel:
                                        _clear_edit_session_state()
                                        st.rerun()

                                    if json_save:
                                        try:
                                            parsed_payload = json.loads(edit_payload_text)
                                            if not isinstance(parsed_payload, dict):
                                                raise ValueError("JSON root must be an object")

                                            if "conditions" in parsed_payload:
                                                new_conditions = parsed_payload.get("conditions", {})
                                                target_account_value = str(
                                                    parsed_payload.get(
                                                        "targetAccount",
                                                        parsed_payload.get("account", target_default),
                                                    )
                                                ).strip()
                                                method_account_value = str(
                                                    parsed_payload.get(
                                                        "methodAccount",
                                                        method_default,
                                                    )
                                                ).strip()
                                                source_value = str(
                                                    parsed_payload.get("source", dialog_rule.get("source", "user"))
                                                ).strip().lower()
                                                confidence_raw = parsed_payload.get(
                                                    "confidence", dialog_rule.get("confidence", 1.0)
                                                )
                                            else:
                                                new_conditions = parsed_payload
                                                target_account_value = target_default
                                                method_account_value = method_default
                                                source_value = str(dialog_rule.get("source", "user")).strip().lower()
                                                confidence_raw = dialog_rule.get("confidence", 1.0)

                                            try:
                                                confidence_value = float(confidence_raw)
                                            except (TypeError, ValueError) as exc:
                                                raise ValueError("`confidence` must be a number") from exc

                                            _save_rule(
                                                target_account_value=target_account_value,
                                                method_account_value=method_account_value,
                                                source_value=source_value,
                                                confidence_value=confidence_value,
                                                new_conditions=new_conditions,
                                            )
                                        except json.JSONDecodeError as e:
                                            st.error(label("rule_invalid_conditions_json", error=str(e)))
                                        except ValueError as e:
                                            st.error(label("rule_invalid_rule_payload", error=str(e)))
                                        except Exception as e:
                                            st.error(label("rule_update_failed", error=str(e)))

                                with tab_form:
                                    with st.form(f"rule_edit_dialog_form_compact_{dialog_rule_id}"):
                                        top_col1, top_col2, top_col3 = st.columns(3)
                                        with top_col1:
                                            edit_scope = st.selectbox(
                                                label("rule_scope"),
                                                ["global", "provider"],
                                                key=edit_scope_key,
                                                format_func=lambda x: (
                                                    label("scope_global")
                                                    if x == "global" else label("scope_provider_specific")
                                                ),
                                            )
                                        with top_col2:
                                            edit_provider_code = ""
                                            if edit_scope == "provider":
                                                provider_codes = [code for code, _ in provider_options if code]
                                                if provider_codes:
                                                    if (
                                                        edit_provider_key not in st.session_state
                                                        or st.session_state[edit_provider_key] not in provider_codes
                                                    ):
                                                        st.session_state[edit_provider_key] = (
                                                            provider_default
                                                            if provider_default in provider_codes
                                                            else provider_codes[0]
                                                        )
                                                    edit_provider_code = st.selectbox(
                                                        label("provider_code"),
                                                        provider_codes,
                                                        key=edit_provider_key,
                                                        format_func=lambda x: next(
                                                            (n for c, n in provider_options if c == x),
                                                            x,
                                                        ),
                                                    )
                                                else:
                                                    if edit_provider_text_key not in st.session_state:
                                                        st.session_state[edit_provider_text_key] = provider_default
                                                    edit_provider_code = st.text_input(
                                                        label("provider_code"),
                                                        key=edit_provider_text_key,
                                                    ).strip().lower()
                                            else:
                                                st.caption(label("scope_global"))
                                        with top_col3:
                                            edit_source = st.selectbox(
                                                label("source"),
                                                ["user", "auto"],
                                                index=0 if str(dialog_rule.get("source", "user")) == "user" else 1,
                                            )

                                        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
                                        with row2_col1:
                                            edit_target_account = st.text_input(
                                                label("target_account"),
                                                value=target_default,
                                            )
                                        with row2_col2:
                                            edit_method_account = st.text_input(
                                                label("method_account"),
                                                value=method_default,
                                            )
                                        with row2_col3:
                                            edit_confidence = st.number_input(
                                                label("confidence"),
                                                min_value=0.0,
                                                max_value=1.0,
                                                value=float(dialog_rule.get("confidence", 1.0)),
                                                step=0.05,
                                            )
                                        with row2_col4:
                                            edit_regexp = st.text_input(
                                                label("regexp_label"),
                                                value=regexp_default,
                                                help=t("regexp_help"),
                                            )

                                        row3_col1, row3_col2, row3_col3 = st.columns(3)
                                        with row3_col1:
                                            edit_peer = st.text_input(
                                                label("peer"),
                                                value=peer_default,
                                                help=t("keywords_help"),
                                            )
                                        with row3_col2:
                                            edit_item = st.text_input(
                                                label("item_rule"),
                                                value=item_default,
                                                help=t("keywords_help"),
                                            )
                                        with row3_col3:
                                            edit_category = st.text_input(
                                                label("category"),
                                                value=category_default,
                                                help=t("keywords_help"),
                                            )

                                        row4_col1, row4_col2, row4_col3 = st.columns(3)
                                        with row4_col1:
                                            edit_tx_type = st.text_input(
                                                label("transaction_type_label"),
                                                value=tx_type_default,
                                                help=t("optional"),
                                            )
                                        with row4_col2:
                                            edit_extra_field = ""
                                            if edit_scope == "provider":
                                                field_options = provider_field_map.get(edit_provider_code, [])
                                                if existing_extra_key and existing_extra_key not in field_options:
                                                    field_options = field_options + [existing_extra_key]
                                                field_options = field_options + ["custom"]
                                                default_field_index = (
                                                    field_options.index(existing_extra_key)
                                                    if existing_extra_key in field_options else len(field_options) - 1
                                                )
                                                selected_extra_field = st.selectbox(
                                                    label("provider_field"),
                                                    field_options,
                                                    index=default_field_index,
                                                )
                                                if selected_extra_field == "custom":
                                                    edit_extra_field = st.text_input(
                                                        label("custom_field_key"),
                                                        value=existing_extra_key,
                                                    ).strip()
                                                else:
                                                    edit_extra_field = selected_extra_field
                                            else:
                                                st.caption(label("optional"))
                                        with row4_col3:
                                            edit_extra_value = ""
                                            if edit_scope == "provider":
                                                edit_extra_value = st.text_input(
                                                    label("provider_field_value"),
                                                    value=existing_extra_value,
                                                    help=t("keywords_help"),
                                                )

                                        form_save_col, form_cancel_col = st.columns(2)
                                        with form_save_col:
                                            form_save = st.form_submit_button(
                                                label("save_rule_changes"),
                                                type="primary",
                                                width="stretch",
                                            )
                                        with form_cancel_col:
                                            form_cancel = st.form_submit_button(
                                                label("cancel_edit_rule"),
                                                width="stretch",
                                            )

                                    if form_cancel:
                                        _clear_edit_session_state()
                                        st.rerun()

                                    if form_save:
                                        try:
                                            new_conditions = {
                                                key: current_conditions.get(key)
                                                for key in internal_preserve_keys
                                                if key in current_conditions
                                            }
                                            if edit_scope == "provider" and edit_provider_code:
                                                new_conditions["provider"] = edit_provider_code
                                            if edit_regexp.strip():
                                                new_conditions["regexp"] = edit_regexp.strip()

                                            edit_peer_tokens = _parse_keyword_list(edit_peer)
                                            edit_item_tokens = _parse_keyword_list(edit_item)
                                            edit_category_tokens = _parse_keyword_list(edit_category)
                                            if edit_peer_tokens:
                                                new_conditions["peer"] = edit_peer_tokens
                                            if edit_item_tokens:
                                                new_conditions["item"] = edit_item_tokens
                                            if edit_category_tokens:
                                                new_conditions["category"] = edit_category_tokens
                                            if edit_tx_type.strip():
                                                new_conditions[tx_type_key] = edit_tx_type.strip()
                                            if edit_extra_field and edit_extra_value.strip():
                                                new_conditions[edit_extra_field] = _parse_keyword_list(edit_extra_value)
                                            for key, value in preserved_extra_items.items():
                                                if key not in new_conditions:
                                                    new_conditions[key] = value

                                            _save_rule(
                                                target_account_value=edit_target_account.strip(),
                                                method_account_value=edit_method_account.strip(),
                                                source_value=str(edit_source or dialog_rule.get("source", "user")).strip().lower(),
                                                confidence_value=float(edit_confidence),
                                                new_conditions=new_conditions,
                                            )
                                        except ValueError as e:
                                            st.error(label("rule_invalid_rule_payload", error=str(e)))
                                        except Exception as e:
                                            st.error(label("rule_update_failed", error=str(e)))

                            _render_rule_edit_dialog()
                        else:
                            st.warning(label("rule_edit_dialog_not_supported"))

                    delete_rule_id = str(st.session_state.get("rule_delete_confirm_id", "")).strip()
                    if delete_rule_id and delete_rule_id in rule_index:
                        delete_rule_name = str(rule_index[delete_rule_id].get("name", delete_rule_id))
                        if hasattr(st, "dialog"):
                            @st.dialog(
                                label("rule_delete_confirm_title"),
                                on_dismiss=lambda: st.session_state.pop("rule_delete_confirm_id", None),
                            )
                            def _render_delete_confirm_dialog():
                                st.warning(label("rule_delete_confirm_text", name=delete_rule_name))
                                confirm_col, cancel_col = st.columns(2)
                                with confirm_col:
                                    confirm_delete = st.button(
                                        label("rule_delete_confirm_button"),
                                        type="primary",
                                        width="stretch",
                                        key=f"confirm_delete_btn_{delete_rule_id}",
                                    )
                                with cancel_col:
                                    cancel_delete = st.button(
                                        label("cancel_edit_rule"),
                                        width="stretch",
                                        key=f"cancel_delete_btn_{delete_rule_id}",
                                    )

                                if cancel_delete:
                                    st.session_state.pop("rule_delete_confirm_id", None)
                                    st.rerun()
                                if confirm_delete:
                                    try:
                                        delete_resp = requests.delete(
                                            get_api_url(f"/rules/{delete_rule_id}"),
                                            timeout=get_api_timeout(),
                                        )
                                        if delete_resp.status_code == 200:
                                            st.session_state.pop("rule_edit_dialog_id", None)
                                            st.session_state.pop("rule_delete_confirm_id", None)
                                            st.success(label("rule_deleted"))
                                            st.rerun()
                                        else:
                                            st.error(delete_resp.text)
                                    except Exception as e:
                                        st.error(str(e))

                            _render_delete_confirm_dialog()
                        else:
                            st.warning(label("rule_edit_dialog_not_supported"))
                else:
                    st.info(label("rule_no_results"))

        except requests.exceptions.ConnectionError:
            st.error(label("backend_not_connected"))
        except Exception as e:
            st.error(str(e))

        # One-click cleanup dialog for auto-generated rules
        if st.session_state.get("rule_cleanup_dialog_open"):
            cleanup_scope = str(st.session_state.get("rule_cleanup_scope", "all")).strip().lower()
            if cleanup_scope not in {"all", "global", "provider"}:
                cleanup_scope = "all"
            cleanup_provider = str(st.session_state.get("rule_cleanup_provider", "all")).strip().lower() or "all"

            provider_name_map = {code: name for code, name in provider_options if code}
            if cleanup_scope == "global":
                cleanup_target_text = label("rule_cleanup_auto_target_global")
            elif cleanup_provider != "all":
                cleanup_target_text = label(
                    "rule_cleanup_auto_target_provider",
                    provider=provider_name_map.get(cleanup_provider, cleanup_provider),
                )
            elif cleanup_scope == "provider":
                cleanup_target_text = label("rule_cleanup_auto_target_provider_only")
            else:
                cleanup_target_text = label("rule_cleanup_auto_target_all")

            if hasattr(st, "dialog"):
                @st.dialog(label("rule_cleanup_auto_dialog_title"))
                def _render_rule_cleanup_dialog():
                    st.warning(label("rule_cleanup_auto_confirm_text", target=cleanup_target_text))
                    confirm_col, cancel_col = st.columns(2)
                    with confirm_col:
                        confirm_cleanup = st.button(
                            label("rule_cleanup_auto_confirm_button"),
                            type="primary",
                            width="stretch",
                            key="rule_cleanup_auto_confirm_btn",
                        )
                    with cancel_col:
                        cancel_cleanup = st.button(
                            label("cancel_edit_rule"),
                            width="stretch",
                            key="rule_cleanup_auto_cancel_btn",
                        )

                    if cancel_cleanup:
                        st.session_state.pop("rule_cleanup_dialog_open", None)
                        st.session_state.pop("rule_cleanup_scope", None)
                        st.session_state.pop("rule_cleanup_provider", None)
                        st.rerun()

                    if confirm_cleanup:
                        cleanup_provider_param = "" if cleanup_provider == "all" else cleanup_provider
                        try:
                            cleanup_resp = requests.post(
                                get_api_url("/rules/cleanup-auto"),
                                params={
                                    "scope": cleanup_scope,
                                    "provider": cleanup_provider_param,
                                },
                                timeout=get_api_timeout(),
                            )
                            if cleanup_resp.status_code == 200:
                                payload = cleanup_resp.json() or {}
                                deleted_count = int(payload.get("deleted", 0))
                                st.session_state.pop("rule_cleanup_dialog_open", None)
                                st.session_state.pop("rule_cleanup_scope", None)
                                st.session_state.pop("rule_cleanup_provider", None)
                                st.success(label("rule_cleanup_auto_success", count=deleted_count))
                                st.rerun()
                            else:
                                st.error(label("rule_cleanup_auto_failed", error=cleanup_resp.text))
                        except Exception as e:
                            st.error(label("rule_cleanup_auto_failed", error=str(e)))

                _render_rule_cleanup_dialog()
            else:
                st.warning(label("rule_cleanup_auto_dialog_not_supported"))

        # Add rule dialog (triggered from Rules Table header button)
        if st.session_state.get("rule_add_dialog_open") and hasattr(st, "dialog"):
            @st.dialog(label("rule_add_dialog_title"))
            def _render_rule_add_dialog():
                add_scope_key = "rule_add_scope"
                add_provider_key = "rule_add_provider"
                add_provider_text_key = "rule_add_provider_text"

                if add_scope_key not in st.session_state:
                    st.session_state[add_scope_key] = "global"
                scope = st.selectbox(
                    label("rule_scope"),
                    ["global", "provider"],
                    key=add_scope_key,
                    format_func=lambda x: (
                        label("scope_global") if x == "global" else label("scope_provider_specific")
                    ),
                )

                provider_code = ""
                if scope == "provider":
                    provider_codes = [code for code, _ in provider_options if code]
                    if provider_codes:
                        if (
                            add_provider_key not in st.session_state
                            or st.session_state[add_provider_key] not in provider_codes
                        ):
                            st.session_state[add_provider_key] = provider_codes[0]
                        provider_code = st.selectbox(
                            label("provider_code"),
                            provider_codes,
                            key=add_provider_key,
                            format_func=lambda x: next((n for c, n in provider_options if c == x), x),
                        )
                    else:
                        provider_code = st.text_input(
                            label("provider_code"),
                            key=add_provider_text_key,
                        ).strip().lower()

                with st.form("create_rule_dialog_form"):
                    st.markdown(f"**{label('deg_match_conditions')}**")
                    regexp = st.text_input(
                        label("regexp_label"),
                        help=t("regexp_help"),
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        peer = st.text_input(label("peer"), help=t("keywords_help"))
                        category = st.text_input(label("category"), help=t("keywords_help"))
                    with col2:
                        item = st.text_input(label("item_rule"), help=t("keywords_help"))
                        tx_type = st.text_input(label("transaction_type_label"), help=t("optional"))

                    extra_field = ""
                    extra_value = ""
                    if scope == "provider":
                        field_options = provider_field_map.get(provider_code, [])
                        field_options = field_options + ["custom"]
                        extra_field = st.selectbox(label("provider_field"), field_options)
                        if extra_field == "custom":
                            extra_field = st.text_input(label("custom_field_key")).strip()
                        extra_value = st.text_input(label("provider_field_value"), help=t("keywords_help"))

                    account_col1, account_col2 = st.columns(2)
                    with account_col1:
                        account = st.text_input(label("target_account"))
                    with account_col2:
                        method_account = st.text_input(label("method_account"))
                    confidence = st.slider(
                        label("confidence"),
                        min_value=0.0,
                        max_value=1.0,
                        value=1.0,
                        step=0.1,
                    )

                    create_col, cancel_col = st.columns(2)
                    with create_col:
                        submit_create = st.form_submit_button(
                            label("create_rule"),
                            type="primary",
                            width="stretch",
                        )
                    with cancel_col:
                        cancel_create = st.form_submit_button(
                            label("cancel_edit_rule"),
                            width="stretch",
                        )

                if cancel_create:
                    st.session_state.pop("rule_add_dialog_open", None)
                    st.session_state.pop(add_scope_key, None)
                    st.session_state.pop(add_provider_key, None)
                    st.session_state.pop(add_provider_text_key, None)
                    st.rerun()

                if submit_create:
                    conditions = {}
                    if scope == "provider" and provider_code:
                        conditions["provider"] = provider_code
                    if regexp.strip():
                        conditions["regexp"] = regexp.strip()

                    peer_tokens = _parse_keyword_list(peer)
                    item_tokens = _parse_keyword_list(item)
                    category_tokens = _parse_keyword_list(category)
                    if peer_tokens:
                        conditions["peer"] = peer_tokens
                    if item_tokens:
                        conditions["item"] = item_tokens
                    if category_tokens:
                        conditions["category"] = category_tokens
                    if tx_type.strip():
                        conditions["transactionType"] = tx_type.strip()
                    if extra_field and extra_value.strip():
                        conditions[extra_field] = _parse_keyword_list(extra_value)
                    if method_account.strip():
                        conditions["methodAccount"] = method_account.strip()

                    account_value = account.strip()
                    method_value = method_account.strip()
                    if account_value:
                        conditions.pop("_deg_only", None)
                        conditions.pop("_deg_has_target", None)
                    elif method_value:
                        conditions["_deg_only"] = True
                        conditions["_deg_has_target"] = False
                    else:
                        st.error(label("rule_target_or_method_required"))
                        return

                    payload = {
                        "name": f"rule-{uuid.uuid4().hex[:8]}",
                        "conditions": conditions,
                        "account": account_value or method_value,
                        "confidence": float(confidence),
                        "source": "user",
                    }
                    try:
                        create_resp = requests.post(
                            get_api_url("/rules"),
                            json=payload,
                            timeout=get_api_timeout(),
                        )
                        if create_resp.status_code == 200:
                            st.session_state.pop("rule_add_dialog_open", None)
                            st.session_state.pop(add_scope_key, None)
                            st.session_state.pop(add_provider_key, None)
                            st.session_state.pop(add_provider_text_key, None)
                            st.success(label("rule_created"))
                            st.rerun()
                        else:
                            st.error(create_resp.text)
                    except Exception as e:
                        st.error(str(e))

            _render_rule_add_dialog()
        elif st.session_state.get("rule_add_dialog_open"):
            st.warning(label("rule_edit_dialog_not_supported"))

        # Import / Export DEG YAML
        st.markdown("---")
        st.subheader(label("deg_yaml_import_export_title"))

        io_provider_codes = [code for code, _ in provider_catalog]
        default_io_provider = io_provider_codes[0] if io_provider_codes else "alipay"

        io_col1, io_col2, io_col3 = st.columns(3)
        with io_col1:
            io_provider = st.selectbox(
                label("deg_yaml_provider"),
                io_provider_codes if io_provider_codes else [default_io_provider],
                format_func=lambda x: next((n for c, n in provider_catalog if c == x), x),
                key="deg_yaml_provider_select",
            )
        with io_col2:
            st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
            if st.button(label("deg_yaml_import_open_modal"), type="primary", width="stretch"):
                _clear_ai_dialog_state()
                st.session_state.rule_import_dialog_open = True
                st.session_state.rule_import_dialog_provider = io_provider
                st.rerun()
        with io_col3:
            st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)
            if st.button(label("deg_yaml_export_button"), width="stretch"):
                try:
                    export_resp = requests.get(
                        get_api_url("/rules/export-deg"),
                        params={"provider": io_provider},
                        timeout=get_api_timeout(),
                    )
                    if export_resp.status_code == 200:
                        st.session_state.deg_yaml_export_provider = io_provider
                        st.session_state.deg_yaml_export_content = export_resp.text
                    else:
                        st.error(label("deg_yaml_export_failed", error=export_resp.text))
                except Exception as e:
                    st.error(label("deg_yaml_export_failed", error=str(e)))

        if st.session_state.get("rule_import_dialog_open") and hasattr(st, "dialog"):
            @st.dialog(label("deg_yaml_import_dialog_title"))
            def _render_import_dialog():
                with st.form("deg_yaml_import_form_dialog"):
                    dialog_provider = st.selectbox(
                        label("deg_yaml_provider"),
                        io_provider_codes if io_provider_codes else [default_io_provider],
                        index=(
                            io_provider_codes.index(st.session_state.get("rule_import_dialog_provider", default_io_provider))
                            if st.session_state.get("rule_import_dialog_provider", default_io_provider) in io_provider_codes
                            else 0
                        ) if io_provider_codes else 0,
                        format_func=lambda x: next((n for c, n in provider_catalog if c == x), x),
                    )
                    dialog_mode = st.selectbox(
                        label("deg_yaml_import_mode"),
                        ["replace", "append"],
                        format_func=lambda m: (
                            label("deg_yaml_mode_replace")
                            if m == "replace" else label("deg_yaml_mode_append")
                        ),
                    )
                    dialog_uploaded_yaml = st.file_uploader(
                        label("deg_yaml_upload_file"),
                        type=["yaml", "yml", "txt"],
                        help=label("deg_yaml_upload_file_help"),
                    )
                    dialog_yaml_text = st.text_area(
                        label("deg_yaml_text_input"),
                        height=140,
                        help=label("deg_yaml_text_input_help"),
                    )

                    submit_col, cancel_col = st.columns(2)
                    with submit_col:
                        submit_import = st.form_submit_button(
                            label("deg_yaml_import_button"),
                            type="primary",
                            width="stretch",
                        )
                    with cancel_col:
                        cancel_import = st.form_submit_button(
                            label("cancel_edit_rule"),
                            width="stretch",
                        )

                if cancel_import:
                    st.session_state.pop("rule_import_dialog_open", None)
                    st.rerun()

                if submit_import:
                    try:
                        if not dialog_provider:
                            st.error(label("deg_yaml_provider_required"))
                            return
                        if dialog_uploaded_yaml is None and not str(dialog_yaml_text or "").strip():
                            st.error(label("deg_yaml_empty_input"))
                            return

                        data = {
                            "provider": dialog_provider,
                            "mode": dialog_mode,
                            "yaml_text": "" if dialog_uploaded_yaml is not None else str(dialog_yaml_text or ""),
                        }
                        files = None
                        if dialog_uploaded_yaml is not None:
                            files = {
                                "yaml_file": (
                                    dialog_uploaded_yaml.name or f"{dialog_provider}.yaml",
                                    dialog_uploaded_yaml.getvalue(),
                                    "application/x-yaml",
                                )
                            }

                        import_resp = requests.post(
                            get_api_url("/rules/import-deg"),
                            data=data,
                            files=files,
                            timeout=get_api_timeout(),
                        )
                        if import_resp.status_code == 200:
                            result = import_resp.json()
                            st.session_state.pop("rule_import_dialog_open", None)
                            st.success(
                                label(
                                    "deg_yaml_import_success",
                                    provider=result.get("provider", dialog_provider),
                                    created=result.get("created", 0),
                                    updated=result.get("updated", 0),
                                    deleted=result.get("deleted_provider_rules", 0),
                                    skipped=result.get("skipped", 0),
                                )
                            )
                            st.rerun()
                        else:
                            st.error(label("deg_yaml_import_failed", error=import_resp.text))
                    except Exception as e:
                        st.error(label("deg_yaml_import_failed", error=str(e)))

            _render_import_dialog()
        elif st.session_state.get("rule_import_dialog_open"):
            st.warning(label("rule_edit_dialog_not_supported"))

        export_content = st.session_state.get("deg_yaml_export_content", "")
        export_provider = st.session_state.get("deg_yaml_export_provider", io_provider)
        if export_content:
            st.download_button(
                label("deg_yaml_download_button"),
                data=export_content,
                file_name=f"{export_provider}.yaml",
                mime="application/x-yaml",
                width="stretch",
                key=f"download_deg_yaml_{export_provider}",
            )

    # System Information
    with tab4:
        st.subheader(label("system_info_title"))

        # Backend status
        st.markdown(f"### {label('backend_status')}")

        try:
            response = requests.get(get_health_check_url(), timeout=2)

            if response.status_code == 200:
                st.success(label("backend_running"))
            else:
                st.error(label("backend_abnormal"))
        except requests.exceptions.ConnectionError:
            st.error(label("backend_not_connected"))
        except Exception as e:
            st.error(label("backend_check_failed", error=str(e)))

        # DEG status
        st.markdown(f"### {label('deg_status')}")

        try:
            response = requests.get(get_api_url("/generate/check"), timeout=2)

            if response.status_code == 200:
                result = response.json()
                if result["installed"]:
                    st.success(label("deg_installed", message=result['message']))
                    if result.get("version"):
                        st.caption(label("deg_version", version=result["version"]))
                else:
                    st.warning(label("deg_warning", message=result['message']))
                    st.code(result.get("install_command", "double-entry-generator version"), language="bash")
                    if result.get("download_url"):
                        st.markdown(label("deg_download", url=result["download_url"]))
        except Exception as e:
            st.error(label("backend_check_failed", error=str(e)))

        # Database information
        st.markdown(f"### {label('database_info')}")

        st.info(f"""
        - **{t('db_path')}**: {t('db_path_value')}
        - **{t('db_type')}**: {t('db_type_value')}
        - **{t('db_status')}**: {t('db_status_value')}
        """)

        # Version information
        st.markdown(f"### {label('version_info')}")
        st.info(f"""
        - **{t('beancountpilot')}**: v0.1.0
        - **{t('python')}**: 3.11+
        - **{t('streamlit')}**: {t('latest')}
        - **{t('fastapi')}**: {t('latest')}
        """)

    # DEG Mapping
    with tab5:
        lang = get_current_language()
        st.subheader(label("deg_provider_mapping_title"))
        st.info(label("deg_provider_mapping_official_note"))

        mapping_col1, mapping_col2 = st.columns([1, 1])
        with mapping_col1:
            reload_mapping_clicked = st.button(
                label("reload_deg_provider_mapping"),
                width="stretch",
            )
        with mapping_col2:
            save_mapping_clicked = st.button(
                label("save_deg_provider_mapping"),
                type="primary",
                width="stretch",
            )

        mapping_result = st.session_state.get("deg_provider_mapping_result")
        if mapping_result is None or "deg_provider_mapping_text" not in st.session_state or reload_mapping_clicked:
            try:
                response = requests.get(get_api_url("/generate/provider-mapping"), timeout=3)
                if response.status_code == 200:
                    mapping_result = response.json()
                    st.session_state.deg_provider_mapping_result = mapping_result
                    st.session_state.deg_provider_mapping_text = _render_deg_mapping_text(
                        mapping_result.get("user_overrides", {})
                    )
                    st.session_state.deg_custom_providers = _normalize_custom_provider_rows(
                        mapping_result.get("custom_providers")
                    )
                else:
                    st.error(label("deg_provider_mapping_load_failed", error=response.text))
            except Exception as e:
                st.error(label("deg_provider_mapping_load_failed", error=str(e)))

        mapping_result = st.session_state.get("deg_provider_mapping_result", {})
        storage = mapping_result.get("storage", {})
        if storage:
            st.caption(
                label(
                    "deg_mapping_storage",
                    official=storage.get("official_catalog", "config/deg.yaml"),
                    mappings=storage.get("mappings", "-"),
                    custom=storage.get("custom_providers", "-"),
                )
            )

        custom_providers = _normalize_custom_provider_rows(
            st.session_state.get("deg_custom_providers")
        )
        st.session_state.deg_custom_providers = custom_providers

        unknown_targets = mapping_result.get("unknown_targets", [])
        if unknown_targets:
            st.warning(
                label(
                    "deg_provider_mapping_unknown_targets",
                    targets=", ".join(unknown_targets),
                )
            )

        st.markdown(f"### {label('deg_official_provider_catalog')}")
        official = mapping_result.get("official_providers", [])
        if official:
            official_rows = [
                {
                    label("deg_mapping_col_code"): item.get("code", ""),
                    label("deg_mapping_col_translation"): _provider_display_name(item, lang),
                }
                for item in official
            ]
            official_df = pd.DataFrame(official_rows)
            st.dataframe(
                official_df,
                width="stretch",
                hide_index=True,
            )

        st.markdown(f"### {label('deg_custom_provider_catalog')}")
        if custom_providers:
            custom_rows = [
                {
                    label("deg_mapping_col_code"): item.get("code", ""),
                    label("deg_mapping_col_translation"): _provider_display_name(item, lang),
                }
                for item in custom_providers
            ]
            custom_df = pd.DataFrame(custom_rows)
            st.dataframe(custom_df, width="stretch", hide_index=True)
        else:
            st.caption(label("deg_no_custom_providers"))

        st.markdown(f"### {label('deg_current_mapping_preview')}")
        details = mapping_result.get("mapping_details", [])
        if details:
            preview_df = pd.DataFrame(details)
            preview_df["target_display_name"] = preview_df.apply(
                lambda row: _provider_display_name(
                    {
                        "i18n_key": row.get("target_i18n_key", ""),
                        "names": row.get("target_names", {}) if isinstance(row.get("target_names"), dict) else {},
                        "name_en": row.get("target_name_en", ""),
                        "name_zh": row.get("target_name_zh", ""),
                        "code": row.get("target", ""),
                    },
                    lang,
                ),
                axis=1,
            )
            preview_df["is_official_target"] = preview_df["is_official_target"].apply(
                lambda v: label("deg_mapping_target_official") if bool(v) else label("deg_mapping_target_custom")
            )
            preview_df = preview_df.rename(
                columns={
                    "source": label("deg_mapping_col_source"),
                    "target": label("deg_mapping_col_target"),
                    "target_display_name": label("deg_mapping_col_translation"),
                    "is_official_target": label("deg_mapping_col_target_type"),
                }
            )
            preview_df = preview_df[
                [
                    label("deg_mapping_col_source"),
                    label("deg_mapping_col_target"),
                    label("deg_mapping_col_translation"),
                    label("deg_mapping_col_target_type"),
                ]
            ]
            st.dataframe(preview_df, width="stretch", hide_index=True)

        st.markdown(f"### {label('deg_add_mapping_entry')}")
        add_col1, add_col2 = st.columns([1.2, 1])
        with add_col1:
            add_source = st.text_input(
                label("deg_add_mapping_source"),
                key="deg_add_mapping_source",
            ).strip().lower()
        with add_col2:
            add_target_kind = st.selectbox(
                label("deg_add_target_kind"),
                ["official", "custom"],
                key="deg_add_target_kind",
                format_func=lambda x: (
                    label("deg_target_kind_official")
                    if x == "official" else label("deg_target_kind_custom")
                ),
            )

        selected_target_code = ""
        custom_code = ""
        custom_name_en = ""
        custom_name_zh = ""

        if add_target_kind == "official":
            official_options = mapping_result.get("official_providers", [])
            official_codes = [item["code"] for item in official_options]
            if official_codes:
                selected_target_code = st.selectbox(
                    label("deg_select_official_provider"),
                    official_codes,
                    format_func=lambda code: next(
                        (
                            f"{code} ({_provider_display_name(item, lang)})"
                            for item in official_options
                            if item.get("code") == code
                        ),
                        code,
                    ),
                    key="deg_official_target_code",
                )
        else:
            row1, row2, row3 = st.columns(3)
            with row1:
                custom_code = st.text_input(
                    label("deg_custom_provider_code"),
                    key="deg_custom_provider_code",
                ).strip().lower()
            with row2:
                custom_name_en = st.text_input(
                    label("deg_custom_provider_name_en"),
                    key="deg_custom_provider_name_en",
                ).strip()
            with row3:
                custom_name_zh = st.text_input(
                    label("deg_custom_provider_name_zh"),
                    key="deg_custom_provider_name_zh",
                ).strip()
            selected_target_code = custom_code

        if st.button(label("deg_add_mapping_row"), width="stretch"):
            try:
                if not add_source:
                    raise ValueError("source is required")
                if not selected_target_code:
                    raise ValueError("target code is required")

                mapping = _parse_deg_mapping_text(
                    st.session_state.get("deg_provider_mapping_text", "")
                )
                mapping[add_source] = selected_target_code
                st.session_state.deg_provider_mapping_text = _render_deg_mapping_text(mapping)

                if add_target_kind == "custom":
                    updated_custom = {
                        item["code"]: {
                            "code": item["code"],
                            "name_en": item.get("name_en", ""),
                            "name_zh": item.get("name_zh", ""),
                        }
                        for item in st.session_state.get("deg_custom_providers", [])
                    }
                    updated_custom[selected_target_code] = {
                        "code": selected_target_code,
                        "name_en": custom_name_en,
                        "name_zh": custom_name_zh,
                    }
                    st.session_state.deg_custom_providers = _normalize_custom_provider_rows(
                        list(updated_custom.values())
                    )

                st.success(label("deg_mapping_row_added"))
                st.rerun()
            except Exception as e:
                st.error(label("deg_mapping_add_failed", error=str(e)))

        st.text_area(
            label("deg_provider_mapping_editor"),
            key="deg_provider_mapping_text",
            height=220,
            help=label("deg_provider_mapping_help"),
        )

        if save_mapping_clicked:
            try:
                parsed = _parse_deg_mapping_text(
                    st.session_state.get("deg_provider_mapping_text", "")
                )
                response = requests.put(
                    get_api_url("/generate/provider-mapping"),
                    json={
                        "mappings": parsed,
                        "custom_providers": st.session_state.get("deg_custom_providers", []),
                    },
                    timeout=get_api_timeout(),
                )
                if response.status_code == 200:
                    result = response.json()
                    st.session_state.deg_provider_mapping_result = result
                    st.session_state.deg_provider_mapping_text = _render_deg_mapping_text(
                        result.get("user_overrides", {})
                    )
                    st.session_state.deg_custom_providers = _normalize_custom_provider_rows(
                        result.get("custom_providers")
                    )
                    unknown_targets = result.get("unknown_targets", [])
                    if unknown_targets:
                        st.warning(
                            label(
                                "deg_provider_mapping_unknown_targets",
                                targets=", ".join(unknown_targets),
                            )
                        )
                    st.success(label("deg_provider_mapping_saved"))
                    st.rerun()
                else:
                    st.error(label("deg_provider_mapping_save_failed", error=response.text))
            except Exception as e:
                st.error(label("deg_provider_mapping_save_failed", error=str(e)))


if __name__ == "__main__":
    init_i18n()
    render()
