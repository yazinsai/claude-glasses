import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from claude_glasses.models import ClaudeSession, SessionStatus


class ProcessScanner:
    """Scans for running Claude Code processes."""

    def scan_claude_processes(self) -> dict[str, int]:
        """Returns dict mapping project_path -> PID for running claude sessions."""
        result = {}

        try:
            ps_output = subprocess.check_output(
                ["ps", "aux"], text=True, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            return result

        claude_pids = []
        for line in ps_output.splitlines():
            parts = line.split()
            if len(parts) >= 11:
                # Column 11 is the command - match only 'claude' or 'claude --resume' etc
                cmd = parts[10]
                if cmd == "claude":
                    try:
                        claude_pids.append(int(parts[1]))
                    except ValueError:
                        continue

        for pid in claude_pids:
            try:
                lsof_output = subprocess.check_output(
                    ["lsof", "-p", str(pid)], text=True, stderr=subprocess.DEVNULL
                )
                for line in lsof_output.splitlines():
                    if "\tcwd\t" in line or " cwd " in line:
                        # Extract path - it's the last field
                        path = line.split()[-1]
                        if path.startswith("/"):
                            result[path] = pid
                        break
            except subprocess.CalledProcessError:
                continue

        return result


class SessionFileScanner:
    """Scans Claude session files for metadata."""

    def __init__(self, claude_dir: Optional[Path] = None):
        self.claude_dir = claude_dir or Path.home() / ".claude"
        self.projects_dir = self.claude_dir / "projects"

    def get_active_sessions(self, hours: int = 24) -> list[ClaudeSession]:
        """Scan for recent session files."""
        sessions = []
        cutoff = time.time() - (hours * 3600)

        if not self.projects_dir.exists():
            return sessions

        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            for session_file in project_dir.glob("*.jsonl"):
                # Skip agent files
                if session_file.name.startswith("agent-"):
                    continue

                try:
                    mtime = session_file.stat().st_mtime
                    if mtime < cutoff:
                        continue

                    session = self._parse_session_file(session_file, project_dir.name)
                    if session:
                        sessions.append(session)
                except (OSError, PermissionError):
                    continue

        return sessions

    def _parse_session_file(
        self, filepath: Path, project_dir_name: str
    ) -> Optional[ClaudeSession]:
        """Parse session JSONL to extract metadata."""
        session_id = filepath.stem

        first_msg = None
        last_msg = None
        slug = None
        cwd = None

        try:
            with open(filepath, "r") as f:
                for line in f:
                    try:
                        msg = json.loads(line)
                        msg_type = msg.get("type")

                        if msg_type in ("user", "assistant"):
                            if first_msg is None:
                                first_msg = msg
                            last_msg = msg

                        if msg.get("slug"):
                            slug = msg["slug"]
                        if msg.get("cwd"):
                            cwd = msg["cwd"]
                    except json.JSONDecodeError:
                        continue
        except (OSError, PermissionError):
            return None

        if not first_msg:
            return None

        # Convert project dir name back to path
        # -Users-rock-projects-foo-bar -> /Users/rock/projects/foo-bar
        # The format is: dash-separated path segments where project name may contain dashes
        project_path = self._decode_project_path(project_dir_name)
        # Use cwd for the real project name (preserves dots, etc.)
        project_name = cwd.split("/")[-1] if cwd else (
            project_path.split("/")[-1] if "/" in project_path else project_dir_name
        )

        # Parse timestamps
        start_time = self._parse_timestamp(first_msg.get("timestamp"))
        last_activity = self._parse_timestamp(
            last_msg.get("timestamp") if last_msg else None
        )

        if start_time is None:
            start_time = datetime.now()
        if last_activity is None:
            last_activity = start_time

        duration = (last_activity - start_time).total_seconds()

        return ClaudeSession(
            session_id=session_id,
            project_path=project_path,
            project_name=project_name,
            session_file=str(filepath),
            status=SessionStatus.DONE,
            start_time=start_time,
            last_activity=last_activity,
            last_message_type=last_msg.get("type", "unknown") if last_msg else "unknown",
            slug=slug,
            cwd=cwd or project_path,
            duration_seconds=duration,
            progress_summary=self._extract_summary(last_msg) if last_msg else None,
        )

    def _decode_project_path(self, dir_name: str) -> str:
        """Convert encoded directory name back to path.

        e.g., -Users-rock-projects-app-foo-bar -> /Users/rock/projects/app-foo-bar
        """
        if not dir_name.startswith("-"):
            return dir_name

        # Remove leading dash
        dir_name = dir_name[1:]

        # Common path prefixes to look for
        # Try to find the 'projects' marker which indicates end of system path
        parts = dir_name.split("-")

        # Build path by finding known segments
        path_parts = []
        remaining_parts = []
        found_projects = False

        for i, part in enumerate(parts):
            if not found_projects:
                path_parts.append(part)
                if part == "projects":
                    found_projects = True
                    # Everything after 'projects' is the project name (may contain dashes)
                    remaining_parts = parts[i + 1:]
                    break

        if found_projects and remaining_parts:
            # Rejoin remaining parts with dashes (that's the project name)
            project_name = "-".join(remaining_parts)
            return "/" + "/".join(path_parts) + "/" + project_name
        else:
            # Fallback: just replace dashes with slashes
            return "/" + dir_name.replace("-", "/")

    def _parse_timestamp(self, ts) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        if ts is None:
            return None

        if isinstance(ts, (int, float)):
            # Unix timestamp in milliseconds
            return datetime.fromtimestamp(ts / 1000)
        elif isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                # Strip timezone to keep everything naive
                return dt.replace(tzinfo=None)
            except ValueError:
                return None
        return None

    def _extract_summary(self, msg: dict) -> Optional[str]:
        """Extract a brief summary from last message."""
        if not msg:
            return None

        content = msg.get("message", {}).get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")[:80]
                # Clean up and truncate
                text = text.replace("\n", " ").strip()
                if len(text) > 60:
                    text = text[:57] + "..."
                return text
        return None


class SessionManager:
    """Coordinates process and file scanning."""

    def __init__(self):
        self.process_scanner = ProcessScanner()
        self.file_scanner = SessionFileScanner()

    def get_sessions(self) -> list[ClaudeSession]:
        """Get all active sessions with current status."""
        running_processes = self.process_scanner.scan_claude_processes()
        sessions = self.file_scanner.get_active_sessions()

        for session in sessions:
            # Check if a Claude process is running for this project
            matched_pid = None
            for proc_path, pid in running_processes.items():
                if proc_path == session.cwd or proc_path == session.project_path:
                    matched_pid = pid
                    break

            if matched_pid:
                session.pid = matched_pid
                session.status = self._determine_activity_status(session)
                # Update duration to current time for running sessions
                if session.start_time:
                    session.duration_seconds = (
                        datetime.now() - session.start_time
                    ).total_seconds()
            else:
                session.status = SessionStatus.DONE

        # Sort by last activity, most recent first
        sessions.sort(key=lambda s: s.last_activity or datetime.min, reverse=True)

        # Deduplicate: one session per running process, one per project for completed
        return self._deduplicate_sessions(sessions)

    def _deduplicate_sessions(
        self, sessions: list[ClaudeSession]
    ) -> list[ClaudeSession]:
        """Keep only the most recent session per running process or project."""
        result = []
        seen_pids: set[int] = set()
        seen_done_projects: set[str] = set()

        for session in sessions:
            if session.pid is not None:
                # Running session - dedupe by PID
                if session.pid not in seen_pids:
                    seen_pids.add(session.pid)
                    result.append(session)
            else:
                # Completed session - dedupe by project
                if session.project_name not in seen_done_projects:
                    seen_done_projects.add(session.project_name)
                    result.append(session)

        return result

    def _determine_activity_status(self, session: ClaudeSession) -> SessionStatus:
        """Determine if running session is BUSY or IDLE."""
        now = time.time()

        # Check session file modification time (longer threshold for thinking)
        try:
            mtime = os.path.getmtime(session.session_file)
            if now - mtime < 30.0:
                return SessionStatus.BUSY
        except OSError:
            pass

        # Check debug log for this session - updates during API calls/thinking
        debug_log = Path.home() / ".claude" / "debug" / f"{session.session_id}.txt"
        try:
            if debug_log.exists():
                debug_mtime = debug_log.stat().st_mtime
                if now - debug_mtime < 30.0:
                    return SessionStatus.BUSY
        except OSError:
            pass

        # If last message was from user, Claude is processing
        if session.last_message_type == "user":
            return SessionStatus.BUSY

        return SessionStatus.IDLE
