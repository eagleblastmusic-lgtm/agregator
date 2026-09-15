from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ChannelKind(StrEnum):
    EMAIL = "email"
    FORM = "form"


class ChannelPurpose(StrEnum):
    BUSINESS_PARTNERSHIP = "business_partnership"
    SALES = "sales"
    SUPPLIER = "supplier"
    FRANCHISE = "franchise"
    GENERIC = "generic"
    RECRUITMENT = "recruitment"
    SUPPORT = "support"
    PRIVACY = "privacy"
    NEGATIVE = "negative"


class Decision(StrEnum):
    GREEN = "green"
    REVIEW = "review"
    IGNORE = "ignore"


class Evidence(BaseModel):
    url: str
    text: str
    signal: str | None = None


class ContactChannel(BaseModel):
    kind: ChannelKind
    value: str
    purpose: ChannelPurpose
    decision: Decision
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Evidence


class SearchCandidate(BaseModel):
    title: str
    url: str
    snippet: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class CompanyIdentity(BaseModel):
    name: str
    city: str | None = None
    website_url: str | None = None
    domain: str | None = None
    website_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class JobPosting(BaseModel):
    source: str
    source_id: str | None = None
    url: str
    title: str
    company_name: str
    company_name_source: str | None = None
    company_name_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    city: str | None = None
    description: str | None = None
    published_at: str | None = None
    refreshed_at: str | None = None


class DiscoveryResult(BaseModel):
    company: CompanyIdentity
    channels: list[ContactChannel] = Field(default_factory=list)
    scanned_pages: list[str] = Field(default_factory=list)
    search_candidates: list[SearchCandidate] = Field(default_factory=list)
