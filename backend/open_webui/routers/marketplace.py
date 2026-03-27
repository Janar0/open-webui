"""
Marketplace router — proxy to ClawHub API + local installation management.

ClawHub token is stored as admin-level config, shared across all users.
"""

import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session
from open_webui.models.marketplace import (
    MarketplaceConfigForm,
    MarketplaceInstallForm,
    MarketplaceInstallResponse,
    MarketplaceInstallationModel,
    MarketplaceInstallations,
)
from open_webui.models.skills import SkillForm, SkillMeta, Skills
from open_webui.models.access_grants import AccessGrants
from open_webui.services.clawhub_client import ClawHubClient, ClawHubError
from open_webui.utils.skill_parser import parse_skill_md
from open_webui.utils.auth import get_verified_user, get_admin_user

log = logging.getLogger(__name__)

router = APIRouter()


def _get_clawhub_client(request: Request) -> ClawHubClient:
    clawhub_config = getattr(request.app.state.config, "CLAWHUB_API_URL", None)
    base_url = clawhub_config.value if clawhub_config and hasattr(clawhub_config, "value") else None
    if not base_url and clawhub_config:
        base_url = str(clawhub_config)
    if base_url:
        return ClawHubClient(base_url=base_url)
    return ClawHubClient()


def _get_clawhub_token(request: Request) -> Optional[str]:
    """Get ClawHub API token from admin config."""
    token_config = getattr(request.app.state.config, "CLAWHUB_API_TOKEN", None)
    if token_config and hasattr(token_config, "value"):
        return token_config.value or None
    return str(token_config) if token_config else None


def _check_marketplace_enabled(request: Request):
    """Raise 404 if marketplace feature is disabled."""
    enabled = getattr(request.app.state.config, "ENABLE_MARKETPLACE", None)
    is_enabled = enabled.value if enabled and hasattr(enabled, "value") else True
    if not is_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace feature is disabled.",
        )


def _get_terminal_connections(request: Request) -> list:
    """Get terminal server connections from config."""
    connections = getattr(request.app.state.config, "TERMINAL_SERVER_CONNECTIONS", None)
    if connections is None:
        return []
    if hasattr(connections, "value"):
        connections = connections.value or []
    return connections or []


def _find_terminal_connection(connections: list, terminal_id: str) -> Optional[dict]:
    """Find a terminal connection by ID, or the first enabled one if terminal_id is 'auto'."""
    if terminal_id == "auto":
        return next((c for c in connections if c.get("enabled", True)), None)
    return next((c for c in connections if c.get("id") == terminal_id), None)


def _build_terminal_headers(connection: dict, user_id: str) -> dict:
    """Build auth headers for communicating with an open-terminal server."""
    auth_type = connection.get("auth_type", "bearer")
    headers = {"Content-Type": "application/json", "X-User-Id": user_id}
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {connection.get('key', '')}"
    return headers


############################
# Admin Config
############################


class MarketplaceAdminConfig(BaseModel):
    ENABLE_MARKETPLACE: bool
    CLAWHUB_API_URL: str
    CLAWHUB_API_TOKEN: str


class MarketplaceAdminConfigUpdate(BaseModel):
    ENABLE_MARKETPLACE: Optional[bool] = None
    CLAWHUB_API_URL: Optional[str] = None
    CLAWHUB_API_TOKEN: Optional[str] = None


@router.get("/config")
async def get_marketplace_config(request: Request, user=Depends(get_admin_user)):
    """Get marketplace config (admin only)."""
    return {
        "ENABLE_MARKETPLACE": request.app.state.config.ENABLE_MARKETPLACE,
        "CLAWHUB_API_URL": request.app.state.config.CLAWHUB_API_URL,
        "CLAWHUB_API_TOKEN": request.app.state.config.CLAWHUB_API_TOKEN,
    }


