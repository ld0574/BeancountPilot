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


def ensure_config_dir():
    """Ensure configuration directory exists"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


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
    }

    return config


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
