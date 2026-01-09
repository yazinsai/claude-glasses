import subprocess
import sys
from enum import Enum

from claude_glasses.models import ClaudeSession, SessionStatus


class NotificationEvent(Enum):
    SESSION_COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"


class NotificationManager:
    """Handles notifications for session state changes."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._notified: set[tuple[str, NotificationEvent]] = set()

    def notify(self, session: ClaudeSession, event: NotificationEvent) -> None:
        """Send notification if enabled and not already notified."""
        key = (session.session_id, event)
        if not self.enabled or key in self._notified:
            return

        self._notified.add(key)

        title = self._get_title(event)
        name = session.slug or session.project_name
        message = f"{session.project_name}: {name}"

        self._send_notification(title, message)

    def test_notification(self) -> None:
        """Send a test notification."""
        self._send_notification("Claude Glasses", "Notifications are working!")

    def _send_notification(self, title: str, message: str) -> None:
        """Send macOS notification with sound."""
        try:
            # Try terminal-notifier first (more reliable)
            subprocess.run(
                [
                    "terminal-notifier",
                    "-title", title,
                    "-message", message,
                    "-sound", "Glass",
                ],
                capture_output=True,
                timeout=5,
            )
        except FileNotFoundError:
            # Fallback to osascript
            title = title.replace('"', '\\"')
            message = message.replace('"', '\\"')
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            try:
                subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            except Exception:
                pass
        except Exception:
            pass

    def _get_title(self, event: NotificationEvent) -> str:
        titles = {
            NotificationEvent.SESSION_COMPLETED: "Claude Session Complete",
            NotificationEvent.NEEDS_INPUT: "Claude Needs Input",
        }
        return titles.get(event, "Claude Code")

    def clear_for_session(self, session_id: str) -> None:
        """Clear notification state for a session."""
        self._notified = {
            (sid, evt) for sid, evt in self._notified if sid != session_id
        }

    def toggle(self) -> bool:
        """Toggle notifications on/off. Returns new state."""
        self.enabled = not self.enabled
        return self.enabled


class SessionStateTracker:
    """Tracks session state changes and triggers notifications."""

    def __init__(self, notification_manager: NotificationManager):
        self.previous_states: dict[str, SessionStatus] = {}
        self.notification_manager = notification_manager
        # Sessions that went BUSY -> IDLE and need attention
        self.needs_attention: set[str] = set()

    def update(self, sessions: list[ClaudeSession]) -> None:
        """Detect state transitions and trigger notifications."""
        current_ids = {s.session_id for s in sessions}

        for session in sessions:
            prev_status = self.previous_states.get(session.session_id)

            if prev_status is not None and prev_status != session.status:
                # State changed
                if prev_status == SessionStatus.BUSY:
                    if session.status == SessionStatus.DONE:
                        self.notification_manager.notify(
                            session, NotificationEvent.SESSION_COMPLETED
                        )
                        self.needs_attention.discard(session.session_id)
                    elif session.status == SessionStatus.IDLE:
                        self.notification_manager.notify(
                            session, NotificationEvent.NEEDS_INPUT
                        )
                        # Mark as needing attention
                        self.needs_attention.add(session.session_id)
                elif prev_status == SessionStatus.IDLE and session.status == SessionStatus.BUSY:
                    # User started interacting again, clear attention flag
                    self.needs_attention.discard(session.session_id)

            self.previous_states[session.session_id] = session.status

        # Clean up old sessions
        for session_id in list(self.previous_states.keys()):
            if session_id not in current_ids:
                del self.previous_states[session_id]
                self.notification_manager.clear_for_session(session_id)
                self.needs_attention.discard(session_id)

    def session_needs_attention(self, session_id: str) -> bool:
        """Check if a session needs user attention."""
        return session_id in self.needs_attention

    def clear_attention(self, session_id: str) -> None:
        """Clear attention flag for a session."""
        self.needs_attention.discard(session_id)
