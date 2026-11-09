"""
Database module for Sahaayak Pro.
SQLite database using built-in sqlite3 for offline-first case and settings management.
"""

import sqlite3
import os
import uuid
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get(
    'SAHAAYAK_DB_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sahaayak_pro.db')
)

_initialized = False


def get_db(db_path=None):
    """
    Get a database connection with row factory.
    Enables WAL mode for concurrent reads/writes.
    """
    path = db_path or os.environ.get('SAHAAYAK_DB_PATH', DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path=None):
    """Create tables if they don't exist."""
    global _initialized
    path = db_path or os.environ.get('SAHAAYAK_DB_PATH', DB_PATH)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        with conn:
            # Table: cases
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    patient_group TEXT,
                    age_months INTEGER,
                    gender TEXT,
                    symptoms TEXT,
                    symptom_text TEXT,
                    risk TEXT,
                    risk_level INTEGER,
                    reasons TEXT,
                    protocol_refs TEXT,
                    explanation TEXT,
                    rules_fired TEXT,
                    sync_status TEXT DEFAULT 'saved_locally',
                    synced_at TEXT,
                    language TEXT DEFAULT 'en'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_case_id ON cases(case_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_sync_status ON cases(sync_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at)")

            # Table: settings
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Table: rules_version
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rules_version (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source TEXT NOT NULL
                )
            """)
        _initialized = True
    finally:
        conn.close()


def _ensure_db_initialized():
    """Ensure database schema is created at least once."""
    global _initialized
    if not _initialized:
        init_db()


def row_to_dict(row):
    """
    Convert a sqlite3.Row or dict to a dictionary and parse JSON fields back to lists.
    Fields parsed: symptoms, reasons, protocol_refs, rules_fired.
    """
    if row is None:
        return None
    
    d = dict(row)
    json_fields = ('symptoms', 'reasons', 'protocol_refs', 'rules_fired')
    for field in json_fields:
        val = d.get(field)
        if val is None:
            d[field] = []
        elif isinstance(val, (list, dict)):
            d[field] = val
        elif isinstance(val, str):
            val_clean = val.strip()
            if not val_clean:
                d[field] = []
            elif (val_clean.startswith('[') and val_clean.endswith(']')) or \
                 (val_clean.startswith('{') and val_clean.endswith('}')):
                try:
                    d[field] = json.loads(val_clean)
                except Exception:
                    d[field] = [val_clean]
            else:
                d[field] = [val_clean]
        else:
            d[field] = [val]
    return d


def _serialize_json_field(val):
    """Serialize a field to a JSON string formatted for SQLite storage."""
    if val is None:
        return "[]"
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, str):
        v_strip = val.strip()
        if (v_strip.startswith('[') and v_strip.endswith(']')) or \
           (v_strip.startswith('{') and v_strip.endswith('}')):
            return v_strip
        return json.dumps([v_strip] if v_strip else [], ensure_ascii=False)
    return json.dumps([val], ensure_ascii=False)


def generate_case_id():
    """Generate a unique case ID like C-A1B2C3D4."""
    return f"C-{uuid.uuid4().hex[:8].upper()}"


def save_case(case_data):
    """
    Save a case and return the case_id.
    case_data is a dict containing case attributes.
    Generates case_id if not present, sets created_at if missing,
    and defaults sync_status to 'saved_locally'.
    """
    _ensure_db_initialized()
    data = dict(case_data)
    
    case_id = data.get('case_id') or generate_case_id()
    created_at = data.get('created_at') or datetime.utcnow().isoformat()
    patient_group = data.get('patient_group')
    age_months = data.get('age_months')
    gender = data.get('gender')
    symptoms = _serialize_json_field(data.get('symptoms'))
    symptom_text = data.get('symptom_text')
    risk = data.get('risk')
    risk_level = data.get('risk_level')
    reasons = _serialize_json_field(data.get('reasons'))
    protocol_refs = _serialize_json_field(data.get('protocol_refs'))
    explanation = data.get('explanation')
    rules_fired = _serialize_json_field(data.get('rules_fired'))
    sync_status = data.get('sync_status') or 'saved_locally'
    synced_at = data.get('synced_at')
    language = data.get('language') or 'en'

    with get_db() as conn:
        conn.execute("""
            INSERT INTO cases (
                case_id, created_at, patient_group, age_months, gender,
                symptoms, symptom_text, risk, risk_level, reasons,
                protocol_refs, explanation, rules_fired, sync_status,
                synced_at, language
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case_id, created_at, patient_group, age_months, gender,
            symptoms, symptom_text, risk, risk_level, reasons,
            protocol_refs, explanation, rules_fired, sync_status,
            synced_at, language
        ))
        conn.commit()

    return case_id


