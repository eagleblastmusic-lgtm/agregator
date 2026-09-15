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


class WebsiteResolutionOrigin(StrEnum):
    SOURCE_CANDIDATE = "source_candidate"
    SEARCH = "search"
    KNOWN_URL = "known_url"


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


class PageSnapshot(BaseModel):
    url: str
    status_code: int
    content_sha256: str
    text_excerpt: str = ""


class WebsiteVerificationAttempt(BaseModel):
    url: str
    resolved_url: str
    accepted: bool
    score: float = Field(ge=0.0, le=1.0)
    search_score: float = Field(ge=0.0, le=1.0)
    content_score: float = Field(ge=0.0, le=1.0)
    name_coverage: float = Field(ge=0.0, le=1.0)
    origin: WebsiteResolutionOrigin | None = None
    source: str | None = None
    signals: list[str] = Field(default_factory=list)
    scanned_pages: list[str] = Field(default_factory=list)
    page_snapshots: list[PageSnapshot] = Field(default_factory=list)


class CompanyIdentity(BaseModel):
    name: str
    city: str | None = None
    website_url: str | None = None
    domain: str | None = None
    website_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    website_resolution_origin: WebsiteResolutionOrigin | None = None
    website_resolution_source: str | None = None
    website_verification_signals: list[str] = Field(default_factory=list)


class CompanyIdentifier(BaseModel):
    kind: str
    value: str
    source: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CompanyWebsiteCandidate(BaseModel):
    url: str
    source: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class JobPosting(BaseModel):
    source: str
    source_id: str | None = None
    url: str
    title: str
    company_name: str
    company_name_source: str | None = None
    company_name_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    company_identifiers: list[CompanyIdentifier] = Field(default_factory=list)
    company_website_candidates: list[CompanyWebsiteCandidate] = Field(default_factory=list)
    city: str | None = None
    description: str | None = None
    published_at: str | None = None
    refreshed_at: str | None = None


class DiscoveryResult(BaseModel):
    company: CompanyIdentity
    channels: list[ContactChannel] = Field(default_factory=list)
    scanned_pages: list[str] = Field(default_factory=list)
    page_snapshots: list[PageSnapshot] = Field(default_factory=list)
    search_candidates: list[SearchCandidate] = Field(default_factory=list)
    website_attempts: list[WebsiteVerificationAttempt] = Field(default_factory=list)
