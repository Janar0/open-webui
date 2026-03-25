"""
HTTP client for ClawHub.ai API.

Proxies requests from OpenWebUI backend to ClawHub, handling auth, caching, and rate limiting.
"""

import logging
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)


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

    async def search_skills(
        self,
        query: str = "",
        page: int = 1,
        category: Optional[str] = None,
        token: Optional[str] = None,
    ) -> dict:
        """
        Search ClawHub skill catalog.
        Returns the JSON response from ClawHub API.
        """
        params = {}
        if query:
            params["q"] = query
        if page and page > 1:
            params["page"] = str(page)
        if category:
            params["category"] = category

        return await self._get("/skills", params=params, token=token)

    async def get_skill(self, slug: str, token: Optional[str] = None) -> dict:
        """Get skill details by slug (e.g., 'peter/todoist-manager')."""
        return await self._get(f"/skills/{slug}", token=token)

    async def get_skill_file(
        self, slug: str, path: str = "SKILL.md", token: Optional[str] = None
    ) -> str:
        """Get a file from a skill (typically SKILL.md). Returns raw text content."""
        return await self._get_text(
            f"/skills/{slug}/file", params={"path": path}, token=token
        )

    async def get_categories(self, token: Optional[str] = None) -> list:
        """Get available skill categories."""
        try:
            result = await self._get("/categories", token=token)
            return result if isinstance(result, list) else []
        except ClawHubError:
            # Categories endpoint may not exist, return empty
            return []

    async def check_auth(self, token: str) -> dict:
        """Verify a ClawHub API token. Returns user info."""
        return await self._get("/whoami", token=token)

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
                    else:
                        text = await resp.text()
                        raise ClawHubError(resp.status, text[:500])
        except aiohttp.ClientError as e:
            raise ClawHubError(503, f"Connection error: {str(e)}")