@router.post("/config/update")
async def update_marketplace_config(
    request: Request,
    form_data: MarketplaceAdminConfigUpdate,
    user=Depends(get_admin_user),
):
    """Update marketplace config (admin only)."""
    if form_data.ENABLE_MARKETPLACE is not None:
        request.app.state.config.ENABLE_MARKETPLACE = form_data.ENABLE_MARKETPLACE
    if form_data.CLAWHUB_API_URL is not None:
        request.app.state.config.CLAWHUB_API_URL = form_data.CLAWHUB_API_URL
    if form_data.CLAWHUB_API_TOKEN is not None:
        # Verify the token if non-empty
        if form_data.CLAWHUB_API_TOKEN:
            client = _get_clawhub_client(request)
            try:
                await client.check_auth(form_data.CLAWHUB_API_TOKEN)
            except ClawHubError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid ClawHub token. Could not verify with ClawHub API.",
                )
        request.app.state.config.CLAWHUB_API_TOKEN = form_data.CLAWHUB_API_TOKEN

    return {
        "ENABLE_MARKETPLACE": request.app.state.config.ENABLE_MARKETPLACE,
        "CLAWHUB_API_URL": request.app.state.config.CLAWHUB_API_URL,
        "CLAWHUB_API_TOKEN": request.app.state.config.CLAWHUB_API_TOKEN,
    }


############################
# Auth status (lightweight)
############################


@router.get("/auth/status")
async def get_auth_status(
    request: Request,
    user=Depends(get_verified_user),
):
    """Check if marketplace has a ClawHub token configured (admin-level)."""
    token = _get_clawhub_token(request)
    return {"authenticated": bool(token)}


############################
# Catalog — proxy to ClawHub
############################


@router.get("/catalog")
async def search_catalog(
    request: Request,
    q: Optional[str] = "",
    cursor: Optional[str] = None,
    limit: Optional[int] = 30,
    non_suspicious_only: bool = False,
    user=Depends(get_verified_user),
):
    """Search or browse ClawHub skill catalog."""
    _check_marketplace_enabled(request)
    client = _get_clawhub_client(request)
    token = _get_clawhub_token(request)

    try:
        result = await client.search_skills(
            query=q or "",
            cursor=cursor,
            limit=limit or 30,
            non_suspicious_only=non_suspicious_only,
            token=token,
        )
        return result
    except ClawHubError as e:
        raise HTTPException(status_code=e.status or 502, detail=e.message)


@router.get("/catalog/{slug:path}/detail")
async def get_catalog_skill(
    slug: str,
    request: Request,
    user=Depends(get_verified_user),
):
    """Get skill details from ClawHub."""
    client = _get_clawhub_client(request)
    token = _get_clawhub_token(request)

    try:
        return await client.get_skill(slug, token=token)
    except ClawHubError as e:
        raise HTTPException(status_code=e.status or 502, detail=e.message)


@router.get("/catalog/{slug:path}/preview")
async def preview_skill(
    slug: str,
    request: Request,
    user=Depends(get_verified_user),
):
    """Get SKILL.md content preview from ClawHub."""
    client = _get_clawhub_client(request)
    token = _get_clawhub_token(request)

    try:
        content = await client.get_skill_file(slug, "SKILL.md", token=token)
        return {"content": content}
    except ClawHubError as e:
        raise HTTPException(status_code=e.status or 502, detail=e.message)


############################
# Install / Uninstall
############################


