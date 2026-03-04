"""
Settings page
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
from frontend.config import get_api_url, get_health_check_url, get_api_timeout
from src.db.init import DEFAULT_LEDGER_FILES


LEDGER_FILES = [
    "assets.bean",
    "equity.bean",
    "expenses.bean",
    "income.bean",
    "liabilities.bean",
]

AI_PROVIDER_ORDER = ["deepseek", "openai", "ollama", "custom"]

DEFAULT_AI_PROVIDER_CONFIG = {
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


def _normalize_ai_providers(providers: dict | None) -> dict:
    """Normalize provider config map for UI editing."""
    normalized = {}
    providers = providers or {}
    for name in AI_PROVIDER_ORDER:
        defaults = DEFAULT_AI_PROVIDER_CONFIG[name]
        current = providers.get(name, {})
        normalized[name] = {
            "api_base": str(current.get("api_base", defaults["api_base"])),
            "api_key": str(current.get("api_key", defaults["api_key"])),
            "model": str(current.get("model", defaults["model"])),
            "temperature": float(current.get("temperature", defaults["temperature"])),
            "timeout": int(current.get("timeout", defaults["timeout"])),
        }
    return normalized


def _load_ai_config() -> tuple[str, dict]:
    """Load AI config from backend; fallback to defaults on failure."""
    default_provider = "deepseek"
    providers = _normalize_ai_providers(None)
    try:
        timeout = min(get_api_timeout(), 3)
        response = requests.get(get_api_url("/ai/config"), timeout=timeout)
        if response.status_code != 200:
            return default_provider, providers

        data = response.json()
        default_provider = data.get("default_provider", default_provider)
        providers = _normalize_ai_providers(data.get("providers"))

        if default_provider not in AI_PROVIDER_ORDER:
            default_provider = "deepseek"
    except Exception:
        return default_provider, providers

    return default_provider, providers


def _decode_uploaded_file(content: bytes) -> str:
    """Decode uploaded text file with common encodings."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unsupported file encoding. Please upload UTF-8 or GBK text.")


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
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            label("ai_settings"),
            label("chart_of_accounts_config"),
            label("rule_management"),
            label("system_info"),
        ]
    )

    # AI Settings
    with tab1:
        st.subheader(label("ai_provider_config"))

        if "ai_config_loaded" not in st.session_state:
            default_provider, providers = _load_ai_config()
            st.session_state.ai_providers = providers
            st.session_state.provider = default_provider
            st.session_state.ai_config_loaded = True

        providers = _normalize_ai_providers(st.session_state.get("ai_providers"))
        current_provider = st.session_state.get("provider", "deepseek")
        if current_provider not in AI_PROVIDER_ORDER:
            current_provider = "deepseek"

        provider_name_map = {
            "deepseek": "DeepSeek",
            "openai": "OpenAI",
            "ollama": "Ollama",
            "custom": "Custom",
        }

        with st.form("ai_provider_config_form"):
            provider_index = AI_PROVIDER_ORDER.index(current_provider)
            active_provider = st.selectbox(
                label("active_ai_provider"),
                AI_PROVIDER_ORDER,
                index=provider_index,
                format_func=lambda x: provider_name_map.get(x, x),
            )
            st.caption(label("active_ai_provider_help"))

            st.markdown("---")
            st.subheader(label("multi_provider_config"))

            edited_providers = {}

            for provider_name in AI_PROVIDER_ORDER:
                cfg = providers[provider_name]
                title = f"{label('provider_settings')}: {provider_name_map.get(provider_name, provider_name)}"

                with st.expander(title, expanded=(provider_name == active_provider)):
                    api_base = st.text_input(
                        label("api_base"),
                        value=cfg["api_base"],
                        key=f"ai_cfg_{provider_name}_api_base",
                    )
                    api_key = st.text_input(
                        label("api_key"),
                        value=cfg["api_key"],
                        type="password",
                        key=f"ai_cfg_{provider_name}_api_key",
                    )

                    if provider_name == "deepseek":
                        model_options = ["deepseek-chat", "deepseek-coder"]
                        if cfg["model"] and cfg["model"] not in model_options:
                            model_options = [cfg["model"]] + model_options
                        model = st.selectbox(
                            label("model"),
                            model_options,
                            index=model_options.index(cfg["model"]) if cfg["model"] in model_options else 0,
                            key=f"ai_cfg_{provider_name}_model",
                        )
                    elif provider_name == "openai":
                        model_options = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
                        if cfg["model"] and cfg["model"] not in model_options:
                            model_options = [cfg["model"]] + model_options
                        model = st.selectbox(
                            label("model"),
                            model_options,
                            index=model_options.index(cfg["model"]) if cfg["model"] in model_options else 0,
                            key=f"ai_cfg_{provider_name}_model",
                        )
                    else:
                        model = st.text_input(
                            label("model"),
                            value=cfg["model"],
                            key=f"ai_cfg_{provider_name}_model",
                        )

                    temperature = st.slider(
                        label("temperature"),
                        min_value=0.0,
                        max_value=1.0,
                        value=float(cfg["temperature"]),
                        step=0.1,
                        key=f"ai_cfg_{provider_name}_temperature",
                        help=t("temperature_help"),
                    )

                    timeout = st.number_input(
                        label("timeout"),
                        min_value=10,
                        max_value=600,
                        value=int(cfg["timeout"]),
                        key=f"ai_cfg_{provider_name}_timeout",
                    )

                    edited_providers[provider_name] = {
                        "api_base": api_base.strip(),
                        "api_key": api_key.strip(),
                        "model": model.strip(),
                        "temperature": float(temperature),
                        "timeout": int(timeout),
                    }

            save_clicked = st.form_submit_button(
                label("save_config"),
                type="primary",
                use_container_width=True,
            )

        if save_clicked:
            payload = {
                "default_provider": active_provider,
                "providers": edited_providers,
            }
            try:
                response = requests.put(
                    get_api_url("/ai/config"),
                    json=payload,
                    timeout=get_api_timeout(),
                )
                if response.status_code == 200:
                    st.session_state.ai_providers = edited_providers
                    st.session_state.provider = active_provider
                    active_cfg = edited_providers[active_provider]
                    st.session_state.api_key = active_cfg.get("api_key", "")
                    st.session_state.api_base = active_cfg.get("api_base", "")
                    st.session_state.model = active_cfg.get("model", "")
                    st.session_state.temperature = active_cfg.get("temperature", 0.3)
                    st.session_state.timeout = active_cfg.get("timeout", 30)
                    st.success(label("config_saved"))
                else:
                    st.error(label("config_save_failed", error=response.text))
            except requests.exceptions.ConnectionError:
                st.error(label("backend_not_connected"))
            except Exception as e:
                st.error(label("config_save_failed", error=str(e)))

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
            import requests

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
            import requests

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


if __name__ == "__main__":
    init_i18n()
    render()
