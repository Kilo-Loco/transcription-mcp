---
name: transcription-mcp
description: >
  Transcribe audio and video files locally on Mac using Apple SpeechAnalyzer
  (Neural Engine). 76x realtime speed, word-level timestamps, YouTube-ready
  SRT captions. Zero API costs — everything runs on-device.
license: MIT
allowed-tools:
  - bash
  - mcp
metadata:
  clawdbot:
    requires:
      bins:
        - ffmpeg
        - python3
    homepage: https://github.com/Kilo-Loco/transcription-mcp
compatibility: macOS 26+ only. Requires ffmpeg (brew install ffmpeg) and Apple Silicon.
---

# Transcription MCP Skill

You have access to a local transcription server powered by Apple's Neural Engine.
It transcribes audio and video at ~76x realtime with zero cloud costs.

## Setup

If the transcription MCP server is not already configured, install it:

```bash
pip install transcription-mcp
```

Then add to the MCP configuration:

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

## How to Transcribe

1. Call the `transcribe` tool with the absolute file path:
   - It accepts any audio or video format (MP4, MOV, MP3, M4A, WAV, etc.)
   - It produces a `.txt` transcript and `.srt` subtitle file next to the source
   - It returns a transcript ID, file paths, duration, and word count

2. Read the generated `.txt` file and clean it up:
   - Fix capitalization and punctuation
   - Add paragraph breaks at natural topic changes
   - Do NOT guess at word corrections from text alone

3. If any words look wrong or don't fit context, use `get_audio_slice` with
   the timestamp range to listen to that section. Only correct words you can
   verify by hearing them.

4. Present the cleaned transcript to the user.

## Other Available Tools

- `get_transcript` — retrieve word-level timestamps or filter by time range
- `search_transcripts` — full-text search across all past transcripts
- `list_transcripts` — list all stored transcripts with metadata
- `get_audio_slice` — extract a short audio clip for verification

## Important Notes

- The `.srt` file is ready for YouTube caption upload — no further processing needed
- Transcripts are archived in SQLite with full-text search
- Everything runs locally on the Mac's Neural Engine — no data leaves the device
- Requires macOS 26+ and Apple Silicon (M1/M2/M3/M4)
- Requires ffmpeg for video audio extraction (`brew install ffmpeg`)