@router.post("/install", response_model=MarketplaceInstallResponse)
async def install_skill(
    form_data: MarketplaceInstallForm,
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Install a ClawHub skill: download SKILL.md and create local skill record."""
    _check_marketplace_enabled(request)
    client = _get_clawhub_client(request)
    token = _get_clawhub_token(request)

    # Check if already installed
    existing = MarketplaceInstallations.get_installation_by_user_and_slug(
        user.id, form_data.source, form_data.slug, db=db
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Skill already installed. Uninstall first to reinstall.",
        )

    # 1. Fetch skill metadata from ClawHub (already normalized/flat)
    try:
        skill_data = await client.get_skill(form_data.slug, token=token)
    except ClawHubError as e:
        raise HTTPException(
            status_code=e.status or 502,
            detail=f"Failed to fetch skill from ClawHub: {e.message}",
        )

    # 2. Download SKILL.md
    try:
        skill_content = await client.get_skill_file(
            form_data.slug, "SKILL.md", token=token
        )
    except ClawHubError as e:
        raise HTTPException(
            status_code=e.status or 502,
            detail=f"Failed to download SKILL.md: {e.message}",
        )

    # 3. Parse YAML frontmatter
    parsed = parse_skill_md(skill_content)

    # 4. Build unique skill ID for this user
    slug_safe = form_data.slug.replace("/", "-").replace(" ", "-").lower()
    skill_id = f"clawhub-{slug_safe}-{user.id[:8]}"

    # Check for ID collision (shouldn't happen but be safe)
    if Skills.get_skill_by_id(skill_id, db=db):
        skill_id = f"clawhub-{slug_safe}-{str(uuid4())[:8]}"

    # 5. Determine skill name (handle uniqueness constraint)
    skill_name = parsed.name or form_data.slug.split("/")[-1]
    if Skills.get_skill_by_name(skill_name, db=db):
        skill_name = f"{skill_name} (ClawHub)"
    if Skills.get_skill_by_name(skill_name, db=db):
        skill_name = f"{skill_name} [{user.id[:6]}]"

    version = skill_data.get("version") or parsed.version or "0.0.0"
    owner = skill_data.get("owner") or ""

    requires_env = parsed.requires.env
    requires_bins = parsed.requires.bins
    requires_any_bins = parsed.requires.any_bins

    # Classify skill execution type
    needs_sandbox = bool(requires_bins or requires_any_bins or parsed.requires.config)
    skill_type = "sandbox" if needs_sandbox else "prompt"

    # 6. Create local skill
    marketplace_meta = {
        "source": form_data.source,
        "slug": form_data.slug,
        "version": version,
        "requires_env": requires_env,
        "requires_bins": requires_bins,
        "requires_any_bins": requires_any_bins,
        "primary_env": parsed.primary_env,
        "emoji": parsed.emoji,
        "owner": owner,
        "skill_type": skill_type,
    }

    skill = Skills.insert_new_skill(
        user.id,
        SkillForm(
            id=skill_id,
            name=skill_name,
            description=parsed.description or skill_data.get("description", ""),
            content=parsed.instructions,
            meta=SkillMeta(tags=skill_data.get("tags", [])),
            is_active=True,
        ),
        db=db,
    )

    if not skill:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create local skill record.",
        )

    # Store marketplace metadata in skill.meta (update after creation)
    updated_meta = skill.meta.model_dump() if hasattr(skill.meta, "model_dump") else dict(skill.meta)
    updated_meta["marketplace"] = marketplace_meta
    Skills.update_skill_by_id(skill_id, {"meta": updated_meta}, db=db)

    # 7. Create installation record
    installation_id = str(uuid4())
    installation = MarketplaceInstallations.create_installation(
        id=installation_id,
        user_id=user.id,
        skill_id=skill_id,
        source=form_data.source,
        external_slug=form_data.slug,
        external_owner=owner,
        installed_version=version,
        meta=skill_data,
        db=db,
    )

    if not installation:
        # Rollback skill creation
        Skills.delete_skill_by_id(skill_id, db=db)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create installation record.",
        )

    # Download skill scripts for sandbox skills and auto-deploy to terminal
    has_scripts = False
    auto_deployed = False
    scripts_path = None
    if skill_type == "sandbox":
        from open_webui.services.skill_deployer import SkillDeployer, SkillDeployError

        deployer = SkillDeployer()
        connections = _get_terminal_connections(request)
        terminal = _find_terminal_connection(connections, "auto")

        try:
            zip_bytes = await client.download_skill(
                form_data.slug, version=version, token=token
            )
            if zip_bytes:
                script_files = deployer.extract_zip(zip_bytes)
                if script_files:
                    has_scripts = True
                    config = {"env": {}, "scripts": script_files, "scripts_deployed": False}

                    # Auto-deploy to first available terminal
                    if terminal:
                        try:
                            terminal_url = terminal.get("url", "")
                            headers = _build_terminal_headers(terminal, user.id)
                            scripts_path = await deployer.deploy_from_files(
                                terminal_url=terminal_url,
                                auth_headers=headers,
                                skill_slug=form_data.slug,
                                files=script_files,
                            )
                            # Run post-deploy setup (npm install, pip install, etc.)
                            await deployer.run_post_deploy_setup(
                                terminal_url, headers, scripts_path, script_files
                            )
                            config["scripts_path"] = scripts_path
                            config["scripts_deployed"] = True
                            config["deployed_terminal_id"] = terminal.get("id")
                            auto_deployed = True
                            log.info(f"Auto-deployed skill {form_data.slug} to terminal at {scripts_path}")
                        except Exception as e:
                            log.warning(f"Auto-deploy failed for {form_data.slug}: {e}")

                    MarketplaceInstallations.update_installation_config(
                        installation_id, config, db=db
                    )
        except Exception as e:
            log.warning(f"Failed to download skill scripts for {form_data.slug}: {e}")

        # Even without scripts, create the skill folder with SKILL.md on the terminal
        if not has_scripts and terminal:
            try:
                terminal_url = terminal.get("url", "")
                headers = _build_terminal_headers(terminal, user.id)
                scripts_path = await deployer.deploy_skill_md(
                    terminal_url=terminal_url,
                    auth_headers=headers,
                    skill_slug=form_data.slug,
                    skill_content=skill_content,
                )
                auto_deployed = True
                config = installation.config or {}
                config["scripts_path"] = scripts_path
                config["scripts_deployed"] = True
                config["deployed_terminal_id"] = terminal.get("id")
                MarketplaceInstallations.update_installation_config(
                    installation_id, config, db=db
                )
                log.info(f"Deployed SKILL.md for {form_data.slug} to terminal at {scripts_path}")
            except SkillDeployError as e:
                log.warning(f"Failed to deploy SKILL.md for {form_data.slug}: {e}")
            except Exception as e:
                log.warning(f"Unexpected error deploying SKILL.md for {form_data.slug}: {e}")

    # Build installation warnings
    warnings = []
    if requires_bins:
        if has_scripts and auto_deployed:
            warnings.append(
                f"Scripts deployed to terminal at {scripts_path}. "
                f"Required CLI tools: {', '.join(requires_bins)}."
            )
        elif has_scripts:
            warnings.append(
                f"This skill has scripts that require CLI tools ({', '.join(requires_bins)}). "
                "Deploy them to your terminal using the 'Deploy to Terminal' button."
            )
        else:
            warnings.append(
                f"This skill requires CLI tools ({', '.join(requires_bins)}) "
                "but no scripts were found in the skill archive."
            )
    if requires_any_bins:
        warnings.append(
            f"This skill requires one of: {', '.join(requires_any_bins)}. "
            "Execution capabilities are limited without a sandbox environment."
        )
    if requires_env:
        warnings.append(
            f"This skill requires API credentials: {', '.join(requires_env)}. "
            "Configure them in the skill settings after installation."
        )

    return MarketplaceInstallResponse(
        installation_id=installation_id,
        skill_id=skill_id,
        name=skill_name,
        description=parsed.description,
        requires_env=requires_env,
        requires_bins=requires_bins,
        skill_type=skill_type,
        warnings=warnings,
        auto_deployed=auto_deployed,
        scripts_path=scripts_path,
        install_steps=parsed.install_steps,
        skill_content=parsed.instructions,
    )


@router.delete("/installations/{installation_id}")
async def uninstall_skill(
    installation_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Uninstall a marketplace skill: remove local skill and installation record."""
    installation = MarketplaceInstallations.get_installation_by_id(
        installation_id, db=db
    )
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Installation not found.",
        )

    if installation.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to uninstall this skill.",
        )

    # Delete local skill
    Skills.delete_skill_by_id(installation.skill_id, db=db)

    # Delete installation record
    MarketplaceInstallations.delete_installation(installation_id, db=db)

    return {"status": "ok", "message": "Skill uninstalled successfully."}


