from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl, field_validator

class JobStatus(StrEnum):
    QUEUED = 'queued'; DETECTING = 'detecting'; EXTRACTING = 'extracting'; ANALYZING = 'analyzing'; UPLOADING = 'uploading'; SENDING = 'sending'; COMPLETED = 'completed'; FAILED = 'failed'

class CloneRequest(BaseModel):
    url: HttpUrl
    mazigho_user_id: str = Field(min_length=1, max_length=160)
    mazigho_project_name: str | None = Field(default=None, max_length=160)
    # Secret éphémère : utilisé uniquement pour déverrouiller une boutique
    # Shopify de développement, jamais recopié dans JobState ou les résultats.
    shopify_password: str | None = Field(default=None, min_length=1, max_length=256)
    force: bool = False
    @field_validator('url')
    @classmethod
    def only_http(cls, value: HttpUrl):
        if value.scheme not in {'http', 'https'}: raise ValueError('Seules les URLs http(s) sont acceptées')
        return value

class JobState(BaseModel):
    job_id: UUID
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    platform_detected: str | None = None
    products_count: int = 0
    variants_count: int = 0
    images_count: int = 0
    pages_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    message: str = ''
    error: str | None = None
    mazigho_project_url: str | None = None
    export_url: str | None = None
    robots_warning: str | None = None
    robots_status: str = 'unknown'
    force_confirmed: bool = False
    recommended_theme: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CloneResponse(BaseModel):
    job_id: UUID
    status: JobStatus

class ImportResponse(BaseModel):
    project_url: str | None = None
    project_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
