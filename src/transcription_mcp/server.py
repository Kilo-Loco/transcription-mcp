"""FastMCP server — exposes transcription tools to Claude Code."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from . import storage
from .audio import extract_audio, extract_slice, get_audio_duration
from .models import Engine, Segment, StoredTranscript

mcp = FastMCP(
    "Transcription MCP",
    instructions=(
        "Local transcription server using Apple SpeechAnalyzer (Neural Engine).\n\n"
        "WORKFLOW:\n"
        "1. `transcribe` → transcribes the file, writes .txt and .srt files\n"
        "   next to the source. Returns file paths, metadata, and transcript ID.\n"
        "2. Read the .txt file. Apply formatting: capitalization, punctuation,\n"
        "   and paragraph breaks. This is safe to do from text alone.\n"
        "3. For words that look wrong or don't fit the context, use\n"
        "   `get_audio_slice` with the timestamp range to listen to that\n"
        "   section of audio. Only correct words you can confidently verify\n"
        "   by hearing them.\n"
        "4. Present the cleaned transcript to the user.\n\n"
        "IMPORTANT: Do NOT guess at word corrections from text alone.\n"
        "Formatting (caps, punctuation, paragraphs) = safe from text.\n"
        "Word corrections = must listen to the audio first.\n\n"
        "CONSTRAINTS:\n"
        "- Runs at ~76x realtime on Apple Neural Engine.\n"
        "- The .srt file is ready for YouTube caption upload.\n"
        "- Transcripts are stored in SQLite for full-text search.\n\n"
        "OTHER TOOLS (only use if explicitly asked):\n"
        "- `get_transcript`: retrieve word-level timestamps or specific sections\n"
        "- `search_transcripts` / `list_transcripts`: search/browse past transcripts"
    ),
)


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _segments_to_srt(segments: list[Segment]) -> str:
    """Convert segments to SRT subtitle format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        text = seg.text or seg.compute_text()
        start = _format_srt_time(seg.start)
        end = _format_srt_time(seg.end)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
async def transcribe(
    file_path: str,
    language: str = "en",
) -> dict:
    """Transcribe an audio or video file.

    Produces a .txt transcript and .srt subtitle file next to the source file.
    Also saves structured data to the searchable archive.

    Args:
        file_path: Absolute path to the audio/video file.
        language: Language code (e.g. "en"). Defaults to "en".

    Returns:
        File paths for the transcript and SRT, plus metadata.
    """
    source_path = Path(file_path)
    if not source_path.exists():
        return {"error": f"File not found: {file_path}"}

    # Extract audio to WAV if needed
    audio_path = extract_audio(source_path)
    cleanup_audio = audio_path != source_path

    try:
        duration = get_audio_duration(source_path)

        # Run Apple SpeechAnalyzer
        lang_arg = language
        if "-" not in lang_arg and "_" not in lang_arg:
            lang_arg = f"{lang_arg}-US"

        from .engines import apple_engine

        result = apple_engine.transcribe(audio_path, language=lang_arg)
        result.duration = duration

        # Write transcript text file
        txt_path = source_path.with_suffix(".txt")
        txt_path.write_text(result.full_text, encoding="utf-8")

        # Write SRT subtitle file
        srt_path = source_path.with_suffix(".srt")
        srt_path.write_text(_segments_to_srt(result.segments), encoding="utf-8")

        # Save to searchable archive
        transcript = StoredTranscript(
            source_file=str(source_path),
            duration=duration,
            language=language,
            engines_used=[Engine.APPLE],
            apple_result=result,
        )
        transcript_id = await storage.save_transcript(transcript)

        return {
            "transcript_id": transcript_id,
            "source_file": str(source_path),
            "transcript_file": str(txt_path),
            "srt_file": str(srt_path),
            "duration_seconds": round(duration, 1),
            "word_count": len(result.words),
        }

    finally:
        if cleanup_audio:
            audio_path.unlink(missing_ok=True)


