"""Channels DVR Server client for triggering M3U source refresh.

Channels DVR exposes an unauthenticated REST API on port 8089 by default
(see https://getchannels.com/docs/server-api/introduction/). Some users
front the server with a reverse proxy that adds HTTP Basic Auth, so the
client supports optional username/password.

The refresh endpoint is fire-and-forget: ``PUT /providers/m3u/sources/
<source_name>/refresh`` returns immediately while the server starts the
refresh task in the background. This is unlike Emby/Jellyfin, which
expose a polling task model, so there is nothing here to poll.
"""

import logging
import time
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class ChannelsDVRClient:
    """Client for Channels DVR Server API."""

    SERVER_LABEL: str = "CHANNELSDVR"

    def __init__(
        self,
        base_url: str,
        source_name: str = "",
        username: str = "",
        password: str = "",
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.source_name = source_name
        self.username = username
        self.password = password
        self.timeout = timeout

    def _auth(self) -> httpx.BasicAuth | None:
        if self.username and self.password:
            return httpx.BasicAuth(self.username, self.password)
        return None

    def _source_path(self) -> str:
        return f"/providers/m3u/sources/{quote(self.source_name, safe='')}"

    def test_connection(self) -> dict:
        """Verify connectivity, version, and that the source exists.

        Returns:
            dict with success, server_version, source_name, error
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/status",
                timeout=self.timeout,
                auth=self._auth(),
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            return {
                "success": False,
                "error": f"Cannot connect to {self.base_url}",
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return {
                    "success": False,
                    "error": "Authentication failed — check username/password",
                }
            return {"success": False, "error": str(e)}
        except httpx.HTTPError as e:
            return {"success": False, "error": str(e)}

        server_version: str | None = None
        try:
            data = resp.json()
            server_version = data.get("version") if isinstance(data, dict) else None
        except ValueError:
            # /status returned non-JSON — still treat as reachable
            pass

        if not self.source_name:
            return {
                "success": True,
                "server_version": server_version,
                "source_name": None,
            }

        try:
            src_resp = httpx.get(
                f"{self.base_url}{self._source_path()}",
                timeout=self.timeout,
                auth=self._auth(),
            )
        except httpx.HTTPError as e:
            return {
                "success": False,
                "server_version": server_version,
                "error": f"Failed to verify source: {e}",
            }

        if src_resp.status_code == 404:
            return {
                "success": False,
                "server_version": server_version,
                "error": f"Source '{self.source_name}' not found on Channels DVR",
            }
        if src_resp.status_code >= 400:
            return {
                "success": False,
                "server_version": server_version,
                "error": f"Source check returned HTTP {src_resp.status_code}",
            }

        return {
            "success": True,
            "server_version": server_version,
            "source_name": self.source_name,
        }

    def trigger_m3u_refresh(self, timeout: int = 60) -> dict:
        """Trigger an M3U source refresh on the Channels DVR server.

        The endpoint returns immediately — Channels DVR runs the refresh
        in the background, so this method does not poll for completion.

        Returns:
            dict with success, message, duration
        """
        if not self.source_name:
            return {
                "success": False,
                "message": "No source name configured",
                "duration": 0,
            }

        start = time.monotonic()
        try:
            resp = httpx.put(
                f"{self.base_url}{self._source_path()}/refresh",
                timeout=timeout,
                auth=self._auth(),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            duration = time.monotonic() - start
            if e.response.status_code == 404:
                msg = f"Source '{self.source_name}' not found"
            elif e.response.status_code in (401, 403):
                msg = "Authentication failed — check username/password"
            else:
                msg = f"Refresh failed: HTTP {e.response.status_code}"
            return {"success": False, "message": msg, "duration": duration}
        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"Refresh failed: {e}",
                "duration": time.monotonic() - start,
            }

        duration = time.monotonic() - start
        logger.info(
            "[%s] Triggered refresh for source '%s' in %.2fs",
            self.SERVER_LABEL,
            self.source_name,
            duration,
        )
        return {
            "success": True,
            "message": f"Refresh triggered for source '{self.source_name}'",
            "duration": duration,
        }
