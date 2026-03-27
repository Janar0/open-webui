"""
Deploys ClawHub skill scripts to an open-terminal instance.

Uses the open-terminal HTTP API (POST /files/write, POST /execute) to:
1. Write skill scripts into the terminal's workspace
2. Make scripts executable
3. Optionally install pip dependencies
"""

import io
import logging
import os
import re
import zipfile
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

DEPLOY_TIMEOUT = aiohttp.ClientTimeout(total=60)


class SkillDeployError(Exception):
    pass


class SkillDeployer:
    """Deploys skill scripts to an open-terminal server."""

    @staticmethod
    def _sanitize_slug(slug: str) -> str:
        """Sanitize a skill slug to be safe for filesystem paths and shell commands."""
        # Replace / with -, then strip anything that's not alphanumeric, dash, dot, or underscore
        safe = slug.replace("/", "-")
        safe = re.sub(r"[^a-zA-Z0-9._-]", "", safe)
        # Remove leading dots/dashes to prevent hidden files or option injection
        safe = safe.lstrip(".-")
        return safe or "unknown-skill"

    async def deploy_from_zip(
        self,
        terminal_url: str,
        auth_headers: dict,
        skill_slug: str,
        zip_bytes: bytes,
    ) -> str:
        """
        Extract a skill ZIP archive and write files to terminal.

        Returns the base directory path in the terminal (e.g., "clawhub-skills/todoist-manager").
        """
        base_dir = f"clawhub-skills/{self._sanitize_slug(skill_slug)}"

        # Extract ZIP contents
        try:
            files = self._extract_zip(zip_bytes)
        except Exception as e:
            raise SkillDeployError(f"Failed to extract skill archive: {e}")

        if not files:
            raise SkillDeployError("Skill archive is empty")

        # Write each file to terminal
        for rel_path, content in files.items():
            full_path = f"{base_dir}/{rel_path}"
            await self._write_file(terminal_url, auth_headers, full_path, content)

        # Make scripts executable
        await self._execute(
            terminal_url,
            auth_headers,
            "find scripts -type f -exec chmod +x {} \\; 2>/dev/null; echo 'deployed'",
            cwd=base_dir,
        )

        # Install pip requirements if present
        if "requirements.txt" in files:
            await self._execute(
                terminal_url,
                auth_headers,
                "pip install -q -r requirements.txt 2>&1 | tail -5",
                cwd=base_dir,
            )

        log.info(f"Deployed skill {skill_slug} to terminal at {base_dir}")
        return base_dir

    async def deploy_from_files(
        self,
        terminal_url: str,
        auth_headers: dict,
        skill_slug: str,
        files: dict,
    ) -> str:
        """
        Deploy individual files (from stored config) to terminal.

        files: {"scripts/main.py": "content...", "scripts/helper.sh": "content..."}
        Returns base directory path.
        """
        base_dir = f"clawhub-skills/{self._sanitize_slug(skill_slug)}"

        for rel_path, content in files.items():
            # Validate relative path
            normalized = os.path.normpath(rel_path)
            if normalized.startswith("..") or os.path.isabs(normalized):
                log.warning(f"Skipping unsafe path: {rel_path}")
                continue
            full_path = f"{base_dir}/{normalized}"
            await self._write_file(terminal_url, auth_headers, full_path, content)

        # Make scripts executable
        await self._execute(
            terminal_url,
            auth_headers,
            "find . -name '*.sh' -o -name '*.py' | xargs chmod +x 2>/dev/null; echo 'ok'",
            cwd=base_dir,
        )

        return base_dir

    async def run_post_deploy_setup(
        self,
        terminal_url: str,
        auth_headers: dict,
        base_dir: str,
        files: dict,
    ) -> list[str]:
        """
        Run post-deploy setup commands (npm install, pip install, etc.).

        Returns a list of setup result messages.
        """
        results = []

        if "package.json" in files or "package-lock.json" in files:
            out = await self._execute(
                terminal_url,
                auth_headers,
                "npm install 2>&1 | tail -20",
                cwd=base_dir,
            )
            results.append(f"npm install: {out or 'done'}")

        if "requirements.txt" in files:
            out = await self._execute(
                terminal_url,
                auth_headers,
                "pip install -q -r requirements.txt 2>&1 | tail -10",
                cwd=base_dir,
            )
            results.append(f"pip install: {out or 'done'}")

        return results

    def _extract_zip(self, zip_bytes: bytes) -> dict:
        """Extract ZIP to dict of {relative_path: text_content}."""
        files = {}
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                # Prevent path traversal (zip slip)
                normalized = os.path.normpath(info.filename)
                if normalized.startswith("..") or os.path.isabs(normalized):
                    log.warning(f"Skipping unsafe zip entry: {info.filename}")
                    continue
                # Skip very large files (>1MB)
                if info.file_size > 1_000_000:
                    log.warning(f"Skipping large file: {info.filename} ({info.file_size} bytes)")
                    continue
                # Skip binary files by extension
                ext = info.filename.rsplit(".", 1)[-1].lower() if "." in info.filename else ""
                binary_exts = {"png", "jpg", "jpeg", "gif", "ico", "woff", "woff2", "ttf", "otf", "zip", "tar", "gz"}
                if ext in binary_exts:
                    continue

                try:
                    content = zf.read(info.filename).decode("utf-8")
                    # Strip leading directory if all files share common prefix
                    files[info.filename] = content
                except UnicodeDecodeError:
                    log.debug(f"Skipping binary file: {info.filename}")
                    continue

        # Strip common prefix (e.g., "skill-name/scripts/main.py" -> "scripts/main.py")
        if files:
            paths = list(files.keys())
            parts = paths[0].split("/")
            prefix_len = 0
            for i in range(len(parts) - 1):
                candidate = "/".join(parts[: i + 1]) + "/"
                if all(p.startswith(candidate) for p in paths):
                    prefix_len = len(candidate)
                else:
                    break
            if prefix_len > 0:
                files = {k[prefix_len:]: v for k, v in files.items() if k[prefix_len:]}

        return files

    async def _write_file(self, url: str, headers: dict, path: str, content: str):
        """Write a file to terminal via open-terminal API (POST /files/write)."""
        try:
            async with aiohttp.ClientSession(timeout=DEPLOY_TIMEOUT) as session:
                resp = await session.post(
                    f"{url}/files/write",
                    headers=headers,
                    json={"path": path, "content": content},
                )
                if resp.status not in (200, 201):
                    text = await resp.text()
                    log.warning(f"write_file failed for {path}: {resp.status} {text[:200]}")
        except aiohttp.ClientError as e:
            log.warning(f"write_file connection error for {path}: {e}")

    async def _execute(
        self,
        url: str,
        headers: dict,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> Optional[str]:
        """Execute a command in terminal via open-terminal API (POST /execute?wait=30)."""
        payload: dict = {"command": command}
        if cwd:
            payload["cwd"] = cwd
        if env:
            payload["env"] = env
        try:
            async with aiohttp.ClientSession(timeout=DEPLOY_TIMEOUT) as session:
                resp = await session.post(
                    f"{url}/execute",
                    params={"wait": "30"},
                    headers=headers,
                    json=payload,
                )
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("output", "")
                else:
                    text = await resp.text()
                    log.warning(f"execute failed: {resp.status} {text[:200]}")
                    return None
        except aiohttp.ClientError as e:
            log.warning(f"execute connection error: {e}")
            return None
