import asyncio
import os
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.blueprints_updater.const import (
    FILTER_MODE_ALL,
    FILTER_MODE_BLACKLIST,
    FILTER_MODE_WHITELIST,
)
from custom_components.blueprints_updater.coordinator import BlueprintUpdateCoordinator


@pytest.fixture
def coordinator(hass):
    """Fixture for BlueprintUpdateCoordinator."""
    entry = MagicMock()
    entry.options = {}
    entry.data = {}
    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__", return_value=None
    ):
        return BlueprintUpdateCoordinator(
            hass,
            entry,
            timedelta(hours=24),
            filter_mode=FILTER_MODE_ALL,
        )


def test_normalize_url(coordinator):
    """Test URL normalization."""
    # GitHub blob to raw
    assert (
        coordinator._normalize_url("https://github.com/user/repo/blob/main/blueprints/test.yaml")
        == "https://raw.githubusercontent.com/user/repo/main/blueprints/test.yaml"
    )

    # Gist to raw
    assert (
        coordinator._normalize_url("https://gist.github.com/user/gist_id")
        == "https://gist.github.com/user/gist_id/raw"
    )

    # Gist already raw
    assert (
        coordinator._normalize_url("https://gist.github.com/user/gist_id/raw")
        == "https://gist.github.com/user/gist_id/raw"
    )

    # HA Forum topic to JSON API
    assert (
        coordinator._normalize_url("https://community.home-assistant.io/t/topic-slug/12345")
        == "https://community.home-assistant.io/t/12345.json"
    )

    # Other URL unchanged
    assert (
        coordinator._normalize_url("https://example.com/blueprint.yaml")
        == "https://example.com/blueprint.yaml"
    )


def test_parse_forum_content(coordinator):
    """Test parsing forum content."""
    # Valid forum JSON
    json_data = {
        "post_stream": {
            "posts": [
                {
                    "cooked": (
                        '<p>Here is my blueprint:</p><pre><code class="lang-yaml">blueprint:\n'
                        "  name: Test\n  source_url: https://url.com</code></pre>"
                    )
                }
            ]
        }
    }
    content = coordinator._parse_forum_content(json_data)
    assert "blueprint:" in content
    assert "name: Test" in content

    # No blueprint in code block
    json_data_no_bp = {"post_stream": {"posts": [{"cooked": "<code>not a blueprint</code>"}]}}
    assert coordinator._parse_forum_content(json_data_no_bp) is None

    # Empty/Missing posts
    assert coordinator._parse_forum_content({}) is None
    assert coordinator._parse_forum_content({"post_stream": {"posts": []}}) is None


def test_ensure_source_url(coordinator):
    """Test ensuring source_url is present."""
    source_url = "https://github.com/user/repo/blob/main/test.yaml"

    # Missing source_url
    content = "blueprint:\n  name: Test"
    new_content = coordinator._ensure_source_url(content, source_url)
    assert f"source_url: {source_url}" in new_content

    # Already present
    content_with_url = f"blueprint:\n  name: Test\n  source_url: {source_url}"
    assert coordinator._ensure_source_url(content_with_url, source_url) == content_with_url

    # Present with quotes
    content_with_quotes = f"blueprint:\n  name: Test\n  source_url: '{source_url}'"
    assert coordinator._ensure_source_url(content_with_quotes, source_url) == content_with_quotes


def test_scan_blueprints(hass, coordinator):
    """Test scanning blueprints directory."""
    bp_path = "/config/blueprints"
    mock_files = [(bp_path, [], ["valid.yaml", "invalid.yaml", "no_url.yaml", "not_yaml.txt"])]

    valid_content = "blueprint:\n  name: Valid\n  source_url: https://url.com"
    invalid_content = "not: a blueprint"
    no_url_content = "blueprint:\n  name: No URL"

    def open_side_effect(path, encoding=None):
        path_str = str(path)
        basename = os.path.basename(path_str)
        content = ""
        if basename == "valid.yaml":
            content = valid_content
        elif basename == "invalid.yaml":
            content = invalid_content
        elif basename == "no_url.yaml":
            content = no_url_content

        m = MagicMock()
        m.read.return_value = content
        m.__enter__.return_value = m
        return m

    with (
        patch("os.path.isdir", return_value=True),
        patch("os.walk", return_value=mock_files),
        patch("builtins.open", side_effect=open_side_effect),
    ):
        # ALL mode
        results = coordinator._scan_blueprints(hass, FILTER_MODE_ALL, [])
        assert len(results) == 1, f"Expected 1, got {len(results)}: {results.keys()}"
        assert any("valid.yaml" in k for k in results)
        full_path = next(iter(results.keys()))
        assert results[full_path]["rel_path"] == "valid.yaml"

        # WHITELIST mode - including valid.yaml
        results = coordinator._scan_blueprints(hass, FILTER_MODE_WHITELIST, ["valid.yaml"])
        assert len(results) == 1

        # WHITELIST mode - excluding valid.yaml
        results = coordinator._scan_blueprints(hass, FILTER_MODE_WHITELIST, ["other.yaml"])
        assert len(results) == 0

        # BLACKLIST mode - excluding valid.yaml
        results = coordinator._scan_blueprints(hass, FILTER_MODE_BLACKLIST, ["valid.yaml"])
        assert len(results) == 0


