"""Apple SpeechAnalyzer engine — wraps the Swift CLI subprocess."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

from ..models import Engine, Segment, TranscriptResult, Word


def _check_platform() -> None:
    """Fail fast with a clear error on unsupported platforms."""
    if platform.system() != "Darwin":
        raise RuntimeError(
            "transcription-mcp requires macOS. "
            "Apple SpeechAnalyzer is not available on other platforms."
        )
    # macOS 26 = Darwin 25.x
    darwin_major = int(platform.release().split(".")[0])
    if darwin_major < 25:
        raise RuntimeError(
            "transcription-mcp requires macOS 26.0 or later. "
            f"You are running Darwin {platform.release()}."
        )
    # SpeechAnalyzer requires Apple Silicon (Neural Engine)
    arch = platform.machine()
    if arch != "arm64":
        raise RuntimeError(
            "transcription-mcp requires Apple Silicon (M1 or later). "
            f"Detected architecture: {arch}. "
            "SpeechAnalyzer uses the Neural Engine, which is only available "
            "on Apple Silicon Macs."
        )


def _find_cli_binary() -> Path | None:
    """Search for the SpeechCLI binary in known locations."""
    # 1. Built binary inside the installed/bundled package source
    pkg_src = Path(__file__).resolve().parent.parent / "apple-speech-cli"
    pkg_bin = pkg_src / ".build" / "release" / "SpeechCLI"
    if pkg_bin.exists():
        return pkg_bin

    # 2. Development layout: repo root / apple-speech-cli / .build / release
    dev_cli_dir = Path(__file__).resolve().parent.parent.parent.parent / "apple-speech-cli"
    dev_bin = dev_cli_dir / ".build" / "release" / "SpeechCLI"
    if dev_bin.exists():
        return dev_bin

    return None


def _find_cli_source() -> Path | None:
    """Find the Swift CLI source for building from source."""
    # 1. Bundled source inside installed package
    pkg_src = Path(__file__).resolve().parent.parent / "apple-speech-cli"
    if (pkg_src / "Package.swift").exists():
        return pkg_src

    # 2. Development layout
    dev_src = Path(__file__).resolve().parent.parent.parent.parent / "apple-speech-cli"
    if (dev_src / "Package.swift").exists():
        return dev_src

    return None


def _ensure_built() -> Path:
    """Find or build the Swift CLI binary."""
    _check_platform()

    # Try to find an existing binary
    binary = _find_cli_binary()
    if binary is not None:
        return binary

    # Try to build from bundled source
    source_dir = _find_cli_source()
    if source_dir is None:
        raise RuntimeError(
            "SpeechCLI binary not found and no source available to build from.\n"
            "Try reinstalling: pip install --force-reinstall transcription-mcp"
        )

    # Check swift is available
    if not _swift_available():
        raise RuntimeError(
            "SpeechCLI binary not found and Swift toolchain is not installed.\n"
            "Either install Xcode (or Xcode Command Line Tools with Swift 6.2+),\n"
            "or reinstall the package which includes a pre-built binary:\n"
            "  pip install --force-reinstall transcription-mcp"
        )

    result = subprocess.run(
        ["swift", "build", "-c", "release"],
        cwd=str(source_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to build SpeechCLI:\n{result.stderr}")

    built_bin = source_dir / ".build" / "release" / "SpeechCLI"
    if not built_bin.exists():
        raise RuntimeError(
            f"Build succeeded but binary not found at {built_bin}\n"
            f"stderr: {result.stderr}"
        )
    return built_bin


def _swift_available() -> bool:
    """Check if the Swift compiler is available."""
    try:
        subprocess.run(
            ["swift", "--version"], capture_output=True, timeout=10
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def transcribe(audio_path: str | Path, language: str = "en-US") -> TranscriptResult:
    """Transcribe an audio file using Apple SpeechAnalyzer via the Swift CLI."""
    cli = _ensure_built()
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    result = subprocess.run(
        [str(cli), str(audio_path), language],
        capture_output=True,
        text=True,
        timeout=14400,  # 4 hour timeout for long files
    )

    if result.returncode != 0:
        raise RuntimeError(f"SpeechCLI failed:\n{result.stderr}")

    data = json.loads(result.stdout)

    segments = []
    for seg_data in data["segments"]:
        words = [
            Word(
                word=w["word"],
                start=w["start"],
                end=w["end"],
                confidence=w.get("confidence", 1.0),
                engine=Engine.APPLE,
            )
            for w in seg_data["words"]
        ]
        segments.append(
            Segment(
                words=words,
                start=seg_data["start"],
                end=seg_data["end"],
                text=seg_data.get("text", " ".join(w.word for w in words)),
            )
        )

    return TranscriptResult(
        engine=Engine.APPLE,
        segments=segments,
        language=data.get("language", language),
        duration=data.get("duration", 0.0),
    )
