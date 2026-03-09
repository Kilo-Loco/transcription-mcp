"""FastMCP server — exposes transcription tools to Claude Code."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import FastMCP

from . import storage
from .audio import extract_audio, extract_slice, get_audio_duration
from .models import Engine, Segment, StoredTranscript

# Maximum characters of transcript text to include inline in the tool response.
# Beyond this, Claude should read the .txt file for the full text.
_MAX_INLINE_TEXT = 10_000

# Maximum segments or words to return inline from get_transcript.
# For longer transcripts, Claude should use time ranges or read the .txt file.
_MAX_INLINE_ITEMS = 200

mcp = FastMCP(
    "Transcription MCP",
    instructions=(
        "Local transcription server using Apple SpeechAnalyzer (Neural Engine).\n\n"
        "WORKFLOW:\n"
        "1. Call `transcribe` with the file path. The response includes the\n"
        "   transcript text (or a preview), file paths, and metadata.\n"
        "2. For short transcripts (included inline): clean up capitalization,\n"
        "   punctuation, and add paragraph breaks at natural topic changes.\n"
        "3. For long transcripts (truncated): read the .txt file path from\n"
        "   the response using the Read tool. Read it in chunks if needed.\n"
        "4. Present the cleaned transcript to the user.\n\n"
        "LARGE FILE HANDLING:\n"
        "- `transcribe` returns the full text inline for short files.\n"
        "  For long files, it returns a preview + the .txt file path.\n"
        "- `get_transcript` returns up to 200 segments/words inline.\n"
        "  For longer transcripts, use start_time/end_time to fetch\n"
        "  specific sections, or read the .txt file directly.\n"
        "- NEVER try to load an entire long transcript through MCP tools.\n"
        "  Use the .txt file with the Read tool instead.\n\n"
        "IMPORTANT: Do NOT guess at word corrections from text alone.\n"
        "Formatting (caps, punctuation, paragraphs) = safe.\n"
        "If a word looks wrong, leave it as-is — the neural engine output\n"
        "is usually more accurate than a guess from context.\n\n"
        "OUTPUT FILES:\n"
        "- The .srt file is ready for YouTube caption upload.\n"
        "- The .txt file contains the raw transcript.\n"
        "- Both are written next to the source file.\n\n"
        "OTHER TOOLS (only use if explicitly asked):\n"
        "- `get_transcript`: retrieve word-level timestamps or specific sections\n"
        "- `get_audio_slice`: extract a short audio clip for the user to review\n"
        "- `search_transcripts` / `list_transcripts`: search/browse past transcripts\n"
        "- `delete_transcript`: remove a transcript from the archive"
    ),
)


# Map bare language codes to their most common locale.
_LOCALE_DEFAULTS = {
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-BR",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "zh": "zh-CN",
    "ru": "ru-RU",
    "ar": "ar-SA",
    "hi": "hi-IN",
    "nl": "nl-NL",
    "sv": "sv-SE",
    "da": "da-DK",
    "fi": "fi-FI",
    "nb": "nb-NO",
    "pl": "pl-PL",
    "tr": "tr-TR",
    "uk": "uk-UA",
    "th": "th-TH",
    "vi": "vi-VN",
    "id": "id-ID",
    "ms": "ms-MY",
    "ca": "ca-ES",
    "hr": "hr-HR",
    "cs": "cs-CZ",
    "el": "el-GR",
    "he": "he-IL",
    "hu": "hu-HU",
    "ro": "ro-RO",
    "sk": "sk-SK",
}


def _normalize_language(lang: str) -> str:
    """Convert a bare language code to a full locale identifier."""
    if "-" in lang or "_" in lang:
        return lang  # Already a full locale like "en-US" or "en_GB"
    return _LOCALE_DEFAULTS.get(lang, f"{lang}-{lang.upper()}")


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m {secs}s"


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = round((seconds % 1) * 1000)
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
    """Transcribe an audio or video file locally using Apple SpeechAnalyzer.

    Returns the transcript text, .txt and .srt file paths, and metadata.
    The .srt file is ready for YouTube caption upload.

    Args:
        file_path: Absolute path to the audio/video file.
        language: Language code (e.g. "en", "es", "ja") or full locale
                  (e.g. "en-US", "en-GB"). Defaults to "en".

    Returns:
        Transcript text (or preview for long files), file paths, and metadata.
    """
    source_path = Path(file_path)
    if not source_path.exists():
        return {"error": f"File not found: {file_path}"}

    # Extract audio to WAV if needed (run blocking ffmpeg off the event loop)
    try:
        audio_path = await asyncio.to_thread(extract_audio, source_path)
    except (RuntimeError, FileNotFoundError) as exc:
        return {"error": f"Audio extraction failed: {exc}"}
    cleanup_audio = audio_path != source_path

    try:
        duration = await asyncio.to_thread(get_audio_duration, source_path)
        lang_arg = _normalize_language(language)

        from .engines import apple_engine

        # Run the blocking Swift CLI transcription off the event loop
        result = await asyncio.to_thread(
            apple_engine.transcribe, audio_path, lang_arg
        )
        result.duration = duration

        # Write transcript text file
        full_text = result.full_text
        txt_path = source_path.with_suffix(".txt")
        txt_path.write_text(full_text, encoding="utf-8")

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

        response = {
            "transcript_id": transcript_id,
            "duration": _format_duration(duration),
            "word_count": len(result.words),
            "transcript_file": str(txt_path),
            "srt_file": str(srt_path),
        }

        # Include transcript text inline when it fits; otherwise provide
        # a preview so Claude can present something immediately.
        if len(full_text) <= _MAX_INLINE_TEXT:
            response["transcript"] = full_text
        else:
            response["transcript_preview"] = full_text[:_MAX_INLINE_TEXT]
            response["transcript_truncated"] = True
            response["full_text_chars"] = len(full_text)

        return response

    except Exception as exc:
        return {"error": f"Transcription failed: {exc}"}

    finally:
        if cleanup_audio:
            audio_path.unlink(missing_ok=True)


@mcp.tool()
async def get_audio_slice(
    transcript_id: str,
    start_time: float,
    end_time: float,
) -> dict:
    """Extract a short audio clip from a transcribed file.

    Use this when the user wants to hear a specific section of audio,
    or to verify what was said at a particular timestamp.

    Args:
        transcript_id: The transcript ID (from a previous transcribe call).
        start_time: Start time in seconds.
        end_time: End time in seconds (max 30s clip).

    Returns:
        Path to the extracted audio clip (.m4a).
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
        result_path = await asyncio.to_thread(
            extract_slice, source_path, start_time, end_time, slice_path
        )
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
    """Retrieve a stored transcript by ID with optional time filtering.

    For long transcripts, use start_time/end_time to fetch specific sections
    rather than loading everything at once.

    Args:
        transcript_id: The transcript ID.
        format: Output format — "words" (with timestamps) or "segments".
        start_time: Filter to content after this time (seconds).
        end_time: Filter to content before this time (seconds).
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
        word_data = [
            {
                "word": w.word,
                "start": round(w.start, 3),
                "end": round(w.end, 3),
                "confidence": round(w.confidence, 3),
            }
            for w in words
        ]
        response: dict = {
            "transcript_id": transcript_id,
            "total_words": len(result.words),
            "returned_words": len(word_data),
        }
        # Cap inline output — for large results, tell Claude to use
        # the .txt file or narrow the time range.
        if len(word_data) > _MAX_INLINE_ITEMS:
            response["words"] = word_data[:_MAX_INLINE_ITEMS]
            response["truncated"] = True
            response["hint"] = (
                "Result truncated. Use start_time/end_time to fetch "
                "specific sections, or read the .txt file directly."
            )
        else:
            response["words"] = word_data
        return response
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

        response = {
            "transcript_id": transcript_id,
            "total_segments": len(result.segments),
            "returned_segments": len(seg_data),
        }
        if len(seg_data) > _MAX_INLINE_ITEMS:
            response["segments"] = seg_data[:_MAX_INLINE_ITEMS]
            response["truncated"] = True
            response["hint"] = (
                "Result truncated. Use start_time/end_time to fetch "
                "specific sections, or read the .txt file directly."
            )
        else:
            response["segments"] = seg_data
        return response


@mcp.tool()
async def search_transcripts(query: str, limit: int = 20) -> dict:
    """Full-text search across all stored transcripts.

    Args:
        query: Search query (supports FTS5 syntax: AND, OR, NOT, phrases).
        limit: Maximum number of results (default 20).
    """
    try:
        results = await storage.search_transcripts(query, limit)
    except ValueError as exc:
        return {"error": str(exc)}
    return {"query": query, "count": len(results), "results": results}


@mcp.tool()
async def list_transcripts() -> dict:
    """List all stored transcripts with metadata."""
    transcripts = await storage.list_transcripts()
    return {"count": len(transcripts), "transcripts": transcripts}


@mcp.tool()
async def delete_transcript(transcript_id: str) -> dict:
    """Delete a stored transcript by ID.

    Use this when the user wants to remove a transcript from the archive.

    Args:
        transcript_id: The transcript ID to delete.

    Returns:
        Whether the transcript was found and deleted.
    """
    deleted = await storage.delete_transcript(transcript_id)
    if deleted:
        return {"deleted": True, "transcript_id": transcript_id}
    return {"error": f"Transcript not found: {transcript_id}"}


def main():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
