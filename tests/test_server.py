"""Tests for the MCP server tools — SRT formatting and server-level integration."""

import pytest

from transcription_mcp.models import Engine, Segment, Word
from transcription_mcp.server import _format_srt_time, _segments_to_srt


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
