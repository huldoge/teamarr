"""Smoke tests for ChannelsDVRClient.

The Channels DVR REST API is unauthenticated by default on the local
network, but supports HTTP Basic Auth when fronted by a reverse proxy.
These tests pin the URL building, source-name encoding, and Basic Auth
behavior so a refactor can't silently break the refresh hook.
"""

import httpx
import pytest

from teamarr.channelsdvr.client import ChannelsDVRClient


class TestUrlBuilding:
    def test_strips_trailing_slash(self):
        client = ChannelsDVRClient(base_url="http://channels:8089/")
        assert client.base_url == "http://channels:8089"

    def test_source_path_uses_source_name(self):
        client = ChannelsDVRClient(
            base_url="http://channels:8089", source_name="MyM3U"
        )
        assert client._source_path() == "/providers/m3u/sources/MyM3U"

    def test_source_path_url_encodes_special_chars(self):
        # Spaces and slashes in source names must be percent-encoded.
        client = ChannelsDVRClient(
            base_url="http://channels:8089", source_name="My Source/With Slash"
        )
        assert (
            client._source_path()
            == "/providers/m3u/sources/My%20Source%2FWith%20Slash"
        )


class TestAuth:
    def test_no_auth_when_credentials_missing(self):
        client = ChannelsDVRClient(base_url="http://channels:8089")
        assert client._auth() is None

    def test_no_auth_when_only_username(self):
        client = ChannelsDVRClient(base_url="http://channels:8089", username="u")
        assert client._auth() is None

    def test_basic_auth_when_both_set(self):
        client = ChannelsDVRClient(
            base_url="http://channels:8089", username="u", password="p"
        )
        auth = client._auth()
        assert isinstance(auth, httpx.BasicAuth)


class TestTriggerRefreshGuards:
    def test_no_source_name_returns_failure(self):
        client = ChannelsDVRClient(base_url="http://channels:8089")
        result = client.trigger_m3u_refresh()
        assert result["success"] is False
        assert "source name" in result["message"].lower()


class TestTriggerRefreshHTTP:
    """Use httpx MockTransport to verify the wire request without a real server."""

    def _make_client(self, handler, **kwargs):
        # Inject a mock transport by monkeypatching httpx.put for this test.
        return ChannelsDVRClient(
            base_url="http://channels:8089", source_name="MyM3U", **kwargs
        )

    def test_successful_refresh_returns_success(self, monkeypatch):
        captured: dict = {}

        def fake_put(url, **kwargs):
            captured["url"] = url
            captured["auth"] = kwargs.get("auth")
            req = httpx.Request("PUT", url)
            return httpx.Response(204, request=req)

        monkeypatch.setattr(httpx, "put", fake_put)

        client = self._make_client(None)
        result = client.trigger_m3u_refresh()

        assert result["success"] is True
        assert (
            captured["url"]
            == "http://channels:8089/providers/m3u/sources/MyM3U/refresh"
        )
        assert captured["auth"] is None

    def test_404_returns_source_not_found(self, monkeypatch):
        def fake_put(url, **kwargs):
            req = httpx.Request("PUT", url)
            return httpx.Response(404, request=req)

        monkeypatch.setattr(httpx, "put", fake_put)

        client = self._make_client(None)
        result = client.trigger_m3u_refresh()

        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_basic_auth_passed_through(self, monkeypatch):
        captured: dict = {}

        def fake_put(url, **kwargs):
            captured["auth"] = kwargs.get("auth")
            req = httpx.Request("PUT", url)
            return httpx.Response(204, request=req)

        monkeypatch.setattr(httpx, "put", fake_put)

        client = self._make_client(None, username="u", password="p")
        result = client.trigger_m3u_refresh()

        assert result["success"] is True
        assert isinstance(captured["auth"], httpx.BasicAuth)


class TestTestConnection:
    def test_status_unreachable_returns_error(self, monkeypatch):
        def fake_get(url, **kwargs):
            raise httpx.ConnectError("conn refused")

        monkeypatch.setattr(httpx, "get", fake_get)

        client = ChannelsDVRClient(base_url="http://channels:8089")
        result = client.test_connection()
        assert result["success"] is False
        assert "cannot connect" in result["error"].lower()

    def test_status_ok_no_source_returns_success(self, monkeypatch):
        def fake_get(url, **kwargs):
            req = httpx.Request("GET", url)
            return httpx.Response(200, json={"version": "2026.04.01"}, request=req)

        monkeypatch.setattr(httpx, "get", fake_get)

        client = ChannelsDVRClient(base_url="http://channels:8089")
        result = client.test_connection()
        assert result["success"] is True
        assert result["server_version"] == "2026.04.01"

    def test_source_404_returns_failure(self, monkeypatch):
        calls: list[str] = []

        def fake_get(url, **kwargs):
            calls.append(url)
            req = httpx.Request("GET", url)
            if url.endswith("/status"):
                return httpx.Response(
                    200, json={"version": "2026.04.01"}, request=req
                )
            return httpx.Response(404, request=req)

        monkeypatch.setattr(httpx, "get", fake_get)

        client = ChannelsDVRClient(
            base_url="http://channels:8089", source_name="missing"
        )
        result = client.test_connection()
        assert result["success"] is False
        assert "not found" in result["error"].lower()
        assert any("/providers/m3u/sources/missing" in c for c in calls)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
