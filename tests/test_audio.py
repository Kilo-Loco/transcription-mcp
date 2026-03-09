"""Tests for audio extraction utilities."""

from pathlib import Path

import pytest

from transcription_mcp.audio import extract_audio, extract_slice, get_audio_duration


class TestGetAudioDuration:
    def test_real_mp3(self, sample_audio):
        duration = get_audio_duration(sample_audio)
        assert duration > 0
        # The test file is a short clip, should be under 2 minutes
        assert duration < 120

    def test_nonexistent_file(self):
        with pytest.raises(RuntimeError):
            get_audio_duration("/tmp/nonexistent_audio.mp3")


class TestExtractAudio:
    def test_mp3_to_wav(self, sample_audio):
        wav_path = extract_audio(sample_audio)
        try:
            assert wav_path.exists()
            assert wav_path.suffix == ".wav"
            assert wav_path != sample_audio  # should be a new file
        finally:
            wav_path.unlink(missing_ok=True)

    def test_wav_passthrough(self, sample_audio, tmp_dir):
        # First convert to WAV, then verify passthrough
        wav_path = extract_audio(sample_audio)
        try:
            result = extract_audio(wav_path)
            assert result == wav_path  # WAV files pass through unchanged
        finally:
            wav_path.unlink(missing_ok=True)

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            extract_audio("/tmp/nonexistent.mp3")


class TestExtractSlice:
    def test_extract_slice(self, sample_audio):
        duration = get_audio_duration(sample_audio)
        # Extract a 2-second slice from the beginning
        end = min(2.0, duration)
        slice_path = extract_slice(sample_audio, 0.0, end)
        try:
            assert slice_path.exists()
            assert slice_path.suffix == ".m4a"
            slice_duration = get_audio_duration(slice_path)
            assert slice_duration > 0
            assert slice_duration <= end + 0.5  # allow small ffmpeg rounding
        finally:
            slice_path.unlink(missing_ok=True)

    def test_extract_slice_custom_output(self, sample_audio, tmp_dir):
        out = tmp_dir / "my_slice.m4a"
        result = extract_slice(sample_audio, 0.0, 1.0, output_path=out)
        assert result == out
        assert out.exists()

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            extract_slice("/tmp/nonexistent.mp3", 0.0, 1.0)
