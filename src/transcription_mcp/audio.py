"""Audio extraction utilities using ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def _check_ffmpeg() -> None:
    """Fail fast with a clear message if ffmpeg/ffprobe are not installed."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is required but not found.\n"
            "Install it with: brew install ffmpeg"
        )


def extract_audio(input_path: str | Path, sample_rate: int = 16000) -> Path:
    """Extract audio from a video/audio file to a 16kHz mono WAV.

    Returns the path to the temporary WAV file. Caller is responsible
    for cleanup.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = input_path.suffix.lower()
    # If already a WAV, return as-is
    if suffix == ".wav":
        return input_path

    _check_ffmpeg()

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    out_path = Path(tmp.name)

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-ar", str(sample_rate),
        "-ac", "1",
        "-f", "wav",
        "-y",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    return out_path


def extract_slice(
    input_path: str | Path,
    start_time: float,
    end_time: float,
    output_path: str | Path | None = None,
) -> Path:
    """Extract a short audio slice from a file.

    Args:
        input_path: Path to the source audio/video file.
        start_time: Start time in seconds.
        end_time: End time in seconds.
        output_path: Where to write the slice. If None, uses a temp file.

    Returns:
        Path to the extracted audio slice (m4a).
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    _check_ffmpeg()

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False)
        tmp.close()
        output_path = Path(tmp.name)
    else:
        output_path = Path(output_path)

    duration = end_time - start_time
    cmd = [
        "ffmpeg",
        "-ss", str(start_time),
        "-i", str(input_path),
        "-t", str(duration),
        "-vn",
        "-acodec", "aac",
        "-y",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg slice failed: {result.stderr}")

    return output_path


def get_audio_duration(file_path: str | Path) -> float:
    """Get the duration of an audio/video file in seconds."""
    _check_ffmpeg()
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())
