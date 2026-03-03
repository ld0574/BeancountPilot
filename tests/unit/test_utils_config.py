"""
Unit tests for configuration utilities
"""

import pytest
import yaml
import tempfile
from pathlib import Path

from src.utils.config import (
    load_yaml_config,
    save_yaml_config,
    get_config,
    set_config,
    _get_default_config,
    CONFIG_DIR,
    AI_CONFIG_FILE,
    DATABASE_CONFIG_FILE,
    APPLICATION_CONFIG_FILE,
    PROVIDERS_CONFIG_DIR,
    load_providers_config,
    save_provider_config,
    _get_default_config,
)


class TestLoadYamlConfig:
    """Test load_yaml_config function"""

    def test_load_existing_config(self):
        """Test loading existing YAML configuration file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"test_key": "test_value"}, f)
            temp_path = Path(f.name)

        try:
            config = load_yaml_config(temp_path)
            assert config == {"test_key": "test_value"}
        finally:
            temp_path.unlink()

    def test_load_nonexistent_config(self):
        """Test loading non-existent configuration file"""
        config = load_yaml_config(Path("/nonexistent/config.yaml"))
        assert config == {}

    def test_load_empty_config(self):
        """Test loading empty configuration file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            config = load_yaml_config(temp_path)
            assert config == {}
        finally:
            temp_path.unlink()

    def test_load_config_with_nested_structure(self):
        """Test loading configuration with nested structure"""
        test_config = {
            "level1": {
                "level2": {
                    "level3": "value"
                }
            }
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            temp_path = Path(f.name)

        try:
            config = load_yaml_config(temp_path)
            assert config["level1"]["level2"]["level3"] == "value"
        finally:
            temp_path.unlink()


class TestSaveYamlConfig:
    """Test save_yaml_config function"""

    def test_save_config(self):
        """Test saving configuration to YAML file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test_config.yaml"
            config = {"test_key": "test_value", "nested": {"key": "value"}}

            save_yaml_config(temp_path, config)

            # Verify file was created
            assert temp_path.exists()

            # Verify content
            loaded = load_yaml_config(temp_path)
            assert loaded == config

    def test_save_config_creates_directory(self):
        """Test that save_yaml_config creates directory if it doesn't exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "subdir" / "test_config.yaml"
            config = {"test_key": "test_value"}

            save_yaml_config(temp_path, config)

            # Verify directory was created
            assert temp_path.exists()
            assert temp_path.parent.exists()

    def test_save_config_unicode(self):
        """Test saving configuration with Unicode characters"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test_config.yaml"
            config = {"test_key": "测试中文", "emoji": "🎉"}

            save_yaml_config(temp_path, config)

            # Verify content
            loaded = load_yaml_config(temp_path)
            assert loaded["test_key"] == "测试中文"
            assert loaded["emoji"] == "🎉"


class TestGetConfig:
    """Test get_config function"""

    def test_get_config_simple_key(self, monkeypatch):
        """Test getting configuration value with simple key"""
        test_config = {
            "ai": {"default_provider": "deepseek"},
            "database": {"type": "sqlite"},
        }
        monkeypatch.setattr("src.utils.config.load_config", lambda: test_config)

        value = get_config("ai.default_provider")
        assert value == "deepseek"

    def test_get_config_nested_key(self, monkeypatch):
        """Test getting configuration value with nested key"""
        test_config = {
            "ai": {
                "providers": {
                    "openai": {
                        "model": "gpt-4o-mini"
                    }
                }
            }
        }
        monkeypatch.setattr("src.utils.config.load_config", lambda: test_config)

        value = get_config("ai.providers.openai.model")
        assert value == "gpt-4o-mini"

    def test_get_config_nonexistent_key(self, monkeypatch):
        """Test getting non-existent configuration key"""
        test_config = {"ai": {"default_provider": "deepseek"}}
        monkeypatch.setattr("src.utils.config.load_config", lambda: test_config)

        value = get_config("nonexistent.key")
        assert value is None

    def test_get_config_with_default(self, monkeypatch):
        """Test getting configuration with default value"""
        test_config = {"ai": {"default_provider": "deepseek"}}
        monkeypatch.setattr("src.utils.config.load_config", lambda: test_config)

        value = get_config("nonexistent.key", default="default_value")
        assert value == "default_value"

    def test_get_config_invalid_path(self, monkeypatch):
        """Test getting configuration with invalid path"""
        test_config = {"ai": {"default_provider": "deepseek"}}
        monkeypatch.setattr("src.utils.config.load_config", lambda: test_config)

        value = get_config("ai.nonexistent.key")
        assert value is None


class TestSetConfig:
    """Test set_config function"""

    def test_set_config_simple_key(self, monkeypatch):
        """Test setting configuration value with simple key"""
        test_config = {"ai": {"default_provider": "deepseek"}}
        monkeypatch.setattr("src.utils.config.load_config", lambda: test_config)
        monkeypatch.setattr("src.utils.config.save_yaml_config", lambda path, config: None)

        set_config("ai.default_provider", "openai")

        # Note: This test verifies the function runs without error
        # Actual file writing is mocked

    def test_set_config_nested_key(self, monkeypatch):
        """Test setting configuration value with nested key"""
        test_config = {"ai": {"providers": {}}}
        monkeypatch.setattr("src.utils.config.load_config", lambda: test_config)
        monkeypatch.setattr("src.utils.config.save_yaml_config", lambda path, config: None)

        set_config("ai.providers.openai.model", "gpt-4o-mini")

        # Note: This test verifies the function runs without error
        # Actual file writing is mocked


class TestGetDefaultConfig:
    """Test _get_default_config function"""

    def test_get_default_config_structure(self):
        """Test default configuration structure"""
        config = _get_default_config()

        assert "ai" in config
        assert "database" in config
        assert "application" in config

    def test_get_default_config_ai_section(self):
        """Test default AI configuration"""
        config = _get_default_config()

        assert "ai" in config
        assert "default_provider" in config["ai"]
        assert "providers" in config["ai"]

    def test_get_default_config_database_section(self):
        """Test default database configuration"""
        config = _get_default_config()

        assert "database" in config
        assert "type" in config["database"]

    def test_get_default_config_application_section(self):
        """Test default application configuration"""
        config = _get_default_config()

        assert "application" in config
        assert "frontend" in config["application"]


class TestProvidersConfig:
    """Test providers configuration helpers"""

    def test_load_providers_config_empty(self, monkeypatch):
        """Test loading providers config when directory missing"""
        monkeypatch.setattr("src.utils.config.PROVIDERS_CONFIG_DIR", Path("/nonexistent"))
        config = load_providers_config()
        assert config == {}

    def test_save_provider_config(self, monkeypatch, tmp_path):
        """Test saving provider config"""
        providers_dir = tmp_path / "providers"
        monkeypatch.setattr("src.utils.config.PROVIDERS_CONFIG_DIR", providers_dir)
        monkeypatch.setattr("src.utils.config.ensure_providers_dir", lambda: providers_dir.mkdir(parents=True, exist_ok=True))

        save_provider_config("alipay", {"mapping": {"default": "Expenses:Misc"}})

        saved_file = providers_dir / "alipay.yaml"
        assert saved_file.exists()
        loaded = load_yaml_config(saved_file)
        assert loaded["mapping"]["default"] == "Expenses:Misc"
