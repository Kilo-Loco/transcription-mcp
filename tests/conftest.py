"""Shared fixtures for transcription MCP tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import pytest_asyncio

from transcription_mcp.models import Engine, Segment, StoredTranscript, TranscriptResult, Word


# 15-second audio clip with clear speech (extracted from Getting started with Claude.ai)
REAL_AUDIO = Path(__file__).parent / "fixtures" / "test_speech.m4a"


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a clean temporary directory."""
    return tmp_path


@pytest.fixture
def sample_audio(tmp_dir):
    """Copy the real audio to a temp dir so tests don't pollute the source."""
    if not REAL_AUDIO.exists():
        pytest.skip(f"Test audio not found: {REAL_AUDIO}")
    dest = tmp_dir / "test_audio.m4a"
    shutil.copy2(REAL_AUDIO, dest)
    return dest


@pytest.fixture
def sample_transcript_result():
    """Build a realistic TranscriptResult for unit tests."""
    words = [
        Word(word="Hello", start=0.0, end=0.5, confidence=0.95, engine=Engine.APPLE),
        Word(word="world", start=0.5, end=1.0, confidence=0.98, engine=Engine.APPLE),
        Word(word="this", start=1.5, end=1.8, confidence=0.90, engine=Engine.APPLE),
        Word(word="is", start=1.8, end=2.0, confidence=0.99, engine=Engine.APPLE),
        Word(word="a", start=2.0, end=2.1, confidence=0.99, engine=Engine.APPLE),
        Word(word="test", start=2.1, end=2.5, confidence=0.97, engine=Engine.APPLE),
    ]
    seg1 = Segment(words=words[:2], start=0.0, end=1.0, text="Hello world")
    seg2 = Segment(words=words[2:], start=1.5, end=2.5, text="this is a test")
    return TranscriptResult(
        engine=Engine.APPLE,
        segments=[seg1, seg2],
        language="en",
        duration=3.0,
    )


@pytest.fixture
def sample_stored_transcript(sample_transcript_result, sample_audio):
    """Build a StoredTranscript backed by the sample audio."""
    return StoredTranscript(
        source_file=str(sample_audio),
        duration=3.0,
        language="en",
        engines_used=[Engine.APPLE],
        apple_result=sample_transcript_result,
    )


@pytest_asyncio.fixture
async def isolated_db(tmp_dir, monkeypatch):
    """Point storage at a temp database so tests don't touch production data."""
    import transcription_mcp.storage as storage_mod

    # Reset the singleton connection so it picks up the new path
    await storage_mod.close()

    db_dir = tmp_dir / "data"
    db_dir.mkdir()
    monkeypatch.setattr(storage_mod, "_DB_DIR", db_dir)
    monkeypatch.setattr(storage_mod, "_DB_PATH", db_dir / "test.db")

    yield

    # Clean up the singleton after each test
    await storage_mod.close()


@pytest_asyncio.fixture
async def saved_transcript(sample_stored_transcript, isolated_db):
    """Save the sample transcript to the isolated DB and return its ID."""
    from transcription_mcp import storage

    tid = await storage.save_transcript(sample_stored_transcript)
    return tid, sample_stored_transcript
