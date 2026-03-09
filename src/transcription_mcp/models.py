"""Pydantic data models for the transcription MCP server."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Engine(str, Enum):
    APPLE = "apple"


class Word(BaseModel):
    """Atomic unit — a single word with timing for playback highlighting."""

    word: str
    start: float
    end: float
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    engine: Engine | None = None


class Segment(BaseModel):
    """A group of words forming a natural speech segment."""

    words: list[Word]
    start: float
    end: float
    text: str = ""

    def compute_text(self) -> str:
        self.text = " ".join(w.word for w in self.words)
        return self.text


class TranscriptResult(BaseModel):
    """Complete transcription output."""

    engine: Engine
    segments: list[Segment]
    language: str = "en"
    duration: float = 0.0

    @property
    def words(self) -> list[Word]:
        return [w for seg in self.segments for w in seg.words]

    @property
    def full_text(self) -> str:
        return " ".join(seg.text or seg.compute_text() for seg in self.segments)


class StoredTranscript(BaseModel):
    """A persisted transcript record."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_file: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    duration: float = 0.0
    language: str = "en"
    engines_used: list[Engine] = Field(default_factory=list)
    apple_result: TranscriptResult | None = None

    @property
    def full_text(self) -> str:
        return self.apple_result.full_text if self.apple_result else ""
