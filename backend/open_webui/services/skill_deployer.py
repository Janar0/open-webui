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

        Returns the base directory path in the terminal (e.g., "skills/todoist-manager").
        """
        base_dir = f"skills/{self._sanitize_slug(skill_slug)}"
        # Extract ZIP contents
        try:
            files = self.extract_zip(zip_bytes)
        except Exception as e:
            raise SkillDeployError(f"Failed to extract skill archive: {e}")

        if not files:
            raise SkillDeployError("Skill archive is empty")

        # Write each file to terminal (reusing a single session)
        async with aiohttp.ClientSession(timeout=DEPLOY_TIMEOUT) as session:
            for rel_path, content in files.items():
                full_path = f"{base_dir}/{rel_path}"
                await self._write_file(
                    session, terminal_url, auth_headers, full_path, content
                )

            # Make scripts executable
            await self._execute(
                session,
                terminal_url,
                auth_headers,
                "find scripts -type f -exec chmod +x {} \\; 2>/dev/null; echo 'deployed'",
                cwd=base_dir,
            )

            # Install pip requirements if present
            if "requirements.txt" in files:
                await self._execute(
                    session,
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
        Raises SkillDeployError if any file write fails.
        """
        base_dir = f"skills/{self._sanitize_slug(skill_slug)}"
        written = 0

        async with aiohttp.ClientSession(timeout=DEPLOY_TIMEOUT) as session:
            for rel_path, content in files.items():
                # Validate relative path
                normalized = os.path.normpath(rel_path)
                if normalized.startswith("..") or os.path.isabs(normalized):
                    log.warning(f"Skipping unsafe path: {rel_path}")
                    continue
                full_path = f"{base_dir}/{normalized}"
                await self._write_file(
                    session, terminal_url, auth_headers, full_path, content
                )
                written += 1

            if written == 0:
                raise SkillDeployError(
                    "No files were written — all paths were unsafe or empty"
                )

            # Make scripts executable
            await self._execute(
                session,
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

        async with aiohttp.ClientSession(timeout=DEPLOY_TIMEOUT) as session:
            if "package.json" in files or "package-lock.json" in files:
                out = await self._execute(
                    session,
                    terminal_url,
                    auth_headers,
                    "npm install 2>&1 | tail -20",
                    cwd=base_dir,
                )
                if out is None:
                    results.append("npm install: FAILED (see server logs)")
                    log.warning(f"npm install failed in {base_dir}")
                else:
                    results.append(f"npm install: {out or 'done'}")

            if "requirements.txt" in files:
                out = await self._execute(
                    session,
                    terminal_url,
                    auth_headers,
                    "pip install -q -r requirements.txt 2>&1 | tail -10",
                    cwd=base_dir,
                )
                if out is None:
                    results.append("pip install: FAILED (see server logs)")
                    log.warning(f"pip install failed in {base_dir}")
                else:
                    results.append(f"pip install: {out or 'done'}")

        return results

    def extract_zip(self, zip_bytes: bytes) -> dict:
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
                    log.warning(
                        f"Skipping large file: {info.filename} ({info.file_size} bytes)"
                    )
                    continue
                # Skip binary files by extension
                ext = (
                    info.filename.rsplit(".", 1)[-1].lower()
                    if "." in info.filename
                    else ""
                )
                binary_exts = {
                    "png",
                    "jpg",
                    "jpeg",
                    "gif",
                    "ico",
                    "woff",
                    "woff2",
                    "ttf",
                    "otf",
                    "zip",
                    "tar",
                    "gz",
                }
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

    async def deploy_skill_md(
        self,
        terminal_url: str,
        auth_headers: dict,
        skill_slug: str,
        skill_content: str,
    ) -> str:
        """
        Create a skill directory and write SKILL.md to it.

        Used for skills that have no scripts but still need a folder on the terminal.
        Returns the base directory path.
        """
        base_dir = f"skills/{self._sanitize_slug(skill_slug)}"        async with aiohttp.ClientSession(timeout=DEPLOY_TIMEOUT) as session:
            await self._write_file(
                session,
                terminal_url,
                auth_headers,
                f"{base_dir}/SKILL.md",
                skill_content,
            )
        log.info(f"Deployed SKILL.md for {skill_slug} to terminal at {base_dir}")
        return base_dir

    async def _write_file(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict,
        path: str,
        content: str,
    ):
        """Write a file to terminal via open-terminal API (POST /files/write).

        Raises SkillDeployError on failure.
        """
        try:
            resp = await session.post(
                f"{url}/files/write",
                headers=headers,
                json={"path": path, "content": content},
            )
            if resp.status not in (200, 201):
                text = await resp.text()
                raise SkillDeployError(
                    f"Failed to write {path}: HTTP {resp.status} {text[:200]}"
                )
        except aiohttp.ClientError as e:
            raise SkillDeployError(f"Connection error writing {path}: {e}")

    async def _execute(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> Optional[str]:
        """Execute a command in terminal via open-terminal API (POST /execute?wait=30).

        Returns command output on success, None on failure.
        """
        payload: dict = {"command": command}
        if cwd:
            payload["cwd"] = cwd
        if env:
            payload["env"] = env
        try:
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
