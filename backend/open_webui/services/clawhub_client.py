"""
HTTP client for ClawHub.ai API v1.

Proxies requests from OpenWebUI backend to ClawHub, handling auth and rate limiting.

API reference:
- Search: GET /api/v1/search?q=...
- List:   GET /api/v1/skills?limit=&cursor=&sort=
- Detail: GET /api/v1/skills/{slug}
- File:   GET /api/v1/skills/{slug}/file?path=&version=
- Download: GET /api/v1/download?slug=&version=
- Versions: GET /api/v1/skills/{slug}/versions?limit=&cursor=
- Auth:   GET /api/v1/whoami
"""

import logging
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=120)


class ClawHubError(Exception):
    """Error from ClawHub API."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"ClawHub API error {status}: {message}")


class ClawHubClient:
    def __init__(self, base_url: str = "https://clawhub.ai", api_prefix: str = "/api/v1"):
        self.base_url = base_url
        self.api_prefix = api_prefix
        self._base_api_url = f"{base_url}{api_prefix}"

    def _headers(self, token: Optional[str] = None) -> dict:
        headers = {
            "User-Agent": "OpenWebUI-Marketplace/1.0",
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # ── Search & Browse ────────────────────────────────────────────────

    async def search_skills(
        self,
        query: str = "",
        cursor: Optional[str] = None,
        limit: int = 30,
        sort: str = "updated",
        highlighted_only: bool = False,
        token: Optional[str] = None,
    ) -> dict:
        """
        Search or list ClawHub skill catalog.

        If query is provided, uses GET /search?q=...
        Otherwise, uses GET /skills?limit=&cursor=&sort=
        """
        if query:
            # Full-text search endpoint
            params = {"q": query}
            if highlighted_only:
                params["highlightedOnly"] = "true"
            params["nonSuspiciousOnly"] = "true"
            return await self._get("/search", params=params, token=token)
        else:
            # Browse/list endpoint with cursor pagination
            params = {"limit": str(limit), "sort": sort}
            if cursor:
                params["cursor"] = cursor
            params["nonSuspiciousOnly"] = "true"
            return await self._get("/skills", params=params, token=token)

    async def get_skill(self, slug: str, token: Optional[str] = None) -> dict:
        """Get skill details by slug (e.g., 'peter/todoist-manager')."""
        return await self._get(f"/skills/{slug}", token=token)

    async def get_skill_versions(
        self, slug: str, limit: int = 10, cursor: Optional[str] = None,
        token: Optional[str] = None,
    ) -> dict:
        """Get version history for a skill."""
        params = {"limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        return await self._get(f"/skills/{slug}/versions", params=params, token=token)

    # ── Files & Download ───────────────────────────────────────────────

    async def get_skill_file(
        self, slug: str, path: str = "SKILL.md",
        version: Optional[str] = None,
        token: Optional[str] = None,
    ) -> str:
        """Get a file from a skill (typically SKILL.md). Returns raw text content."""
        params = {"path": path}
        if version:
            params["version"] = version
        return await self._get_text(
            f"/skills/{slug}/file", params=params, token=token
        )

    async def download_skill(
        self, slug: str, version: Optional[str] = None,
        token: Optional[str] = None,
    ) -> bytes:
        """Download full skill archive (ZIP). Returns raw bytes."""
        params = {"slug": slug}
        if version:
            params["version"] = version
        return await self._get_bytes("/download", params=params, token=token)

    async def get_skill_scan(
        self, slug: str, version: Optional[str] = None,
        token: Optional[str] = None,
    ) -> dict:
        """Get security scan results for a skill."""
        params = {}
        if version:
            params["version"] = version
        return await self._get(f"/skills/{slug}/scan", params=params, token=token)

    # ── Auth ───────────────────────────────────────────────────────────

    async def check_auth(self, token: str) -> dict:
        """Verify a ClawHub API token. Returns user info."""
        return await self._get("/whoami", token=token)

    # ── HTTP primitives ────────────────────────────────────────────────

    async def _get(
        self, path: str, params: dict = None, token: Optional[str] = None
    ) -> dict:
        url = f"{self._base_api_url}{path}"
        try:
            async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
                async with session.get(
                    url, params=params, headers=self._headers(token)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        retry_after = resp.headers.get("Retry-After", "30")
                        raise ClawHubError(429, f"Rate limited. Retry after {retry_after}s")
                    else:
                        text = await resp.text()
                        raise ClawHubError(resp.status, text[:500])
        except aiohttp.ClientError as e:
            raise ClawHubError(503, f"Connection error: {str(e)}")

    async def _get_text(
        self, path: str, params: dict = None, token: Optional[str] = None
    ) -> str:
        url = f"{self._base_api_url}{path}"
        try:
            async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
                async with session.get(
                    url, params=params, headers=self._headers(token)
                ) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    elif resp.status == 429:
                        retry_after = resp.headers.get("Retry-After", "30")
                        raise ClawHubError(429, f"Rate limited. Retry after {retry_after}s")
                    else:
                        text = await resp.text()
                        raise ClawHubError(resp.status, text[:500])
        except aiohttp.ClientError as e:
            raise ClawHubError(503, f"Connection error: {str(e)}")

    async def _get_bytes(
        self, path: str, params: dict = None, token: Optional[str] = None
    ) -> bytes:
        url = f"{self._base_api_url}{path}"
        try:
            async with aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session:
                async with session.get(
                    url, params=params, headers=self._headers(token)
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    elif resp.status == 429:
                        retry_after = resp.headers.get("Retry-After", "30")
                        raise ClawHubError(429, f"Rate limited. Retry after {retry_after}s")
                    else:
                        text = await resp.text()
                        raise ClawHubError(resp.status, text[:500])
        except aiohttp.ClientError as e:
            raise ClawHubError(503, f"Connection error: {str(e)}")
