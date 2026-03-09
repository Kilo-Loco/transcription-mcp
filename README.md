# Transcription MCP

Local transcription at **76x realtime** using Apple's Neural Engine. Zero API costs. YouTube-ready captions.

Transcribe a 3-hour video in under 3 minutes. Everything runs on-device — your audio never leaves your Mac.

## What It Does

- **Transcribes audio and video** files using Apple SpeechAnalyzer on the Neural Engine
- **Generates `.srt` subtitle files** ready for YouTube caption upload
- **Writes `.txt` transcripts** alongside the source file
- **Stores transcripts** in a searchable SQLite archive with full-text search
- **Extracts audio slices** so Claude can listen to and verify unclear words
- Works with **Claude Code**, **OpenClaw**, and any MCP-compatible client

## Install

```bash
pip install transcription-mcp
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install transcription-mcp
```

## Quick Start

### 1. Add to Claude Code

Add to your `~/.claude.json`:

```json
{
  "mcpServers": {
    "transcription": {
      "command": "transcription-mcp",
      "args": []
    }
  }
}
```

### 2. Transcribe

In Claude Code, just ask:

> "Transcribe /path/to/my-video.mp4"

Claude will transcribe the file, clean up the output, and present the formatted transcript. An `.srt` file for YouTube captions is written automatically.

### 3. Search Past Transcripts

> "Search my transcripts for 'neural engine'"

## Features

| Feature | Details |
|---------|---------|
| **Speed** | ~76x realtime on Apple Neural Engine (M1/M2/M3/M4) |
| **Privacy** | 100% on-device — audio never leaves your Mac |
| **Captions** | YouTube-ready `.srt` files with word-level timestamps |
| **Search** | Full-text search across all past transcripts (SQLite + FTS5) |
| **Formats** | Any audio/video format supported by ffmpeg |
| **Languages** | All languages supported by Apple SpeechAnalyzer |
| **Cost** | Free forever — no API keys, no subscriptions, no cloud |

## Requirements

- **macOS 26.0** (Tahoe) or later
- **Apple Silicon** (M1/M2/M3/M4) — uses the Neural Engine
- **ffmpeg** — for audio extraction from video files
  ```bash
  brew install ffmpeg
  ```
- **Python 3.11+**

## How It Works

```
Audio/Video File
       |
       v
   [ffmpeg] ──> 16kHz mono WAV
       |
       v
  [SpeechCLI] ──> Apple SpeechAnalyzer (Neural Engine)
       |
       v
  JSON (word-level timestamps + segments)
       |
       v
  [MCP Server] ──> .txt transcript
                ──> .srt subtitles
                ──> SQLite archive (searchable)
```

The Swift CLI (`SpeechCLI`) wraps Apple's `SpeechAnalyzer` framework, which runs transcription on the Neural Engine — dedicated hardware for ML inference. This is why it's so fast: it's not using your CPU or GPU.

## MCP Tools Reference

### `transcribe`
Transcribe an audio or video file. Produces `.txt` and `.srt` files next to the source.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | string | required | Absolute path to the audio/video file |
| `language` | string | `"en"` | Language code (e.g., `"en"`, `"es"`, `"ja"`) |

### `get_transcript`
Retrieve a stored transcript by ID with optional time filtering.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `transcript_id` | string | required | The transcript ID |
| `format` | string | `"segments"` | `"segments"` or `"words"` |
| `start_time` | float | null | Filter to words after this time (seconds) |
| `end_time` | float | null | Filter to words before this time (seconds) |

### `get_audio_slice`
Extract a short audio clip for word verification.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `transcript_id` | string | required | The transcript ID |
| `start_time` | float | required | Start time in seconds |
| `end_time` | float | required | End time in seconds |

### `search_transcripts`
Full-text search across all stored transcripts. Supports FTS5 syntax (AND, OR, NOT, phrases).

### `list_transcripts`
List all stored transcripts with metadata.

## FAQ

**Q: Does this work on Intel Macs?**
A: No. Apple SpeechAnalyzer requires Apple Silicon (M1 or later) and macOS 26.

**Q: What audio/video formats are supported?**
A: Anything ffmpeg can decode — MP4, MOV, MKV, MP3, M4A, WAV, FLAC, and many more.

**Q: How accurate is the transcription?**
A: Apple SpeechAnalyzer uses on-device neural models. Accuracy is comparable to cloud services for clear speech. Claude reviews and cleans up the output.

**Q: Where are transcripts stored?**
A: In `~/Library/Application Support/transcription-mcp/transcripts.db`. This is a standard SQLite database you can query directly.

**Q: Can I use this without Claude Code?**
A: Yes — it works with any MCP client. You can also run `transcription-mcp` directly as a stdio MCP server.

**Q: Is my audio data sent anywhere?**
A: No. Everything runs locally on your Mac. No network calls, no cloud APIs, no telemetry.

## License

MIT
