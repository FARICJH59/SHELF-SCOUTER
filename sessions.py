"""
In-memory session store for shelf-scanning sessions.

Each session tracks GPS/orientation metadata, uploaded frames, and the
final multi-frame fusion result.  Sessions are stored in a module-level
dict protected by a threading lock so the store is safe under Gunicorn
threads (though not across multiple worker processes; use Redis for that).
"""

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional


_store: dict[str, dict] = {}
_lock = threading.Lock()


def create_session(
    gps: dict,
    orientation: dict,
    store_id: Optional[str] = None,
) -> dict:
    """
    Create and persist a new scanning session.

    Args:
        gps: ``{"latitude": float, "longitude": float, "accuracy": float}``
        orientation: ``{"pitch": float, "yaw": float, "roll": float}``
        store_id: Pre-resolved store identifier (may be ``None`` if the
            caller wants the backend to resolve it from GPS).

    Returns:
        The newly created session dict.
    """
    session_id = str(uuid.uuid4())
    session: dict = {
        "session_id": session_id,
        "store_id": store_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gps": gps,
        "orientation": orientation,
        "aisle": None,
        "shelf": None,
        "frames": [],
        "status": "open",
        "result": None,
    }
    with _lock:
        _store[session_id] = session
    return session


def get_session(session_id: str) -> Optional[dict]:
    """Return the session dict for *session_id*, or ``None``."""
    with _lock:
        return _store.get(session_id)


def add_frame(session_id: str, frame: dict) -> bool:
    """
    Append a processed frame record to the session.

    Args:
        session_id: Target session.
        frame: Dict with at least ``{"frame_index": int, "result": dict}``.

    Returns:
        ``True`` on success, ``False`` if the session does not exist or is
        already finalised.
    """
    with _lock:
        session = _store.get(session_id)
        if session is None or session["status"] != "open":
            return False
        session["frames"].append(frame)
        return True


def finalize_session(session_id: str, result: dict) -> bool:
    """
    Mark a session as finalised and attach the fused result.

    Args:
        session_id: Target session.
        result: Fused product detection result.

    Returns:
        ``True`` on success, ``False`` if the session does not exist.
    """
    with _lock:
        session = _store.get(session_id)
        if session is None:
            return False
        session["status"] = "finalized"
        session["result"] = result
        return True