############################
# Installations — per-user
############################


@router.get("/installations", response_model=list[MarketplaceInstallationModel])
async def get_installations(
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """List user's installed marketplace skills."""
    return MarketplaceInstallations.get_installations_by_user_id(user.id, db=db)


@router.get("/installations/{installation_id}", response_model=MarketplaceInstallationModel)
async def get_installation(
    installation_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Get a specific installation."""
    installation = MarketplaceInstallations.get_installation_by_id(
        installation_id, db=db
    )
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found."
        )
    if installation.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized."
        )
    return installation


############################
# Per-user configuration
############################


@router.put("/installations/{installation_id}/config")
async def update_installation_config(
    installation_id: str,
    form_data: MarketplaceConfigForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Update per-user configuration (env vars) for an installed skill."""
    installation = MarketplaceInstallations.get_installation_by_id(
        installation_id, db=db
    )
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found."
        )
    if installation.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized."
        )

    config = installation.config or {}
    config["env"] = form_data.env
    result = MarketplaceInstallations.update_installation_config(
        installation_id, config, db=db
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update config.",
        )

    return {"status": "ok", "config": config}


@router.get("/installations/{installation_id}/config/spec")
async def get_installation_config_spec(
    installation_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """
    Get the config spec for a marketplace skill (required env vars).
    Returns JSON Schema-like spec for dynamic form rendering.
    """
    installation = MarketplaceInstallations.get_installation_by_id(
        installation_id, db=db
    )
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found."
        )
    if installation.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized."
        )

    # Get skill to read marketplace meta
    skill = Skills.get_skill_by_id(installation.skill_id, db=db)
    if not skill:
        return {"properties": {}, "required": []}

    meta = skill.meta
    if hasattr(meta, "model_dump"):
        meta = meta.model_dump()
    marketplace = meta.get("marketplace", {}) if isinstance(meta, dict) else {}
    requires_env = marketplace.get("requires_env", [])
    primary_env = marketplace.get("primary_env")

    # Build JSON Schema-like spec
    properties = {}
    required = []
    for env_var in requires_env:
        properties[env_var] = {
            "type": "string",
            "title": env_var,
            "description": f"{'Primary API key' if env_var == primary_env else 'Required'} for this skill",
        }
        required.append(env_var)

    # Include current values (masked)
    current_env = (installation.config or {}).get("env", {})
    values = {}
    for key in requires_env:
        val = current_env.get(key, "")
        if val and len(val) > 4:
            values[key] = val[:4] + "..." + val[-2:]
        else:
            values[key] = val

    return {
        "properties": properties,
        "required": required,
        "current_values": values,
    }


