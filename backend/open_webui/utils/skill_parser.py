"""
Utility for parsing ClawHub SKILL.md files with YAML frontmatter.
"""

import re
import logging
from typing import Optional

import yaml
from pydantic import BaseModel

log = logging.getLogger(__name__)


class SkillRequirements(BaseModel):
    env: list[str] = []
    bins: list[str] = []
    any_bins: list[str] = []
    config: list[str] = []


class SkillMetadata(BaseModel):
    name: str = ""
    description: str = ""
    version: str = "0.0.0"
    homepage: Optional[str] = None
    emoji: Optional[str] = None
    primary_env: Optional[str] = None
    requires: SkillRequirements = SkillRequirements()
    install_steps: list[dict] = []
    instructions: str = ""  # The markdown body (without frontmatter)
    raw_frontmatter: dict = {}


def parse_skill_md(content: str) -> SkillMetadata:
    """
    Parse a SKILL.md file: extract YAML frontmatter and markdown body.

    Expected format:
    ---
    name: my-skill
    description: ...
    version: 1.0.0
    metadata:
      openclaw:
        requires:
          env: [API_KEY]
          bins: [curl]
        primaryEnv: API_KEY
        emoji: "✅"
    ---
    # Markdown instructions here...
    """
    frontmatter, body = _split_frontmatter(content)

    if not frontmatter:
        return SkillMetadata(
            name="unknown",
            instructions=content,
        )

    # Extract openclaw/clawdbot/clawdis metadata block
    meta_block = {}
    metadata_section = frontmatter.get("metadata", {})
    if isinstance(metadata_section, dict):
        for key in ("openclaw", "clawdbot", "clawdis"):
            if key in metadata_section:
                meta_block = metadata_section[key]
                break

    requires_raw = meta_block.get("requires", {})
    if not isinstance(requires_raw, dict):
        requires_raw = {}

    requires = SkillRequirements(
        env=requires_raw.get("env", []) or [],
        bins=requires_raw.get("bins", []) or [],
        any_bins=requires_raw.get("anyBins", []) or [],
        config=requires_raw.get("config", []) or [],
    )

    install_steps = meta_block.get("install", []) or []
    if not isinstance(install_steps, list):
        install_steps = []

    return SkillMetadata(
        name=frontmatter.get("name", "unknown"),
        description=frontmatter.get("description", ""),
        version=frontmatter.get("version", "0.0.0"),
        homepage=frontmatter.get("homepage"),
        emoji=meta_block.get("emoji"),
        primary_env=meta_block.get("primaryEnv"),
        requires=requires,
        install_steps=install_steps,
        instructions=body.strip(),
        raw_frontmatter=frontmatter,
    )


def _split_frontmatter(content: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body. Returns (frontmatter_dict, body_str)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    try:
        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            return {}, content
    except yaml.YAMLError as e:
        log.warning(f"Failed to parse SKILL.md frontmatter: {e}")
        return {}, content

    return frontmatter, match.group(2)


def check_eligibility(
    skill: SkillMetadata,
    user_env_keys: set[str],
) -> tuple[bool, list[str]]:
    """
    Check if a skill's requirements are satisfied by the user's configured env vars.
    Returns (eligible, list_of_missing_items).
    """
    missing = []

    for env_var in skill.requires.env:
        if env_var not in user_env_keys:
            missing.append(f"Missing env var: {env_var}")

    return (len(missing) == 0, missing)
