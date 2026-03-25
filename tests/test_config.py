"""Tests for lifeos.core.config module."""
import importlib
import pytest
from pathlib import Path


def test_get_config_returns_object_with_required_attrs(mock_env):
    """get_config() returns a Config object with all required attributes."""
    # Reset cached config singleton before test
    import lifeos.core.config as cfg_module
    cfg_module._config = None

    from lifeos.core.config import get_config
    config = get_config()

    assert hasattr(config, "gemini_api_key")
    assert hasattr(config, "groq_api_key")
    assert hasattr(config, "falkordb_host")
    assert hasattr(config, "falkordb_port")
    assert hasattr(config, "graph_name")
    assert hasattr(config, "transcript_dir")


def test_get_config_reads_api_keys_from_env(mock_env):
    """get_config() reads GEMINI_API_KEY and GROQ_API_KEY from environment."""
    import lifeos.core.config as cfg_module
    cfg_module._config = None

    from lifeos.core.config import get_config
    config = get_config()

    assert config.gemini_api_key == "test-gemini-key"
    assert config.groq_api_key == "test-groq-key"


def test_get_config_falkordb_host_port(mock_env):
    """get_config() reads FALKORDB_HOST and FALKORDB_PORT from environment."""
    import lifeos.core.config as cfg_module
    cfg_module._config = None

    from lifeos.core.config import get_config
    config = get_config()

    assert config.falkordb_host == "localhost"
    assert config.falkordb_port == 6379


def test_get_config_graph_name(mock_env):
    """get_config() reads GRAPH_NAME from environment."""
    import lifeos.core.config as cfg_module
    cfg_module._config = None

    from lifeos.core.config import get_config
    config = get_config()

    assert config.graph_name == "test-lifeos"


def test_get_config_transcript_dir_is_path(mock_env):
    """get_config().transcript_dir is a Path instance."""
    import lifeos.core.config as cfg_module
    cfg_module._config = None

    from lifeos.core.config import get_config
    config = get_config()

    assert isinstance(config.transcript_dir, Path)


def test_get_config_falkordb_port_is_int(mock_env):
    """get_config().falkordb_port is an integer, not a string."""
    import lifeos.core.config as cfg_module
    cfg_module._config = None

    from lifeos.core.config import get_config
    config = get_config()

    assert isinstance(config.falkordb_port, int)