############################
# Deploy to Terminal
############################


class DeployForm(BaseModel):
    terminal_id: str


@router.post("/installations/{installation_id}/deploy")
async def deploy_to_terminal(
    installation_id: str,
    form_data: DeployForm,
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Deploy skill scripts to user's open-terminal instance."""
    installation = MarketplaceInstallations.get_installation_by_id(
        installation_id, db=db
    )
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found."
        )
    if installation.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized."
        )

    # Check that scripts exist in config
    config = installation.config or {}
    scripts = config.get("scripts")
    if not scripts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No scripts found for this skill. Re-install to download scripts.",
        )

    # Find terminal connection (supports "auto" to pick first available)
    connections = _get_terminal_connections(request)
    connection = _find_terminal_connection(connections, form_data.terminal_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Terminal server not found. Configure a terminal in Admin > Integrations.",
        )

    # Check user has access to this terminal (skip for "auto" — admin configured)
    if form_data.terminal_id != "auto":
        from open_webui.models.groups import Groups
        from open_webui.utils.access_control import has_connection_access

        user_group_ids = {group.id for group in Groups.get_groups_by_member_id(user.id, db=db)}
        if not has_connection_access(user, connection, user_group_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this terminal.",
            )

    # Build auth headers and deploy
    terminal_url = connection.get("url", "")
    headers = _build_terminal_headers(connection, user.id)

    from open_webui.services.skill_deployer import SkillDeployer

    deployer = SkillDeployer()
    try:
        scripts_path = await deployer.deploy_from_files(
            terminal_url=terminal_url,
            auth_headers=headers,
            skill_slug=installation.external_slug,
            files=scripts,
        )
        # Run post-deploy setup (npm install, pip install, etc.)
        await deployer.run_post_deploy_setup(
            terminal_url, headers, scripts_path, scripts
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deploy scripts: {str(e)}",
        )

    # Update config with deployment info
    actual_terminal_id = form_data.terminal_id if form_data.terminal_id != "auto" else connection.get("id", "auto")
    config["scripts_path"] = scripts_path
    config["scripts_deployed"] = True
    config["deployed_terminal_id"] = actual_terminal_id
    MarketplaceInstallations.update_installation_config(
        installation_id, config, db=db
    )

    return {
        "status": "ok",
        "scripts_path": scripts_path,
        "terminal_id": actual_terminal_id,
    }