@mcp.tool()
async def get_audio_slice(
    transcript_id: str,
    start_time: float,
    end_time: float,
) -> dict:
    """Extract a short audio clip from a transcribed file for verification.

    Use this to listen to a section of audio when a transcribed word
    looks wrong or doesn't fit the context. Returns the path to an
    audio file that can be played/read.

    Args:
        transcript_id: The transcript ID (to look up the source file).
        start_time: Start time in seconds.
        end_time: End time in seconds.

    Returns:
        Path to the extracted audio slice.
    """
    transcript = await storage.get_transcript(transcript_id)
    if transcript is None:
        return {"error": f"Transcript not found: {transcript_id}"}

    source_path = Path(transcript.source_file)
    if not source_path.exists():
        return {"error": f"Source file no longer exists: {transcript.source_file}"}

    # Cap slice length at 30 seconds to keep files manageable
    max_slice = 30.0
    if end_time - start_time > max_slice:
        end_time = start_time + max_slice

    # Extract the slice
    slice_dir = source_path.parent / ".audio_slices"
    slice_dir.mkdir(exist_ok=True)
    slice_path = slice_dir / f"{transcript_id}_{start_time:.1f}-{end_time:.1f}.m4a"

    try:
        result_path = extract_slice(source_path, start_time, end_time, slice_path)
    except Exception as e:
        return {"error": f"Failed to extract audio slice: {e}"}

    return {
        "audio_file": str(result_path),
        "start_time": round(start_time, 2),
        "end_time": round(end_time, 2),
        "duration": round(end_time - start_time, 2),
    }


@mcp.tool()
async def get_transcript(
    transcript_id: str,
    format: str = "segments",
    start_time: float | None = None,
    end_time: float | None = None,
) -> dict:
    """Retrieve a stored transcript by ID.

    Args:
        transcript_id: The transcript ID.
        format: Output format — "words" or "segments".
        start_time: Filter to words after this time (seconds).
        end_time: Filter to words before this time (seconds).
    """
    transcript = await storage.get_transcript(transcript_id)
    if transcript is None:
        return {"error": f"Transcript not found: {transcript_id}"}

    result = transcript.apple_result
    if result is None:
        return {"error": "No transcript result available"}

    words = result.words
    if start_time is not None:
        words = [w for w in words if w.end >= start_time]
    if end_time is not None:
        words = [w for w in words if w.start <= end_time]

    if format == "words":
        return {
            "transcript_id": transcript_id,
            "words": [
                {
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "confidence": round(w.confidence, 3),
                }
                for w in words
            ],
        }
    else:  # segments
        segments = result.segments
        if start_time is not None or end_time is not None:
            seg_data = []
            for seg in segments:
                seg_words = seg.words
                if start_time is not None:
                    seg_words = [w for w in seg_words if w.end >= start_time]
                if end_time is not None:
                    seg_words = [w for w in seg_words if w.start <= end_time]
                if seg_words:
                    seg_data.append({
                        "start": round(seg_words[0].start, 3),
                        "end": round(seg_words[-1].end, 3),
                        "text": " ".join(w.word for w in seg_words),
                        "word_count": len(seg_words),
                    })
        else:
            seg_data = [
                {
                    "start": round(s.start, 3),
                    "end": round(s.end, 3),
                    "text": s.text or s.compute_text(),
                    "word_count": len(s.words),
                }
                for s in segments
            ]

        return {
            "transcript_id": transcript_id,
            "segments": seg_data,
        }


@mcp.tool()
async def search_transcripts(query: str, limit: int = 20) -> dict:
    """Full-text search across all stored transcripts.

    Args:
        query: Search query (supports FTS5 syntax: AND, OR, NOT, phrases).
        limit: Maximum number of results (default 20).
    """
    results = await storage.search_transcripts(query, limit)
    return {"query": query, "count": len(results), "results": results}


@mcp.tool()
async def list_transcripts() -> dict:
    """List all stored transcripts with metadata."""
    transcripts = await storage.list_transcripts()
    return {"count": len(transcripts), "transcripts": transcripts}


def main():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
