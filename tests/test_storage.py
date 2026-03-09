"""Tests for SQLite + FTS5 storage."""

import pytest

from transcription_mcp import storage
from transcription_mcp.models import Engine, Segment, StoredTranscript, TranscriptResult, Word


@pytest.fixture
def transcript_with_text(tmp_dir):
    """Create a StoredTranscript with known searchable text."""
    words = [
        Word(word="Claude", start=0.0, end=0.5, engine=Engine.APPLE),
        Word(word="is", start=0.5, end=0.7, engine=Engine.APPLE),
        Word(word="an", start=0.7, end=0.9, engine=Engine.APPLE),
        Word(word="AI", start=0.9, end=1.2, engine=Engine.APPLE),
        Word(word="assistant", start=1.2, end=1.8, engine=Engine.APPLE),
    ]
    seg = Segment(words=words, start=0.0, end=1.8, text="Claude is an AI assistant")
    result = TranscriptResult(
        engine=Engine.APPLE,
        segments=[seg],
        language="en",
        duration=2.0,
    )
    return StoredTranscript(
        source_file=str(tmp_dir / "test_video.mp4"),
        duration=2.0,
        language="en",
        engines_used=[Engine.APPLE],
        apple_result=result,
    )


class TestSaveAndGet:
    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, isolated_db, transcript_with_text):
        tid = await storage.save_transcript(transcript_with_text)
        assert tid == transcript_with_text.id

        retrieved = await storage.get_transcript(tid)
        assert retrieved is not None
        assert retrieved.id == tid
        assert retrieved.source_file == transcript_with_text.source_file
        assert retrieved.full_text == "Claude is an AI assistant"
        assert len(retrieved.apple_result.words) == 5

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, isolated_db):
        result = await storage.get_transcript("nonexistent_id")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_overwrites(self, isolated_db, transcript_with_text):
        await storage.save_transcript(transcript_with_text)

        # Modify and re-save with same ID
        transcript_with_text.language = "fr"
        await storage.save_transcript(transcript_with_text)

        retrieved = await storage.get_transcript(transcript_with_text.id)
        assert retrieved.language == "fr"


class TestListTranscripts:
    @pytest.mark.asyncio
    async def test_empty_list(self, isolated_db):
        result = await storage.list_transcripts()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_returns_metadata(self, isolated_db, transcript_with_text):
        await storage.save_transcript(transcript_with_text)
        result = await storage.list_transcripts()
        assert len(result) == 1
        assert result[0]["id"] == transcript_with_text.id
        assert result[0]["source_file"] == transcript_with_text.source_file
        assert result[0]["duration"] == 2.0
        assert result[0]["language"] == "en"

    @pytest.mark.asyncio
    async def test_list_multiple(self, isolated_db, tmp_dir):
        for i in range(3):
            t = StoredTranscript(
                source_file=str(tmp_dir / f"video_{i}.mp4"),
                duration=float(i + 1),
            )
            await storage.save_transcript(t)
        result = await storage.list_transcripts()
        assert len(result) == 3


class TestSearchTranscripts:
    @pytest.mark.asyncio
    async def test_search_finds_match(self, isolated_db, transcript_with_text):
        await storage.save_transcript(transcript_with_text)
        results = await storage.search_transcripts("Claude")
        assert len(results) == 1
        assert results[0]["id"] == transcript_with_text.id

    @pytest.mark.asyncio
    async def test_search_no_match(self, isolated_db, transcript_with_text):
        await storage.save_transcript(transcript_with_text)
        results = await storage.search_transcripts("xyznonexistent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_with_snippet(self, isolated_db, transcript_with_text):
        await storage.save_transcript(transcript_with_text)
        results = await storage.search_transcripts("AI assistant")
        assert len(results) == 1
        assert "snippet" in results[0]


class TestDeleteTranscript:
    @pytest.mark.asyncio
    async def test_delete_existing(self, isolated_db, transcript_with_text):
        await storage.save_transcript(transcript_with_text)
        deleted = await storage.delete_transcript(transcript_with_text.id)
        assert deleted is True

        retrieved = await storage.get_transcript(transcript_with_text.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, isolated_db):
        deleted = await storage.delete_transcript("nonexistent_id")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_removes_from_search(self, isolated_db, transcript_with_text):
        await storage.save_transcript(transcript_with_text)
        await storage.delete_transcript(transcript_with_text.id)
        results = await storage.search_transcripts("Claude")
        assert len(results) == 0
