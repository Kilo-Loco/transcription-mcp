"""End-to-end tests — transcribe a real audio file through the full pipeline.

These tests require:
- macOS 26 with Apple SpeechAnalyzer
- The Swift CLI built (auto-builds on first run)
- ffmpeg installed
- A real MP3 test fixture (86s+ — SpeechAnalyzer needs files >60s)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transcription_mcp import storage
from transcription_mcp.server import (
    get_audio_slice,
    get_transcript,
    list_transcripts,
    search_transcripts,
    transcribe,
)


@pytest.mark.asyncio
@pytest.mark.speechanalyzer
class TestTranscribeE2E:
    """Real transcription through Apple SpeechAnalyzer."""

    async def test_transcribe_produces_files(self, sample_audio, isolated_db):
        result = await transcribe(str(sample_audio))

        assert "error" not in result, f"Transcription failed: {result.get('error')}"
        assert "transcript_id" in result
        assert result["word_count"] > 0
        assert "duration" in result  # Human-readable string like "1m 26s"

        # Transcript text included in response
        assert "transcript" in result or "transcript_preview" in result

        # .txt file written next to source
        txt_path = Path(result["transcript_file"])
        assert txt_path.exists()
        txt_content = txt_path.read_text()
        assert len(txt_content) > 0

        # .srt file written next to source
        srt_path = Path(result["srt_file"])
        assert srt_path.exists()
        srt_content = srt_path.read_text()
        assert "-->" in srt_content  # SRT format marker

    async def test_transcribe_saves_to_db(self, sample_audio, isolated_db):
        result = await transcribe(str(sample_audio))
        assert "error" not in result, f"Transcription failed: {result.get('error')}"
        tid = result["transcript_id"]

        stored = await storage.get_transcript(tid)
        assert stored is not None
        assert stored.apple_result is not None
        assert len(stored.apple_result.words) == result["word_count"]

    async def test_transcribe_nonexistent_file(self, isolated_db):
        result = await transcribe("/tmp/nonexistent_file.mp3")
        assert "error" in result

    async def test_srt_file_valid_format(self, sample_audio, isolated_db):
        result = await transcribe(str(sample_audio))
        assert "error" not in result
        srt_path = Path(result["srt_file"])
        srt_content = srt_path.read_text()

        # Empty SRT is valid if transcription produced no segments
        if not srt_content.strip():
            pytest.skip("Transcription produced empty SRT")

        lines = srt_content.strip().split("\n")
        assert lines[0] == "1"
        assert "-->" in lines[1]
        parts = lines[1].split(" --> ")
        assert len(parts) == 2
        for part in parts:
            h, m, rest = part.split(":")
            s, ms = rest.split(",")
            assert len(h) == 2
            assert len(m) == 2
            assert len(s) == 2
            assert len(ms) == 3

    async def test_word_timestamps_are_monotonic(self, sample_audio, isolated_db):
        result = await transcribe(str(sample_audio))
        assert "error" not in result
        tid = result["transcript_id"]

        words_result = await get_transcript(tid, format="words")
        words = words_result["words"]

        if not words:
            pytest.skip("Transcription produced no words")

        for i in range(1, len(words)):
            assert words[i]["start"] >= words[i - 1]["start"], (
                f"Word {i} starts before word {i-1}: "
                f"{words[i]['word']}@{words[i]['start']} < "
                f"{words[i-1]['word']}@{words[i-1]['start']}"
            )


@pytest.mark.asyncio
class TestGetTranscript:
    """Test transcript retrieval using pre-saved data (no real transcription)."""

    async def test_get_segments(self, saved_transcript):
        tid, _ = saved_transcript
        result = await get_transcript(tid, format="segments")
        assert "error" not in result
        assert "segments" in result
        assert len(result["segments"]) == 2

        seg = result["segments"][0]
        assert "start" in seg
        assert "end" in seg
        assert "text" in seg
        assert "word_count" in seg
        assert seg["text"] == "Hello world"

    async def test_get_words(self, saved_transcript):
        tid, _ = saved_transcript
        result = await get_transcript(tid, format="words")
        assert "error" not in result
        assert "words" in result
        assert len(result["words"]) == 6

        word = result["words"][0]
        assert word["word"] == "Hello"
        assert word["start"] == 0.0
        assert word["end"] == 0.5
        assert word["confidence"] == 0.95

    async def test_get_time_range(self, saved_transcript):
        tid, _ = saved_transcript

        # Words where end >= 1.1 (excludes "Hello" end=0.5, "world" end=1.0)
        result = await get_transcript(tid, format="words", start_time=1.1)
        words = result["words"]
        assert len(words) == 4  # "this", "is", "a", "test"
        assert words[0]["word"] == "this"

    async def test_get_time_range_end(self, saved_transcript):
        tid, _ = saved_transcript

        # Words where start <= 1.0 (includes "Hello" and "world", excludes "this" start=1.5)
        result = await get_transcript(tid, format="words", end_time=1.0)
        words = result["words"]
        assert len(words) == 2  # "Hello", "world"

    async def test_not_found(self, isolated_db):
        result = await get_transcript("nonexistent_id")
        assert "error" in result


@pytest.mark.asyncio
class TestListAndSearch:
    """Test list and search using pre-saved data."""

    async def test_list_transcripts(self, saved_transcript):
        tid, stored = saved_transcript
        result = await list_transcripts()
        assert result["count"] == 1
        assert result["transcripts"][0]["id"] == tid

    async def test_list_empty(self, isolated_db):
        result = await list_transcripts()
        assert result["count"] == 0

    async def test_search_finds_match(self, saved_transcript):
        tid, _ = saved_transcript
        result = await search_transcripts("Hello")
        assert result["count"] >= 1
        assert result["results"][0]["id"] == tid

    async def test_search_no_match(self, saved_transcript):
        result = await search_transcripts("xyznonexistentword123")
        assert result["count"] == 0

    async def test_search_malformed_query_returns_error(self, isolated_db):
        result = await search_transcripts('"unbalanced quote')
        assert "error" in result


@pytest.mark.asyncio
class TestGetAudioSlice:
    """Test audio slice extraction."""

    async def test_extract_slice(self, saved_transcript):
        tid, stored = saved_transcript
        source = Path(stored.source_file)
        if not source.exists():
            pytest.skip("Source MP3 not available")

        result = await get_audio_slice(tid, 0.0, 2.0)
        assert "error" not in result
        assert "audio_file" in result

        audio_path = Path(result["audio_file"])
        assert audio_path.exists()
        assert audio_path.suffix == ".m4a"
        assert result["duration"] == 2.0

        # Cleanup
        audio_path.unlink(missing_ok=True)

    async def test_caps_at_30s(self, saved_transcript):
        tid, stored = saved_transcript
        source = Path(stored.source_file)
        if not source.exists():
            pytest.skip("Source MP3 not available")

        result = await get_audio_slice(tid, 0.0, 60.0)
        assert "error" not in result
        assert result["duration"] == 30.0
        assert result["end_time"] == 30.0

        Path(result["audio_file"]).unlink(missing_ok=True)

    async def test_not_found(self, isolated_db):
        result = await get_audio_slice("nonexistent_id", 0.0, 1.0)
        assert "error" in result
