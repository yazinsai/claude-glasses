from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SessionStatus(Enum):
    BUSY = "busy"
    IDLE = "idle"
    DONE = "done"


@dataclass
class ClaudeSession:
    session_id: str
    project_path: str
    project_name: str
    session_file: str
    pid: Optional[int] = None
    status: SessionStatus = SessionStatus.DONE
    start_time: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    last_message_type: str = "unknown"
    slug: Optional[str] = None
    cwd: Optional[str] = None
    duration_seconds: float = 0.0
    progress_summary: Optional[str] = None

    def format_duration(self) -> str:
        """Format duration as HH:MM:SS."""
        total_seconds = int(self.duration_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m {secs}s"


@dataclass
class AppState:
    sessions: dict[str, ClaudeSession] = field(default_factory=dict)
    notifications_enabled: bool = True
    last_scan_time: Optional[datetime] = None
