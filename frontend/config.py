"""
Frontend configuration module
Loads configuration from application.yaml
"""

import yaml
from pathlib import Path
from typing import Dict, Any


# Cache for loaded config
_config_cache: Dict[str, Any] = None


def _load_config() -> Dict[str, Any]:
    """
    Load configuration from application.yaml

    Returns:
        Configuration dictionary
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    try:
        # Find config directory
        # Try multiple possible locations
        config_paths = [
            Path(__file__).parent.parent / "config" / "application.yaml",
            Path(__file__).parent / "config" / "application.yaml",
            Path("config") / "application.yaml",
        ]

        config_file = None
        for path in config_paths:
            if path.exists():
                config_file = path
                break

        if config_file is None:
            # Return default config if file not found
            _config_cache = _get_default_config()
            return _config_cache

        with open(config_file, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f)
            return _config_cache
    except Exception:
        # Return default config on any error
        _config_cache = _get_default_config()
        return _config_cache


def _get_default_config() -> Dict[str, Any]:
    """
    Get default configuration

    Returns:
        Default configuration dictionary
    """
    return {
        "frontend": {
            "api": {
                "base_url": "http://localhost:8000",
                "prefix": "/api",
                "health_endpoint": "/health",
                "timeout": 30,
            },
            "streamlit": {
                "port": 8501,
                "headless": False,
                "gather_usage_stats": False,
            },
            "default_chart_of_accounts": "",
        }
    }


def get_api_base_url() -> str:
    """
    Get API base URL

    Returns:
        API base URL
    """
    config = _load_config()
    return config.get("frontend", {}).get("api", {}).get("base_url", "http://localhost:8000")


def get_api_prefix() -> str:
    """
    Get API prefix

    Returns:
        API prefix
    """
    config = _load_config()
    return config.get("frontend", {}).get("api", {}).get("prefix", "/api")


def get_api_health_endpoint() -> str:
    """
    Get API health check endpoint

    Returns:
        Health check endpoint
    """
    config = _load_config()
    return config.get("frontend", {}).get("api", {}).get("health_endpoint", "/health")


def get_api_timeout() -> int:
    """
    Get API timeout in seconds

    Returns:
        Timeout in seconds
    """
    config = _load_config()
    return config.get("frontend", {}).get("api", {}).get("timeout", 30)


def get_api_url(endpoint: str) -> str:
    """
    Build full API URL for a given endpoint

    Args:
        endpoint: API endpoint (e.g., "/upload", "/classify")

    Returns:
        Full API URL
    """
    base_url = get_api_base_url()
    prefix = get_api_prefix()
    return f"{base_url}{prefix}{endpoint}"


def get_health_check_url() -> str:
    """
    Get health check URL

    Returns:
        Health check URL
    """
    base_url = get_api_base_url()
    health_endpoint = get_api_health_endpoint()
    return f"{base_url}{health_endpoint}"


def get_default_chart_of_accounts() -> str:
    """
    Get default chart of accounts

    Returns:
        Default chart of accounts text
    """
    config = _load_config()
    return config.get("frontend", {}).get("default_chart_of_accounts", "")


def get_streamlit_port() -> int:
    """
    Get Streamlit port

    Returns:
        Streamlit port
    """
    config = _load_config()
    return config.get("frontend", {}).get("streamlit", {}).get("port", 8501)
