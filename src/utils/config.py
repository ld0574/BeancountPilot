"""
Configuration loading module
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


# Configuration file paths
CONFIG_DIR = Path.home() / ".beancountpilot" / "config"
AI_CONFIG_FILE = CONFIG_DIR / "ai.yaml"
DATABASE_CONFIG_FILE = CONFIG_DIR / "database.yaml"
APPLICATION_CONFIG_FILE = CONFIG_DIR / "application.yaml"
PROVIDERS_CONFIG_DIR = CONFIG_DIR / "providers"


def ensure_config_dir():
    """Ensure configuration directory exists"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def ensure_providers_dir():
    """Ensure providers configuration directory exists"""
    ensure_config_dir()
    PROVIDERS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_yaml_config(file_path: Path) -> Dict[str, Any]:
    """
    Load YAML configuration file

    Args:
        file_path: Configuration file path

    Returns:
        Configuration dictionary
    """
    if not file_path.exists():
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml_config(file_path: Path, config: Dict[str, Any]) -> None:
    """
    Save YAML configuration file

    Args:
        file_path: Configuration file path
        config: Configuration dictionary
    """
    ensure_config_dir()

    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)


def save_provider_config(provider: str, config: Dict[str, Any]) -> None:
    """
    Save provider-specific configuration file

    Args:
        provider: Provider name
        config: Configuration dictionary
    """
    ensure_providers_dir()
    file_path = PROVIDERS_CONFIG_DIR / f"{provider}.yaml"
    save_yaml_config(file_path, config)


def load_config() -> Dict[str, Any]:
    """
    Load all configurations

    Returns:
        Merged configuration dictionary
    """
    config = {
        "ai": load_yaml_config(AI_CONFIG_FILE),
        "database": load_yaml_config(DATABASE_CONFIG_FILE),
        "application": load_yaml_config(APPLICATION_CONFIG_FILE),
        "providers": load_providers_config(),
    }

    default_config = _get_default_config()
    for section, value in default_config.items():
        config.setdefault(section, value)
        if isinstance(value, dict) and isinstance(config.get(section), dict):
            for key, default_value in value.items():
                config[section].setdefault(key, default_value)

    return config


def load_providers_config() -> Dict[str, Any]:
    """
    Load provider-specific configuration files

    Returns:
        Mapping of provider name to configuration
    """
    if not PROVIDERS_CONFIG_DIR.exists():
        return {}

    providers = {}
    for file_path in PROVIDERS_CONFIG_DIR.glob("*.yaml"):
        providers[file_path.stem] = load_yaml_config(file_path)

    return providers


def get_config(key: str, default: Any = None) -> Any:
    """
    Get configuration value

    Args:
        key: Configuration key (supports dot-separated path like "ai.default_provider")
        default: Default value

    Returns:
        Configuration value
    """
    config = load_config()

    # Support dot-separated path
    keys = key.split(".")
    value = config

    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default

    return value


def set_config(key: str, value: Any) -> None:
    """
    Set configuration value

    Args:
        key: Configuration key
        value: Configuration value
    """
    config = load_config()

    # Support dot-separated path
    keys = key.split(".")
    target = config

    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]

    target[keys[-1]] = value

    # Save to corresponding configuration file
    if keys[0] == "ai":
        save_yaml_config(AI_CONFIG_FILE, config["ai"])
    elif keys[0] == "database":
        save_yaml_config(DATABASE_CONFIG_FILE, config["database"])
    elif keys[0] == "application":
        save_yaml_config(APPLICATION_CONFIG_FILE, config["application"])
    elif keys[0] == "providers" and len(keys) > 1:
        provider_name = keys[1]
        provider_config = config.get("providers", {}).get(provider_name, {})
        save_provider_config(provider_name, provider_config)


def _get_default_config() -> Dict[str, Any]:
    """
    Get default configuration

    Returns:
        Default configuration dictionary
    """
    return {
        "ai": {
            "default_provider": "deepseek",
            "providers": {
                "openai": {
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "",
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "timeout": 30,
                },
                "deepseek": {
                    "api_base": "https://api.deepseek.com/v1",
                    "api_key": "",
                    "model": "deepseek-chat",
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
            },
        },
        "database": {
            "type": "sqlite",
            "path": str(Path.home() / ".beancountpilot" / "data" / "beancountpilot.db"),
        },
        "application": {
            "frontend": {
                "default_language": "en",
            }
        },
        "providers": {},
    }


def get_env_var(key: str, default: str = "") -> str:
    """
    Get environment variable

    Args:
        key: Environment variable name
        default: Default value

    Returns:
        Environment variable value
    """
    return os.getenv(key, default)


def expand_path(path: str) -> Path:
    """
    Expand path (supports ~ and environment variables)

    Args:
        path: Path string

    Returns:
        Expanded Path object
    """
    # Expand environment variables
    path = os.path.expandvars(path)

    # Expand ~
    path = os.path.expanduser(path)

    return Path(path)