@pytest.mark.asyncio
async def test_async_update_blueprint(coordinator):
    """Test the full update flow for a single blueprint."""
    path = "/config/blueprints/test.yaml"
    info = {
        "name": "Test",
        "rel_path": "test.yaml",
        "source_url": "https://github.com/user/repo/blob/main/test.yaml",
        "hash": "old_hash",
    }
    results = {path: {"last_error": None, "hash": "old_hash"}}

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = AsyncMock(return_value="blueprint:\n  name: Test")

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__.return_value = mock_response

    semaphore = asyncio.Semaphore(1)

    with patch("custom_components.blueprints_updater.coordinator.hashlib.sha256") as mock_hash:
        # Mock hash to be different
        mock_hash.return_value.hexdigest.return_value = "new_hash"

        await coordinator._async_update_blueprint(mock_session, semaphore, path, info, results)

    assert path in results
    assert results[path]["updatable"] is True
    assert results[path]["remote_hash"] == "new_hash"
    assert "source_url" in results[path]["remote_content"]


@pytest.mark.asyncio
async def test_async_install_blueprint(hass, coordinator):
    """Test installing a blueprint and reloading services."""
    path = "/config/blueprints/test.yaml"
    remote_content = "blueprint:\n  name: Test"

    # Mock services: automation and script exist, template does not
    hass.services.has_service = MagicMock(
        side_effect=lambda domain, service: (
            domain in ["automation", "script"] if service == "reload" else False
        )
    )
    hass.services.async_call = AsyncMock()

    with (
        patch("builtins.open", MagicMock()),
        patch("custom_components.blueprints_updater.coordinator.os.path.isfile", return_value=True),
    ):
        await coordinator.async_install_blueprint(path, remote_content)

    # Verify automation and script were called, template was not
    assert hass.services.async_call.call_count == 2
    hass.services.async_call.assert_any_call("automation", "reload")
    hass.services.async_call.assert_any_call("script", "reload")

    # Verify template was NOT called
    with pytest.raises(AssertionError):
        hass.services.async_call.assert_any_call("template", "reload")


@pytest.mark.asyncio
async def test_async_update_data_partial_failure(coordinator):
    """Test that one failed blueprint does not stop others."""
    # Setup 2 blueprints
    blueprints = {
        "/config/blueprints/good.yaml": {
            "name": "Good",
            "rel_path": "good.yaml",
            "source_url": "https://url.com/good.yaml",
            "hash": "good_hash",
        },
        "/config/blueprints/bad.yaml": {
            "name": "Bad",
            "rel_path": "bad.yaml",
            "source_url": "https://url.com/bad.yaml",
            "hash": "bad_hash",
        },
    }

    # Mock _scan_blueprints
    coordinator._scan_blueprints = MagicMock(return_value=blueprints)

    # Mock responses: good = 200, bad = 404
    mock_good_resp = MagicMock()
    mock_good_resp.status = 200
    mock_good_resp.raise_for_status = MagicMock()
    mock_good_resp.text = AsyncMock(return_value="blueprint:\n  name: Good")

    mock_bad_resp = MagicMock()
    mock_bad_resp.status = 404
    mock_bad_resp.raise_for_status = MagicMock(side_effect=Exception("404 Not Found"))

    @patch("aiohttp.ClientSession")
    async def run_test(mock_session_class):
        mock_session = mock_session_class.return_value
        mock_session.__aenter__.return_value = mock_session

        def get_side_effect(url, **kwargs):
            m = MagicMock()
            if "good.yaml" in url:
                m.__aenter__.return_value = mock_good_resp
            else:
                m.__aenter__.return_value = mock_bad_resp
            return m

        mock_session.get.side_effect = get_side_effect

        with patch("custom_components.blueprints_updater.coordinator.hashlib.sha256") as mock_hash:
            mock_hash.return_value.hexdigest.return_value = "new_hash"
            return await coordinator._async_update_data()

    results = await run_test()

    # Verify both are in results
    assert "/config/blueprints/good.yaml" in results
    assert "/config/blueprints/bad.yaml" in results

    # Good one should be updatable
    assert results["/config/blueprints/good.yaml"]["updatable"] is True
    assert results["/config/blueprints/good.yaml"]["last_error"] is None

    # Bad one should have error
    assert results["/config/blueprints/bad.yaml"]["last_error"] is not None
    assert "404" in results["/config/blueprints/bad.yaml"]["last_error"]
