"""
Settings page
"""

import sys
import uuid
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
            add_clicked = st.button(label("add_profile"), use_container_width=True)

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

        with st.form("ai_profiles_form"):
            active_profile_id = st.selectbox(
                label("active_ai_provider"),
                profile_options,
                index=profile_options.index(current_profile_id),
                format_func=format_profile,
            )
            st.caption(label("active_ai_provider_help"))

            st.markdown("---")
            st.subheader(label("multi_provider_config"))

            edited_profiles = []
            delete_profile_id = None
            for profile_id in profile_options:
                profile = profile_by_id[profile_id]
                title = format_profile(profile_id)

                with st.expander(title, expanded=(profile_id == active_profile_id)):
                    edited_name = st.text_input(
                        label("profile_name"),
                        value=profile["name"],
                        key=f"ai_profile_{profile_id}_name",
                    )
                    edited_type = st.selectbox(
                        label("profile_type"),
                        AI_PROVIDER_TYPES,
                        index=AI_PROVIDER_TYPES.index(profile["provider"])
                        if profile["provider"] in AI_PROVIDER_TYPES else AI_PROVIDER_TYPES.index("custom"),
                        key=f"ai_profile_{profile_id}_type",
                        format_func=_provider_label,
                    )

                    type_defaults = DEFAULT_AI_PROFILE_TEMPLATE[edited_type]
                    edited_api_base = st.text_input(
                        label("api_base"),
                        value=profile["api_base"] or type_defaults["api_base"],
                        key=f"ai_profile_{profile_id}_api_base",
                    )
                    edited_api_key = st.text_input(
                        label("api_key"),
                        value=profile["api_key"],
                        type="password",
                        key=f"ai_profile_{profile_id}_api_key",
                    )
                    edited_model = st.text_input(
                        label("model"),
                        value=profile["model"] or type_defaults["model"],
                        key=f"ai_profile_{profile_id}_model",
                    )
                    edited_temperature = st.slider(
                        label("temperature"),
                        min_value=0.0,
                        max_value=1.0,
                        value=float(profile["temperature"]),
                        step=0.1,
                        key=f"ai_profile_{profile_id}_temperature",
                        help=t("temperature_help"),
                    )
                    edited_timeout = st.number_input(
                        label("timeout"),
                        min_value=10,
                        max_value=600,
                        value=int(profile["timeout"]),
                        key=f"ai_profile_{profile_id}_timeout",
                    )

                    edited_profiles.append(
                        {
                            "id": profile_id,
                            "name": edited_name.strip() or f"{_provider_label(edited_type)} Profile",
                            "provider": edited_type,
                            "api_base": edited_api_base.strip(),
                            "api_key": edited_api_key.strip(),
                            "model": edited_model.strip(),
                            "temperature": float(edited_temperature),
                            "timeout": int(edited_timeout),
                        }
                    )

                    if st.form_submit_button(
                        label("delete_profile"),
                        key=f"delete_profile_btn_{profile_id}",
                        use_container_width=True,
                    ):
                        delete_profile_id = profile_id

            save_clicked = st.form_submit_button(
                label("save_config"),
                type="primary",
                use_container_width=True,
            )

        if delete_profile_id:
            remaining_profiles = [
                profile for profile in edited_profiles
                if profile["id"] != delete_profile_id
            ]
            if not remaining_profiles:
                _show_toast_warning(label("at_least_one_profile"))
            else:
                selected_profile_id = active_profile_id
                if selected_profile_id == delete_profile_id:
                    selected_profile_id = remaining_profiles[0]["id"]
                _persist_ai_profiles(remaining_profiles, selected_profile_id)
                st.rerun()

        if save_clicked and not delete_profile_id:
            if not edited_profiles:
                _show_toast_warning(label("at_least_one_profile"))
            else:
                _persist_ai_profiles(edited_profiles, active_profile_id)

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
            validate_clicked = st.button(label("validate_chart"), use_container_width=True)

        with action_col2:
            sync_from_ledger_clicked = st.button(
                label("sync_from_ledger_files"), use_container_width=True
            )

        with action_col3:
            sync_to_ledger_clicked = st.button(
                label("sync_to_ledger_files"), use_container_width=True
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
                use_container_width=True,
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
            if st.button(label("save_ledger_file"), use_container_width=True):
                selected_ledger_path.write_text(st.session_state.get(editor_key, ""), encoding="utf-8")
                synced_accounts = _sync_chart_from_ledger_files(ledger_dir)
                st.session_state.chart_of_accounts = "\n".join(synced_accounts)
                st.success(label("ledger_file_saved", filename=selected_ledger_file))

        with action_col2:
            if st.button(label("reload_ledger_file"), use_container_width=True):
                st.session_state[editor_key] = selected_ledger_path.read_text(encoding="utf-8")
                st.rerun()

        uploaded_ledger_file = st.file_uploader(
            label("import_ledger_file"),
            type=["bean", "beancount", "txt"],
            key=f"ledger_upload__{selected_ledger_file}",
            help=label("import_ledger_file_help"),
        )
        if uploaded_ledger_file is not None and st.button(
            label("import_to_selected_file"), use_container_width=True
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

        # Rule list
        try:
            response = requests.get(get_api_url("/rules"), timeout=get_api_timeout())

            if response.status_code == 200:
                rules = response.json()

                if rules:
                    # Display rule list
                    for rule in rules:
                        with st.expander(rule["name"]):
                            st.write(f"**Account**: {rule['account']}")
                            st.write(f"**Confidence**: {rule['confidence']}")
                            st.write(f"**Conditions**: {rule['conditions']}")
                            st.write(f"**Source**: {rule['source']}")
                else:
                    st.info(label("no_rules"))
            else:
                st.warning(label("failed_load_rules"))

        except requests.exceptions.ConnectionError:
            st.error(label("backend_not_connected"))

        # Create new rule
        st.markdown("---")
        st.subheader(label("create_new_rule"))

        with st.form("create_rule"):
            rule_name = st.text_input(label("rule_name"))

            st.markdown(f"**{label('conditions')}**")

            col1, col2 = st.columns(2)

            with col1:
                peer = st.text_input(label("peer"))
                category = st.text_input(label("category"))

            with col2:
                item = st.text_input(label("item_rule"))

            account = st.text_input(label("target_account"))

            confidence = st.slider(
                label("confidence"),
                min_value=0.0,
                max_value=1.0,
                value=1.0,
                step=0.1,
            )

            if st.form_submit_button(label("create_rule"), type="primary", use_container_width=True):
                st.success(label("rule_created"))

        # Export rules
        st.markdown("---")
        st.subheader(label("export_rules"))

        if st.button(label("export_format"), use_container_width=True):
            st.info(label("rules_exported"))

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
                use_container_width=True,
            )
        with mapping_col2:
            save_mapping_clicked = st.button(
                label("save_deg_provider_mapping"),
                type="primary",
                use_container_width=True,
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
                use_container_width=True,
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
            st.dataframe(custom_df, use_container_width=True, hide_index=True)
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
            st.dataframe(preview_df, use_container_width=True, hide_index=True)

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

        if st.button(label("deg_add_mapping_row"), use_container_width=True):
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