def get_case(case_id):
    """Get a single case by case_id. Returns dict or None."""
    _ensure_db_initialized()
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        row = cursor.fetchone()
        if row:
            return row_to_dict(row)
        return None


def get_all_cases(limit=100, offset=0):
    """Get all cases ordered by created_at DESC. Returns list of dicts."""
    _ensure_db_initialized()
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM cases ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = cursor.fetchall()
        return [row_to_dict(r) for r in rows]


def get_pending_cases():
    """Get cases with sync_status = 'pending' or 'saved_locally'."""
    _ensure_db_initialized()
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM cases WHERE sync_status IN ('pending', 'saved_locally') ORDER BY created_at ASC"
        )
        rows = cursor.fetchall()
        return [row_to_dict(r) for r in rows]


def mark_synced(case_id):
    """Update sync_status to 'synced' and set synced_at."""
    _ensure_db_initialized()
    now_iso = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE cases SET sync_status = 'synced', synced_at = ? WHERE case_id = ?",
            (now_iso, case_id)
        )
        conn.commit()


def mark_pending(case_id):
    """Update sync_status to 'pending'."""
    _ensure_db_initialized()
    with get_db() as conn:
        conn.execute(
            "UPDATE cases SET sync_status = 'pending' WHERE case_id = ?",
            (case_id,)
        )
        conn.commit()


def delete_case(case_id):
    """Delete a case by case_id. Returns True if deleted, False otherwise."""
    _ensure_db_initialized()
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        conn.commit()
        return cursor.rowcount > 0


def _format_size(size_bytes):
    """Format bytes into human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def get_stats():
    """Return dict with total_cases, pending_count, synced_count, db_size_bytes, db_size_human."""
    _ensure_db_initialized()
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM cases WHERE sync_status IN ('pending', 'saved_locally')"
        ).fetchone()[0]
        synced = conn.execute(
            "SELECT COUNT(*) FROM cases WHERE sync_status = 'synced'"
        ).fetchone()[0]

    db_file = os.environ.get('SAHAAYAK_DB_PATH', DB_PATH)
    try:
        size_bytes = os.path.getsize(db_file) if os.path.exists(db_file) else 0
    except OSError:
        size_bytes = 0

    return {
        "total_cases": total,
        "pending_count": pending,
        "synced_count": synced,
        "db_size_bytes": size_bytes,
        "db_size_human": _format_size(size_bytes)
    }


def get_setting(key, default=None):
    """Get a setting value."""
    _ensure_db_initialized()
    with get_db() as conn:
        cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row is not None:
            return row[0]
        return default


def set_setting(key, value):
    """Set a setting value (upsert)."""
    _ensure_db_initialized()
    val_str = str(value) if value is not None else ""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, val_str)
        )
        conn.commit()


def get_cases_for_export():
    """Get all cases as a list of plain dicts (not Row objects) for CSV/JSON export."""
    _ensure_db_initialized()
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM cases ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [row_to_dict(r) for r in rows]


def get_rules_version():
    """Get the latest rule version record as a dict or None."""
    _ensure_db_initialized()
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT version, updated_at, source FROM rules_version ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            return {
                "version": row["version"],
                "updated_at": row["updated_at"],
                "source": row["source"]
            }
        return None


def set_rules_version(version, source="local"):
    """Record a new rule version."""
    _ensure_db_initialized()
    now_iso = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO rules_version (version, updated_at, source) VALUES (?, ?, ?)",
            (version, now_iso, source)
        )
        conn.commit()


# Initialize database automatically on module import
init_db()
