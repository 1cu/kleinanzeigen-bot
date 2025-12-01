# SPDX-FileCopyrightText: © Sebastian Thomschke and contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-ArtifactOfProjectHomePage: https://github.com/Second-Hand-Friends/kleinanzeigen-bot/
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kleinanzeigen_bot import LOG, KleinanzeigenBot


@pytest.mark.asyncio
async def test_cli_runs_requested_action(monkeypatch:pytest.MonkeyPatch, test_bot:KleinanzeigenBot) -> None:
    """Ensure that the run method executes the selected command."""
    create_mock = MagicMock()
    monkeypatch.setattr(test_bot, "create_default_config", create_mock)

    await test_bot.run(["app", "create-config"])

    create_mock.assert_called_once_with()
    assert test_bot.command == "create-config"


@pytest.mark.asyncio
async def test_cli_verbose_flag_sets_log_level(caplog:pytest.LogCaptureFixture, test_bot:KleinanzeigenBot) -> None:
    """Verify that verbose mode really enables DEBUG logging."""
    LOG.setLevel(logging.INFO)
    with caplog.at_level(logging.DEBUG, logger="kleinanzeigen_bot"):
        await test_bot.run(["app", "-v", "help"])
        assert LOG.level == logging.DEBUG


@pytest.mark.asyncio
async def test_cli_loads_config_with_overrides(
    monkeypatch:pytest.MonkeyPatch,
    tmp_path:Path,
    test_bot:KleinanzeigenBot
) -> None:
    """Ensure verify flow wires config overrides and update checks without touching I/O."""
    config_path = tmp_path / "cli-config.yaml"
    dummy_config = SimpleNamespace(login = SimpleNamespace(username = "cli_user"))

    monkeypatch.setattr(test_bot, "configure_file_logging", MagicMock())
    load_ads_mock = MagicMock(return_value = [])
    monkeypatch.setattr(test_bot, "load_ads", load_ads_mock)

    def fake_load_config() -> None:
        test_bot.config = dummy_config

    load_config_mock = MagicMock(side_effect = fake_load_config)
    monkeypatch.setattr(test_bot, "load_config", load_config_mock)

    with patch("kleinanzeigen_bot.UpdateChecker") as update_checker_cls:
        checker_instance = update_checker_cls.return_value
        checker_instance.check_for_updates.return_value = None

        await test_bot.run(["app", "--config", str(config_path), "verify", "--ads=all"])

        checker_instance.check_for_updates.assert_called_once_with()
        update_checker_cls.assert_called_once_with(dummy_config)

    assert test_bot.command == "verify"
    assert test_bot.ads_selector == "all"
    assert test_bot.config_file_path == str(config_path.resolve())
    assert test_bot.config.login.username == "cli_user"
    load_config_mock.assert_called_once_with()
    load_ads_mock.assert_called_once_with()


@pytest.mark.asyncio
async def test_cli_missing_config_reports_error(
    caplog:pytest.LogCaptureFixture,
    monkeypatch:pytest.MonkeyPatch,
    tmp_path:Path,
    test_bot:KleinanzeigenBot
) -> None:
    """Simulate a missing config where load_config surfaces the failure immediately."""
    monkeypatch.setattr(test_bot, "configure_file_logging", MagicMock())
    missing_config = tmp_path / "missing" / "config.yaml"
    expected_path = missing_config.resolve()

    def fake_create_default_config() -> None:
        LOG.info("Saving [%s]...", expected_path)

    monkeypatch.setattr(test_bot, "create_default_config", MagicMock(side_effect = fake_create_default_config))

    def fake_load_config() -> None:
        test_bot.create_default_config()
        raise FileNotFoundError(f"Unable to load {expected_path}")

    monkeypatch.setattr(test_bot, "load_config", MagicMock(side_effect = fake_load_config))

    with caplog.at_level(logging.INFO):
        with pytest.raises(FileNotFoundError) as exc_info:
            await test_bot.run(["app", "verify", "--config", str(missing_config)])

    assert str(expected_path) in str(exc_info.value)
    assert f"Saving [{expected_path}]" in caplog.text


@pytest.mark.asyncio
async def test_cli_invalid_option_logs_error(caplog:pytest.LogCaptureFixture, test_bot:KleinanzeigenBot) -> None:
    """Ensure invalid CLI options are logged and raise the expected exit code."""
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc_info:
            await test_bot.run(["app", "--definitely-invalid"])

    assert exc_info.value.code == 2
    assert "Use --help" in caplog.text
