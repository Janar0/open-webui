"""
Marketplace installation tracking for ClawHub skills.
"""

import logging
import time
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Session

from open_webui.internal.db import Base, JSONField, get_db_context
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


####################
# MarketplaceInstallation DB Schema
####################


class MarketplaceInstallation(Base):
    __tablename__ = "marketplace_installation"

    id = Column(Text, primary_key=True)
    user_id = Column(Text, nullable=False)
    skill_id = Column(Text, nullable=False)
    source = Column(Text, nullable=False, default="clawhub")
    external_slug = Column(Text, nullable=False)
    external_owner = Column(Text, nullable=True)
    installed_version = Column(Text, nullable=False)
    latest_version = Column(Text, nullable=True)
    auto_update = Column(Boolean, default=False)
    config = Column(JSONField, default=dict)
    meta = Column(JSONField, default=dict)

    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)

    __table_args__ = (
        UniqueConstraint("user_id", "source", "external_slug", name="uq_user_source_slug"),
    )


####################
# Pydantic Models
####################


class MarketplaceInstallationModel(BaseModel):
    id: str
    user_id: str
    skill_id: str
    source: str = "clawhub"
    external_slug: str
    external_owner: Optional[str] = None
    installed_version: str
    latest_version: Optional[str] = None
    auto_update: bool = False
    config: dict = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)
    updated_at: int
    created_at: int

    model_config = ConfigDict(from_attributes=True)


class MarketplaceInstallForm(BaseModel):
    slug: str = Field(..., pattern=r"^[a-zA-Z0-9._/@-]+$", min_length=1, max_length=500)
    source: str = "clawhub"


class MarketplaceConfigForm(BaseModel):
    env: dict = Field(default_factory=dict)  # {"API_KEY": "value", ...}


class MarketplaceInstallResponse(BaseModel):
    installation_id: str
    skill_id: str
    name: str
    description: Optional[str] = None
    requires_env: list[str] = []
    requires_bins: list[str] = []
    skill_type: str = "prompt"  # "prompt" (text-only) or "sandbox" (needs execution)
    warnings: list[str] = []
    auto_deployed: bool = False
    scripts_path: Optional[str] = None


####################
# Table Operations
####################


class MarketplaceInstallationsTable:
    def create_installation(
        self,
        id: str,
        user_id: str,
        skill_id: str,
        source: str,
        external_slug: str,
        external_owner: Optional[str],
        installed_version: str,
        meta: Optional[dict] = None,
        db: Optional[Session] = None,
    ) -> Optional[MarketplaceInstallationModel]:
        with get_db_context(db) as db:
            try:
                now = int(time.time())
                installation = MarketplaceInstallation(
                    id=id,
                    user_id=user_id,
                    skill_id=skill_id,
                    source=source,
                    external_slug=external_slug,
                    external_owner=external_owner,
                    installed_version=installed_version,
                    meta=meta or {},
                    config={},
                    updated_at=now,
                    created_at=now,
                )
                db.add(installation)
                db.commit()
                db.refresh(installation)
                return MarketplaceInstallationModel.model_validate(installation)
            except Exception as e:
                log.exception(f"Error creating marketplace installation: {e}")
                return None

    def get_installation_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[MarketplaceInstallationModel]:
        with get_db_context(db) as db:
            installation = db.get(MarketplaceInstallation, id)
            if installation:
                return MarketplaceInstallationModel.model_validate(installation)
            return None

    def get_installation_by_skill_id(
        self, skill_id: str, db: Optional[Session] = None
    ) -> Optional[MarketplaceInstallationModel]:
        with get_db_context(db) as db:
            installation = (
                db.query(MarketplaceInstallation)
                .filter_by(skill_id=skill_id)
                .first()
            )
            if installation:
                return MarketplaceInstallationModel.model_validate(installation)
            return None

    def get_installations_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> list[MarketplaceInstallationModel]:
        with get_db_context(db) as db:
            installations = (
                db.query(MarketplaceInstallation)
                .filter_by(user_id=user_id)
                .order_by(MarketplaceInstallation.created_at.desc())
                .all()
            )
            return [
                MarketplaceInstallationModel.model_validate(i) for i in installations
            ]

    def get_installation_by_user_and_slug(
        self, user_id: str, source: str, external_slug: str, db: Optional[Session] = None
    ) -> Optional[MarketplaceInstallationModel]:
        with get_db_context(db) as db:
            installation = (
                db.query(MarketplaceInstallation)
                .filter_by(user_id=user_id, source=source, external_slug=external_slug)
                .first()
            )
            if installation:
                return MarketplaceInstallationModel.model_validate(installation)
            return None

    def update_installation_config(
        self, id: str, config: dict, db: Optional[Session] = None
    ) -> Optional[MarketplaceInstallationModel]:
        with get_db_context(db) as db:
            try:
                db.query(MarketplaceInstallation).filter_by(id=id).update(
                    {"config": config, "updated_at": int(time.time())}
                )
                db.commit()
                installation = db.get(MarketplaceInstallation, id)
                if installation:
                    return MarketplaceInstallationModel.model_validate(installation)
                return None
            except Exception as e:
                log.exception(f"Error updating installation config: {e}")
                return None

    def update_installation_version(
        self,
        id: str,
        installed_version: str,
        skill_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[MarketplaceInstallationModel]:
        with get_db_context(db) as db:
            try:
                update_data = {
                    "installed_version": installed_version,
                    "updated_at": int(time.time()),
                }
                if skill_id:
                    update_data["skill_id"] = skill_id
                db.query(MarketplaceInstallation).filter_by(id=id).update(update_data)
                db.commit()
                installation = db.get(MarketplaceInstallation, id)
                if installation:
                    return MarketplaceInstallationModel.model_validate(installation)
                return None
            except Exception as e:
                log.exception(f"Error updating installation version: {e}")
                return None

    def update_latest_version(
        self, id: str, latest_version: str, db: Optional[Session] = None
    ) -> bool:
        with get_db_context(db) as db:
            try:
                db.query(MarketplaceInstallation).filter_by(id=id).update(
                    {"latest_version": latest_version, "updated_at": int(time.time())}
                )
                db.commit()
                return True
            except Exception:
                return False

    def delete_installation(self, id: str, db: Optional[Session] = None) -> bool:
        with get_db_context(db) as db:
            try:
                db.query(MarketplaceInstallation).filter_by(id=id).delete()
                db.commit()
                return True
            except Exception as e:
                log.exception(f"Error deleting installation: {e}")
                return False


MarketplaceInstallations = MarketplaceInstallationsTable()
