"""SQLite + FTS5 storage for transcripts."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from .models import StoredTranscript

def _default_db_dir() -> Path:
    """Platform-appropriate data directory for transcription-mcp."""
    # macOS: ~/Library/Application Support/transcription-mcp
    app_support = Path.home() / "Library" / "Application Support" / "transcription-mcp"
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support


_DB_DIR = _default_db_dir()
_DB_PATH = _DB_DIR / "transcripts.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    duration REAL DEFAULT 0,
    language TEXT DEFAULT 'en',
    engines_used TEXT DEFAULT '[]',
    full_text TEXT DEFAULT '',
    data TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    full_text,
    source_file,
    content='transcripts',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, full_text, source_file)
    VALUES (new.rowid, new.full_text, new.source_file);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, full_text, source_file)
    VALUES ('delete', old.rowid, old.full_text, old.source_file);
END;

CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, full_text, source_file)
    VALUES ('delete', old.rowid, old.full_text, old.source_file);
    INSERT INTO transcripts_fts(rowid, full_text, source_file)
    VALUES (new.rowid, new.full_text, new.source_file);
END;
"""


async def _get_db() -> aiosqlite.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(_DB_PATH))
    await db.executescript(_SCHEMA)
    return db


async def save_transcript(transcript: StoredTranscript) -> str:
    """Save a transcript to the database. Returns the transcript ID."""
    db = await _get_db()
    try:
        engines_json = json.dumps([e.value for e in transcript.engines_used])
        data_json = transcript.model_dump_json()
        full_text = transcript.full_text

        await db.execute(
            """INSERT OR REPLACE INTO transcripts
               (id, source_file, created_at, duration, language, engines_used, full_text, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                transcript.id,
                transcript.source_file,
                transcript.created_at,
                transcript.duration,
                transcript.language,
                engines_json,
                full_text,
                data_json,
            ),
        )
        await db.commit()
        return transcript.id
    finally:
        await db.close()


async def get_transcript(transcript_id: str) -> StoredTranscript | None:
    """Retrieve a transcript by ID."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT data FROM transcripts WHERE id = ?", (transcript_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return StoredTranscript.model_validate_json(row[0])
    finally:
        await db.close()


async def list_transcripts() -> list[dict]:
    """List all transcripts with summary metadata."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            """SELECT id, source_file, created_at, duration, language, engines_used
               FROM transcripts ORDER BY created_at DESC"""
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "source_file": r[1],
                "created_at": r[2],
                "duration": r[3],
                "language": r[4],
                "engines_used": json.loads(r[5]),
            }
            for r in rows
        ]
    finally:
        await db.close()


async def search_transcripts(query: str, limit: int = 20) -> list[dict]:
    """Full-text search across all transcripts.

    Raises ValueError on malformed FTS5 query syntax.
    """
    db = await _get_db()
    try:
        try:
            cursor = await db.execute(
                """SELECT t.id, t.source_file, t.created_at, t.duration,
                          snippet(transcripts_fts, 0, '>>>', '<<<', '...', 40) as snippet
                   FROM transcripts_fts
                   JOIN transcripts t ON transcripts_fts.rowid = t.rowid
                   WHERE transcripts_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            )
        except Exception as exc:
            # FTS5 raises OperationalError on malformed queries (unbalanced
            # quotes, bare AND/OR, etc.).  Surface as ValueError so callers
            # can return a user-friendly message.
            raise ValueError(f"Invalid search query: {exc}") from exc

        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "source_file": r[1],
                "created_at": r[2],
                "duration": r[3],
                "snippet": r[4],
            }
            for r in rows
        ]
    finally:
        await db.close()


async def delete_transcript(transcript_id: str) -> bool:
    """Delete a transcript by ID. Returns True if deleted."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM transcripts WHERE id = ?", (transcript_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
