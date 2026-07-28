from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, computed_field


class Chamber(str, Enum):
    house = "House"
    senate = "Senate"


class PartyLane(str, Enum):
    majority = "majority"
    minority = "minority"
    committee = "committee"


class ItemType(str, Enum):
    press_release = "press_release"
    letter = "letter"
    report = "report"
    hearing_notice = "hearing_notice"
    pdf = "pdf"
    document = "document"


class ItemStatus(str, Enum):
    new = "new"
    updated = "updated"
    unchanged = "unchanged"


class SourceTier(str, Enum):
    tier1 = "tier1"
    tier2 = "tier2"
    tier3 = "tier3"


# --- Source configuration (loaded from sources.yml) ---


class SourceConfig(BaseModel):
    id: str
    name: str
    committee: str
    chamber: Chamber
    party_lane: PartyLane
    url: str
    collection: str
    kind: ItemType
    tier: SourceTier
    parser: str  # maps to parser registry key
    enabled: bool = True
    detail_fetch: str = "none"  # none, html, pdf
    recent_item_limit: int = 20
    notes: str = ""
    why_relevant: str = ""


# --- Feed items (the pipeline's internal currency) ---


class FeedItem(BaseModel):
    source_id: str
    source_name: str
    committee: str
    chamber: Chamber
    party_lane: PartyLane
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    item_type: ItemType = ItemType.press_release
    is_pdf: bool = False
    content_hash: str = ""
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: ItemStatus = ItemStatus.new
    source_tier: SourceTier = SourceTier.tier1

    @computed_field
    @property
    def item_id(self) -> str:
        """Stable source-local identity."""
        date_str = self.published_at.isoformat() if self.published_at else ""
        raw = f"{self.source_id}|{self.url}|{self.title}|{date_str}"
        return hashlib.sha1(raw.encode()).hexdigest()

    @computed_field
    @property
    def cluster_id(self) -> str:
        """Cross-source dedupe key. Same URL = same cluster."""
        if self.url:
            return hashlib.sha1(self.url.encode()).hexdigest()
        raw = f"{self.title}|{self.published_at.isoformat() if self.published_at else ''}"
        return hashlib.sha1(raw.encode()).hexdigest()


# --- Run result (per-source execution summary) ---


class RunResult(BaseModel):
    source_id: str
    source_name: str
    items_found: int = 0
    new_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    errors: list[str] = Field(default_factory=list)
    fetch_duration_ms: float = 0.0
    success: bool = True


class RunSummary(BaseModel):
    started_at: datetime
    finished_at: datetime
    sources_attempted: int
    sources_succeeded: int
    sources_failed: int
    total_new: int
    total_updated: int
    results: list[RunResult]
