"""Unit tests for the Apple SpeechAnalyzer engine wrapper.

All tests mock the subprocess and filesystem to run on any platform —
no macOS, Swift, or SpeechAnalyzer required.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest

from transcription_mcp.engines import apple_engine
from transcription_mcp.models import Engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CLI_OUTPUT = {
    "segments": [
        {
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.4, "confidence": 0.95},
                {"word": "world", "start": 0.5, "end": 0.9},
            ],
            "start": 0.0,
            "end": 0.9,
            "text": "Hello world",
        },
        {
            "words": [
                {"word": "Testing", "start": 2.0, "end": 2.5, "confidence": 0.88},
            ],
            "start": 2.0,
            "end": 2.5,
            "text": "Testing",
        },
    ],
    "language": "en-US",
    "duration": 3.0,
}


def _make_subprocess_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# _check_platform
# ---------------------------------------------------------------------------


class TestCheckPlatform:
    def test_rejects_linux(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Linux")
        with pytest.raises(RuntimeError, match="requires macOS"):
            apple_engine._check_platform()

    def test_rejects_windows(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Windows")
        with pytest.raises(RuntimeError, match="requires macOS"):
            apple_engine._check_platform()

    def test_rejects_old_macos(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.release", lambda: "24.1.0")
        with pytest.raises(RuntimeError, match="requires macOS 26.0"):
            apple_engine._check_platform()

    def test_accepts_macos_26(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.release", lambda: "25.0.0")
        apple_engine._check_platform()  # should not raise

    def test_accepts_future_macos(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.release", lambda: "26.3.0")
        apple_engine._check_platform()  # should not raise


# ---------------------------------------------------------------------------
# _find_cli_binary
# ---------------------------------------------------------------------------


class TestFindCliBinary:
    def test_finds_bundled_binary(self, tmp_path, monkeypatch):
        """Should return the bundled package binary when it exists."""
        # Layout: <root>/transcription_mcp/engines/apple_engine.py
        #         <root>/transcription_mcp/bin/SpeechCLI
        engine_dir = tmp_path / "transcription_mcp" / "engines"
        engine_dir.mkdir(parents=True)
        fake_file = engine_dir / "apple_engine.py"
        fake_file.touch()

        bin_dir = tmp_path / "transcription_mcp" / "bin"
        bin_dir.mkdir()
        binary = bin_dir / "SpeechCLI"
        binary.touch()

        monkeypatch.setattr(apple_engine, "__file__", str(fake_file))
        result = apple_engine._find_cli_binary()
        assert result is not None
        assert result.name == "SpeechCLI"
        assert result == binary

    def test_returns_none_when_no_binary(self, tmp_path, monkeypatch):
        """Should return None when no binary exists in any location."""
        # Point __file__ to a location with no binary nearby
        fake_file = tmp_path / "engines" / "apple_engine.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.touch()

        monkeypatch.setattr(apple_engine, "__file__", str(fake_file))
        result = apple_engine._find_cli_binary()
        assert result is None

    def test_finds_dev_binary(self, tmp_path, monkeypatch):
        """Should find the binary in the development repo layout."""
        # Create dev layout: <root>/src/transcription_mcp/engines/__file__
        # Binary at:          <root>/apple-speech-cli/.build/release/SpeechCLI
        root = tmp_path / "repo"
        engine_dir = root / "src" / "transcription_mcp" / "engines"
        engine_dir.mkdir(parents=True)
        fake_file = engine_dir / "apple_engine.py"
        fake_file.touch()

        bin_dir = root / "apple-speech-cli" / ".build" / "release"
        bin_dir.mkdir(parents=True)
        binary = bin_dir / "SpeechCLI"
        binary.touch()

        monkeypatch.setattr(apple_engine, "__file__", str(fake_file))
        result = apple_engine._find_cli_binary()
        assert result is not None
        assert result.name == "SpeechCLI"


# ---------------------------------------------------------------------------
# _find_cli_source
# ---------------------------------------------------------------------------


class TestFindCliSource:
    def test_returns_none_when_no_source(self, tmp_path, monkeypatch):
        fake_file = tmp_path / "engines" / "apple_engine.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.touch()

        monkeypatch.setattr(apple_engine, "__file__", str(fake_file))
        result = apple_engine._find_cli_source()
        assert result is None

    def test_finds_bundled_source(self, tmp_path, monkeypatch):
        """Should find source inside the installed package."""
        pkg_dir = tmp_path / "transcription_mcp"
        engine_dir = pkg_dir / "engines"
        engine_dir.mkdir(parents=True)
        fake_file = engine_dir / "apple_engine.py"
        fake_file.touch()

        src_dir = pkg_dir / "apple-speech-cli"
        src_dir.mkdir()
        (src_dir / "Package.swift").touch()

        monkeypatch.setattr(apple_engine, "__file__", str(fake_file))
        result = apple_engine._find_cli_source()
        assert result is not None
        assert (result / "Package.swift").exists()

    def test_finds_dev_source(self, tmp_path, monkeypatch):
        """Should find source in the development repo layout."""
        root = tmp_path / "repo"
        engine_dir = root / "src" / "transcription_mcp" / "engines"
        engine_dir.mkdir(parents=True)
        fake_file = engine_dir / "apple_engine.py"
        fake_file.touch()

        src_dir = root / "apple-speech-cli"
        src_dir.mkdir()
        (src_dir / "Package.swift").touch()

        monkeypatch.setattr(apple_engine, "__file__", str(fake_file))
        result = apple_engine._find_cli_source()
        assert result is not None
        assert (result / "Package.swift").exists()


# ---------------------------------------------------------------------------
# _swift_available
# ---------------------------------------------------------------------------


class TestSwiftAvailable:
    def test_returns_true_when_swift_exists(self, monkeypatch):
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(),
        )
        assert apple_engine._swift_available() is True

    def test_returns_false_when_not_found(self, monkeypatch):
        def raise_not_found(*a, **kw):
            raise FileNotFoundError("swift not found")

        monkeypatch.setattr("subprocess.run", raise_not_found)
        assert apple_engine._swift_available() is False

    def test_returns_false_on_timeout(self, monkeypatch):
        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="swift", timeout=10)

        monkeypatch.setattr("subprocess.run", raise_timeout)
        assert apple_engine._swift_available() is False


# ---------------------------------------------------------------------------
# _ensure_built
# ---------------------------------------------------------------------------


class TestEnsureBuilt:
    def test_returns_existing_binary(self, monkeypatch):
        sentinel = Path("/fake/SpeechCLI")
        monkeypatch.setattr(apple_engine, "_check_platform", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_binary", lambda: sentinel)

        assert apple_engine._ensure_built() == sentinel

    def test_raises_when_no_binary_and_no_source(self, monkeypatch):
        monkeypatch.setattr(apple_engine, "_check_platform", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_binary", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_source", lambda: None)

        with pytest.raises(RuntimeError, match="no source available"):
            apple_engine._ensure_built()

    def test_raises_when_no_binary_and_no_swift(self, monkeypatch):
        monkeypatch.setattr(apple_engine, "_check_platform", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_binary", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_source", lambda: Path("/src"))
        monkeypatch.setattr(apple_engine, "_swift_available", lambda: False)

        with pytest.raises(RuntimeError, match="Swift toolchain is not installed"):
            apple_engine._ensure_built()

    def test_raises_on_build_failure(self, monkeypatch):
        monkeypatch.setattr(apple_engine, "_check_platform", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_binary", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_source", lambda: Path("/src"))
        monkeypatch.setattr(apple_engine, "_swift_available", lambda: True)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(returncode=1, stderr="build error"),
        )

        with pytest.raises(RuntimeError, match="Failed to build SpeechCLI"):
            apple_engine._ensure_built()

    def test_raises_when_build_succeeds_but_binary_missing(self, tmp_path, monkeypatch):
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        monkeypatch.setattr(apple_engine, "_check_platform", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_binary", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_source", lambda: source_dir)
        monkeypatch.setattr(apple_engine, "_swift_available", lambda: True)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(returncode=0),
        )

        with pytest.raises(RuntimeError, match="Build succeeded but binary not found"):
            apple_engine._ensure_built()

    def test_returns_built_binary(self, tmp_path, monkeypatch):
        source_dir = tmp_path / "source"
        bin_path = source_dir / ".build" / "release" / "SpeechCLI"
        bin_path.parent.mkdir(parents=True)
        bin_path.touch()

        monkeypatch.setattr(apple_engine, "_check_platform", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_binary", lambda: None)
        monkeypatch.setattr(apple_engine, "_find_cli_source", lambda: source_dir)
        monkeypatch.setattr(apple_engine, "_swift_available", lambda: True)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(returncode=0),
        )

        result = apple_engine._ensure_built()
        assert result == bin_path


# ---------------------------------------------------------------------------
# transcribe — JSON parsing and model construction
# ---------------------------------------------------------------------------


class TestTranscribe:
    def test_parses_cli_output(self, tmp_path, monkeypatch):
        """Verify correct parsing of SpeechCLI JSON into TranscriptResult."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        monkeypatch.setattr(
            apple_engine, "_ensure_built", lambda: Path("/fake/SpeechCLI")
        )
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(
                stdout=json.dumps(SAMPLE_CLI_OUTPUT),
            ),
        )

        result = apple_engine.transcribe(audio_file, language="en-US")

        assert result.engine == Engine.APPLE
        assert result.language == "en-US"
        assert result.duration == 3.0
        assert len(result.segments) == 2

        # First segment
        seg0 = result.segments[0]
        assert seg0.text == "Hello world"
        assert seg0.start == 0.0
        assert seg0.end == 0.9
        assert len(seg0.words) == 2
        assert seg0.words[0].word == "Hello"
        assert seg0.words[0].confidence == 0.95
        assert seg0.words[0].engine == Engine.APPLE
        # "world" has no explicit confidence — should default to 1.0
        assert seg0.words[1].confidence == 1.0

        # Second segment
        seg1 = result.segments[1]
        assert seg1.text == "Testing"
        assert len(seg1.words) == 1
        assert seg1.words[0].confidence == 0.88

    def test_raises_on_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            apple_engine, "_ensure_built", lambda: Path("/fake/SpeechCLI")
        )

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            apple_engine.transcribe(tmp_path / "nonexistent.wav")

    def test_raises_on_cli_failure(self, tmp_path, monkeypatch):
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        monkeypatch.setattr(
            apple_engine, "_ensure_built", lambda: Path("/fake/SpeechCLI")
        )
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(
                returncode=1, stderr="SpeechAnalyzer error"
            ),
        )

        with pytest.raises(RuntimeError, match="SpeechCLI failed"):
            apple_engine.transcribe(audio_file)

    def test_handles_missing_optional_fields(self, tmp_path, monkeypatch):
        """CLI output without 'language' or 'duration' should use defaults."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        minimal_output = {
            "segments": [
                {
                    "words": [
                        {"word": "Hi", "start": 0.0, "end": 0.3},
                    ],
                    "start": 0.0,
                    "end": 0.3,
                },
            ],
        }

        monkeypatch.setattr(
            apple_engine, "_ensure_built", lambda: Path("/fake/SpeechCLI")
        )
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(
                stdout=json.dumps(minimal_output),
            ),
        )

        result = apple_engine.transcribe(audio_file, language="ja-JP")

        # Should use the passed language as fallback
        assert result.language == "ja-JP"
        assert result.duration == 0.0
        # Segment text should be computed from words when missing
        assert result.segments[0].text == "Hi"

    def test_accepts_string_path(self, tmp_path, monkeypatch):
        """transcribe() should accept str paths, not just Path objects."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        monkeypatch.setattr(
            apple_engine, "_ensure_built", lambda: Path("/fake/SpeechCLI")
        )
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_subprocess_result(
                stdout=json.dumps(SAMPLE_CLI_OUTPUT),
            ),
        )

        result = apple_engine.transcribe(str(audio_file))
        assert result.engine == Engine.APPLE
