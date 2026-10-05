"""Strict input contracts shared by routes and services."""

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

Name = Annotated[str, Field(min_length=1, max_length=200)]
Contact = Annotated[str, Field(min_length=1, max_length=320)]
RequestText = Annotated[str, Field(max_length=10000)]
Role = Literal["admin", "manager"]
LeadSource = Literal["bot", "manual", "telegram", "webhook"]
LeadStatus = Literal["new", "in_progress", "done", "rejected"]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class User(Schema):
    id: UUID
    telegram_id: Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)] | None = None
    role: Role = "manager"
    created_at: datetime


class TagCreate(Schema):
    name: Annotated[str, Field(min_length=1, max_length=64)]
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] = "#6B7280"


class Tag(TagCreate):
    id: UUID


class LeadCreate(Schema):
    name: Name
    contact: Contact
    request: RequestText | None = None
    source: LeadSource = "manual"
    status: LeadStatus = "new"
    next_contact_date: date | None = None


class LeadUpdate(Schema):
    name: Name | None = None
    contact: Contact | None = None
    request: RequestText | None = None
    status: LeadStatus | None = None
    next_contact_date: date | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field")
        for field in ("name", "contact", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class Lead(LeadCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime
    tags: list[Tag] = Field(default_factory=list)


class TelegramLogin(Schema):
    init_data: str = Field(alias="initData", min_length=1, max_length=16384)


class PinLogin(Schema):
    pin: str = Field(min_length=1, max_length=128)


class TokenResponse(Schema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class ExternalLead(Schema):
    # Providers may include event metadata; it must not affect acceptance or persistence.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    source_name: Annotated[str, Field(min_length=1, max_length=128)]
    name: Name
    contact: Contact
    request: RequestText | None = None
    secret: SecretStr | None = None


class WebhookResult(Schema):
    status: Literal["created"] = "created"
    lead_id: UUID
