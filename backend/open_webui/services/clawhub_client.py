"""
HTTP client for ClawHub.ai API v1.

Proxies requests from OpenWebUI backend to ClawHub, handling auth and rate limiting.
All public methods return normalized/flattened dicts so callers don't need to know
the raw API nesting.

API reference:
- Search:   GET /api/v1/search?q=...
- List:     GET /api/v1/skills?limit=&cursor=
- Detail:   GET /api/v1/skills/{slug}
- File:     GET /api/v1/skills/{slug}/file?path=&version=
- Download: GET /api/v1/download?slug=&version=
- Versions: GET /api/v1/skills/{slug}/versions?limit=&cursor=
- Scan:     GET /api/v1/skills/{slug}/scan?version=
- Auth:     GET /api/v1/whoami
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
    def __init__(
        self, base_url: str = "https://clawhub.ai", api_prefix: str = "/api/v1"
    ):
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

    # ── Response normalizers ──────────────────────────────────────────

    @staticmethod
    def _normalize_search_item(item: dict) -> dict:
        """Normalize a SearchResult into the unified catalog item shape."""
        return {
            "slug": item.get("slug"),
            "name": item.get("displayName"),
            "description": item.get("summary"),
            "version": item.get("version"),
            "updatedAt": item.get("updatedAt"),
            "score": item.get("score"),
            "tags": [],
            "stats": {},
            "downloads": 0,
            "installs": 0,
            "owner": "",
        }

    @staticmethod
    def _normalize_list_item(item: dict) -> dict:
        """Normalize a SkillListItem into the unified catalog item shape."""
        latest = item.get("latestVersion") or {}
        tags = item.get("tags") or {}
        stats = item.get("stats") or {}
        return {
            "slug": item.get("slug"),
            "name": item.get("displayName"),
            "description": item.get("summary"),
            "version": latest.get("version"),
            "tags": list(tags.keys()) if isinstance(tags, dict) else tags,
            "stats": stats,
            "downloads": stats.get("downloads", 0),
            "installs": stats.get("installs", 0),
            "updatedAt": item.get("updatedAt"),
            "createdAt": item.get("createdAt"),
            "owner": "",
        }

    @staticmethod
    def _normalize_skill_detail(data: dict) -> dict:
        """Flatten nested SkillResponse into a flat dict."""
        skill = data.get("skill") or {}
        latest = data.get("latestVersion") or {}
        owner_data = data.get("owner") or {}
        tags = skill.get("tags") or {}
        stats = skill.get("stats") or {}
        return {
            "slug": skill.get("slug"),
            "name": skill.get("displayName"),
            "description": skill.get("summary"),
            "tags": list(tags.keys()) if isinstance(tags, dict) else tags,
            "stats": stats,
            "downloads": stats.get("downloads", 0),
            "installs": stats.get("installs", 0),
            "version": latest.get("version"),
            "changelog": latest.get("changelog"),
            "owner": owner_data.get("handle", ""),
            "owner_display": owner_data.get("displayName", ""),
            "owner_image": owner_data.get("image"),
            "createdAt": skill.get("createdAt"),
            "updatedAt": skill.get("updatedAt"),
        }

    @staticmethod
    def _normalize_whoami(data: dict) -> dict:
        """Flatten nested WhoamiResponse."""
        user = data.get("user") or {}
        return {
            "username": user.get("handle", ""),
            "display_name": user.get("displayName", ""),
            "image": user.get("image", ""),
        }

    # ── Search & Browse ────────────────────────────────────────────────

    async def search_skills(
        self,
        query: str = "",
        cursor: Optional[str] = None,
        limit: int = 30,
        highlighted_only: bool = False,
        non_suspicious_only: bool = False,
        token: Optional[str] = None,
    ) -> dict:
        """
        Search or list ClawHub skill catalog.

        Returns normalized ``{items: [...], nextCursor: str}``.
        """
        if query:
            params = {"q": query}
            if highlighted_only:
                params["highlightedOnly"] = "true"
            if non_suspicious_only:
                params["nonSuspiciousOnly"] = "true"
            raw = await self._request("/search", params=params, token=token)
            items = [self._normalize_search_item(r) for r in raw.get("results", [])]
            return {"items": items, "nextCursor": ""}
        else:
            params = {"limit": str(limit)}
            if cursor:
                params["cursor"] = cursor
            if non_suspicious_only:
                params["nonSuspiciousOnly"] = "true"
            raw = await self._request("/skills", params=params, token=token)
            items = [self._normalize_list_item(s) for s in raw.get("items", [])]
            return {"items": items, "nextCursor": raw.get("nextCursor", "")}

    async def get_skill(self, slug: str, token: Optional[str] = None) -> dict:
        """Get skill details by slug. Returns a flat normalized dict."""
        raw = await self._request(f"/skills/{slug}", token=token)
        return self._normalize_skill_detail(raw)

    async def get_skill_versions(
        self,
        slug: str,
        limit: int = 10,
        cursor: Optional[str] = None,
        token: Optional[str] = None,
    ) -> dict:
        """Get version history for a skill."""
        params = {"limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        return await self._request(
            f"/skills/{slug}/versions", params=params, token=token
        )

    # ── Files & Download ───────────────────────────────────────────────

    async def get_skill_file(
        self,
        slug: str,
        path: str = "SKILL.md",
        version: Optional[str] = None,
        token: Optional[str] = None,
    ) -> str:
        """Get a file from a skill (typically SKILL.md). Returns raw text content."""
        params = {"path": path}
        if version:
            params["version"] = version
        return await self._request(
            f"/skills/{slug}/file", params=params, token=token, response_type="text"
        )

    async def download_skill(
        self,
        slug: str,
        version: Optional[str] = None,
        token: Optional[str] = None,
    ) -> bytes:
        """Download full skill archive (ZIP). Returns raw bytes."""
        params = {"slug": slug}
        if version:
            params["version"] = version
        return await self._request(
            "/download",
            params=params,
            token=token,
            timeout=DOWNLOAD_TIMEOUT,
            response_type="bytes",
        )

    async def get_skill_scan(
        self,
        slug: str,
        version: Optional[str] = None,
        token: Optional[str] = None,
    ) -> dict:
        """Get security scan results for a skill."""
        params = {}
        if version:
            params["version"] = version
        return await self._request(f"/skills/{slug}/scan", params=params, token=token)

    # ── Auth ───────────────────────────────────────────────────────────

    async def check_auth(self, token: str) -> dict:
        """Verify a ClawHub API token. Returns normalized user info."""
        raw = await self._request("/whoami", token=token)
        return self._normalize_whoami(raw)

    # ── HTTP primitives ────────────────────────────────────────────────

    async def _request(
        self,
        path: str,
        params: dict = None,
        token: Optional[str] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        response_type: str = "json",
    ):
        """
        Unified HTTP GET with error handling.

        response_type: "json" (dict), "text" (str), or "bytes" (bytes).
        """
        url = f"{self._base_api_url}{path}"
        try:
            async with aiohttp.ClientSession(
                timeout=timeout or DEFAULT_TIMEOUT
            ) as session:
                async with session.get(
                    url, params=params, headers=self._headers(token)
                ) as resp:
                    if resp.status == 200:
                        if response_type == "text":
                            return await resp.text()
                        elif response_type == "bytes":
                            return await resp.read()
                        return await resp.json()
                    elif resp.status == 429:
                        retry_after = resp.headers.get("Retry-After", "30")
                        raise ClawHubError(
                            429, f"Rate limited. Retry after {retry_after}s"
                        )
                    else:
                        text = await resp.text()
                        raise ClawHubError(resp.status, text[:500])
        except aiohttp.ClientError as e:
            raise ClawHubError(503, f"Connection error: {str(e)}")