############################
# Updates
############################


@router.post("/installations/{installation_id}/check-update")
async def check_update(
    installation_id: str,
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Check if a newer version is available on ClawHub."""
    installation = MarketplaceInstallations.get_installation_by_id(
        installation_id, db=db
    )
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found."
        )
    if installation.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized."
        )

    client = _get_clawhub_client(request)
    token = _get_clawhub_token(request)

    try:
        skill_data = await client.get_skill(installation.external_slug, token=token)
    except ClawHubError as e:
        raise HTTPException(
            status_code=e.status or 502, detail=f"Failed to check update: {e.message}"
        )

    latest_version = skill_data.get("version", installation.installed_version)
    MarketplaceInstallations.update_latest_version(
        installation_id, latest_version, db=db
    )

    has_update = latest_version != installation.installed_version

    return {
        "has_update": has_update,
        "installed_version": installation.installed_version,
        "latest_version": latest_version,
    }


@router.post("/installations/{installation_id}/update")
async def update_skill_version(
    installation_id: str,
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """Update an installed skill to the latest version from ClawHub."""
    installation = MarketplaceInstallations.get_installation_by_id(
        installation_id, db=db
    )
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found."
        )
    if installation.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized."
        )

    client = _get_clawhub_client(request)
    token = _get_clawhub_token(request)

    # Download fresh content
    try:
        skill_content = await client.get_skill_file(
            installation.external_slug, "SKILL.md", token=token
        )
        skill_data = await client.get_skill(installation.external_slug, token=token)
    except ClawHubError as e:
        raise HTTPException(
            status_code=e.status or 502, detail=f"Failed to fetch update: {e.message}"
        )

    parsed = parse_skill_md(skill_content)
    new_version = skill_data.get("version") or parsed.version or "0.0.0"

    # Update local skill content
    skill = Skills.get_skill_by_id(installation.skill_id, db=db)
    if skill:
        meta = skill.meta
        if hasattr(meta, "model_dump"):
            meta = meta.model_dump()
        marketplace = meta.get("marketplace", {}) if isinstance(meta, dict) else {}
        marketplace["version"] = new_version
        marketplace["requires_env"] = parsed.requires.env
        marketplace["requires_bins"] = parsed.requires.bins
        marketplace["primary_env"] = parsed.primary_env
        marketplace["emoji"] = parsed.emoji

        if isinstance(meta, dict):
            meta["marketplace"] = marketplace
        else:
            meta = {"marketplace": marketplace}

        Skills.update_skill_by_id(
            installation.skill_id,
            {
                "content": parsed.instructions,
                "description": parsed.description or skill_data.get("description", ""),
                "meta": meta,
            },
            db=db,
        )

    # Update installation version
    MarketplaceInstallations.update_installation_version(
        installation_id, new_version, db=db
    )

    return {
        "status": "ok",
        "installed_version": new_version,
    }
