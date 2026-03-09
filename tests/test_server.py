"""Tests for the MCP server tools — SRT formatting, duration, language normalization."""

import pytest

from transcription_mcp.models import Engine, Segment, Word
from transcription_mcp.server import (
    _format_duration,
    _format_srt_time,
    _normalize_language,
    _segments_to_srt,
)


class TestSrtFormatting:
    def test_format_zero(self):
        assert _format_srt_time(0.0) == "00:00:00,000"

    def test_format_seconds(self):
        assert _format_srt_time(5.123) == "00:00:05,123"

    def test_format_minutes(self):
        assert _format_srt_time(65.5) == "00:01:05,500"

    def test_format_hours(self):
        assert _format_srt_time(3661.0) == "01:01:01,000"

    def test_format_large(self):
        assert _format_srt_time(7384.567) == "02:03:04,567"

    def test_segments_to_srt(self):
        words1 = [Word(word="Hello", start=0.0, end=0.5)]
        words2 = [Word(word="World", start=1.0, end=1.5)]
        seg1 = Segment(words=words1, start=0.0, end=0.5, text="Hello")
        seg2 = Segment(words=words2, start=1.0, end=1.5, text="World")

        srt = _segments_to_srt([seg1, seg2])
        lines = srt.strip().split("\n")

        # First subtitle block
        assert lines[0] == "1"
        assert lines[1] == "00:00:00,000 --> 00:00:00,500"
        assert lines[2] == "Hello"

        # Second subtitle block
        assert lines[4] == "2"
        assert lines[5] == "00:00:01,000 --> 00:00:01,500"
        assert lines[6] == "World"

    def test_segments_to_srt_empty(self):
        assert _segments_to_srt([]) == ""

    def test_segments_to_srt_computes_text(self):
        """Segments without pre-set text should compute it from words."""
        words = [
            Word(word="hello", start=0.0, end=0.5),
            Word(word="there", start=0.5, end=1.0),
        ]
        seg = Segment(words=words, start=0.0, end=1.0)  # text="" by default
        srt = _segments_to_srt([seg])
        assert "hello there" in srt


class TestFormatDuration:
    def test_seconds_only(self):
        assert _format_duration(5.3) == "5.3s"

    def test_seconds_under_minute(self):
        assert _format_duration(59.9) == "59.9s"

    def test_minutes_and_seconds(self):
        assert _format_duration(65.0) == "1m 5s"

    def test_exact_minutes(self):
        assert _format_duration(120.0) == "2m 0s"

    def test_hours_minutes_seconds(self):
        assert _format_duration(3661.0) == "1h 1m 1s"

    def test_large_duration(self):
        assert _format_duration(10800.0) == "3h 0m 0s"


class TestNormalizeLanguage:
    def test_bare_english(self):
        assert _normalize_language("en") == "en-US"

    def test_bare_spanish(self):
        assert _normalize_language("es") == "es-ES"

    def test_bare_japanese(self):
        assert _normalize_language("ja") == "ja-JP"

    def test_already_full_locale_hyphen(self):
        assert _normalize_language("en-GB") == "en-GB"

    def test_already_full_locale_underscore(self):
        assert _normalize_language("en_GB") == "en_GB"

    def test_unknown_bare_code(self):
        # Falls back to "{code}-{CODE}" pattern
        assert _normalize_language("xx") == "xx-XX"
