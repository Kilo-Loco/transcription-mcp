"""Tests for Pydantic data models."""

from transcription_mcp.models import Engine, Segment, StoredTranscript, TranscriptResult, Word


class TestWord:
    def test_create_word(self):
        w = Word(word="hello", start=0.0, end=0.5)
        assert w.word == "hello"
        assert w.confidence == 1.0
        assert w.engine is None

    def test_word_with_engine(self):
        w = Word(word="hello", start=0.0, end=0.5, engine=Engine.APPLE)
        assert w.engine == Engine.APPLE


class TestSegment:
    def test_compute_text(self):
        words = [
            Word(word="hello", start=0.0, end=0.5),
            Word(word="world", start=0.5, end=1.0),
        ]
        seg = Segment(words=words, start=0.0, end=1.0)
        assert seg.compute_text() == "hello world"
        assert seg.text == "hello world"

    def test_empty_segment(self):
        seg = Segment(words=[], start=0.0, end=0.0)
        assert seg.compute_text() == ""


class TestTranscriptResult:
    def test_full_text(self, sample_transcript_result):
        text = sample_transcript_result.full_text
        assert "Hello world" in text
        assert "this is a test" in text

    def test_words_flattened(self, sample_transcript_result):
        words = sample_transcript_result.words
        assert len(words) == 6
        assert words[0].word == "Hello"
        assert words[-1].word == "test"

    def test_duration(self, sample_transcript_result):
        assert sample_transcript_result.duration == 3.0


class TestStoredTranscript:
    def test_auto_id(self):
        t = StoredTranscript(source_file="test.mp4")
        assert len(t.id) == 12

    def test_unique_ids(self):
        t1 = StoredTranscript(source_file="test.mp4")
        t2 = StoredTranscript(source_file="test.mp4")
        assert t1.id != t2.id

    def test_full_text_with_result(self, sample_stored_transcript):
        assert "Hello world" in sample_stored_transcript.full_text

    def test_full_text_without_result(self):
        t = StoredTranscript(source_file="test.mp4")
        assert t.full_text == ""

    def test_serialization_roundtrip(self, sample_stored_transcript):
        json_str = sample_stored_transcript.model_dump_json()
        restored = StoredTranscript.model_validate_json(json_str)
        assert restored.id == sample_stored_transcript.id
        assert restored.source_file == sample_stored_transcript.source_file
        assert restored.full_text == sample_stored_transcript.full_text
        assert len(restored.apple_result.words) == 6
