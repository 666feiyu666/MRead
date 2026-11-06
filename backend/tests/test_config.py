"""Data profile selection: dev is the default, explicit paths win, .env never overrides."""

from __future__ import annotations

import importlib

import pytest

from app import config


@pytest.fixture
def reload_config(monkeypatch, tmp_path):
    """Reload the config module under a given environment, then restore the test setup.

    The repository's own ``.env`` is pointed away so a developer's local
    ``MREAD_PROFILE=daily`` cannot make these assertions flaky.
    """
    absent = tmp_path / "no-env-file"
    monkeypatch.setenv("MREAD_ENV_FILE", str(absent))

    def _reload(**env: str | None):
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        return importlib.reload(config)

    yield _reload

    importlib.reload(config)
    monkeypatch.undo()
    importlib.reload(config)


def test_dev_is_the_default_profile(reload_config):
    reloaded = reload_config(MREAD_PROFILE=None, MREAD_DATA_DIR=None)
    assert reloaded.DATA_PROFILE == "dev"
    assert reloaded.DATA_DIR == reloaded.REPO_ROOT / "data" / "dev"
    assert reloaded.DB_PATH.name == "mread.db"


def test_daily_profile_uses_its_own_directory(reload_config):
    reloaded = reload_config(MREAD_PROFILE="daily", MREAD_DATA_DIR=None)
    assert reloaded.DATA_DIR == reloaded.REPO_ROOT / "data" / "daily"
    assert reloaded.DATA_DIR != reloaded.REPO_ROOT / "data" / "dev"


def test_explicit_data_dir_overrides_the_profile(reload_config, tmp_path):
    reloaded = reload_config(MREAD_PROFILE="daily", MREAD_DATA_DIR=str(tmp_path))
    assert reloaded.DATA_DIR == tmp_path


def test_unknown_profile_name_becomes_a_sibling_directory(reload_config):
    reloaded = reload_config(MREAD_PROFILE="Experiment", MREAD_DATA_DIR=None)
    assert reloaded.DATA_PROFILE == "experiment"
    assert reloaded.DATA_DIR == reloaded.REPO_ROOT / "data" / "experiment"


def test_dotenv_does_not_override_the_process_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('MREAD_PROFILE=daily\nDEEPSEEK_MODEL="from-file"\n', encoding="utf-8")

    monkeypatch.setenv("MREAD_PROFILE", "dev")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    config._load_dotenv(env_file)

    import os

    assert os.environ["MREAD_PROFILE"] == "dev", "an explicit shell variable must win"
    assert os.environ["DEEPSEEK_MODEL"] == "from-file", "an unset variable is filled from .env"
