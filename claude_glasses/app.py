from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Static
from rich.text import Text
from rich.console import RenderableType

from claude_glasses.models import SessionStatus
from claude_glasses.notifications import NotificationManager, SessionStateTracker
from claude_glasses.session_manager import SessionManager


SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class SessionList(Static):
    """Compact animated session list."""

    frame = reactive(0)

    def __init__(self, session_manager: SessionManager, state_tracker: SessionStateTracker, notif_manager: NotificationManager):
        super().__init__()
        self.session_manager = session_manager
        self.state_tracker = state_tracker
        self.notif_manager = notif_manager
        self.sessions = []

    def on_mount(self) -> None:
        self.set_interval(0.1, self._tick)
        self.set_interval(2.0, self._refresh)
        self._refresh()

    def _tick(self) -> None:
        self.frame = (self.frame + 1) % 20

    def _refresh(self) -> None:
        all_sessions = self.session_manager.get_sessions()
        # Exclude completed sessions
        self.sessions = [s for s in all_sessions if s.status != SessionStatus.DONE]
        self.state_tracker.update(self.sessions)

    def render(self) -> RenderableType:
        lines = []

        # Header
        notif = "[green]●[/]" if self.notif_manager.enabled else "[red]○[/]"
        lines.append(f"[bold]claude-glasses[/] [dim]│[/] {len(self.sessions)} sessions  {notif}")
        lines.append("")

        # Sessions
        for s in self.sessions:
            attn = self.state_tracker.session_needs_attention(s.session_id)
            line = self._format_session(s, attn)
            lines.append(line)

        if not self.sessions:
            lines.append("[dim]  no active sessions[/]")

        # Footer
        lines.append("")
        lines.append("[dim]q[/] quit  [dim]n[/] notify  [dim]r[/] refresh  [dim]t[/] test")

        return Text.from_markup("\n".join(lines))

    def _format_session(self, s, needs_attention: bool) -> str:
        name = s.project_name[:18].ljust(18)
        time = s.format_duration().rjust(8)
        status = self._first_sentence(s.progress_summary, 30)

        if s.status == SessionStatus.BUSY:
            icon = f"[green]{SPINNER[self.frame // 2]}[/]"
            return f"  {icon} [bold]{name}[/] [dim]{time}[/]  [dim]{status}[/]"
        elif s.status == SessionStatus.IDLE:
            if needs_attention:
                dot = "●" if self.frame % 10 < 5 else "○"
                return f"  [bold magenta]{dot} {name} {time}  ← ready[/]"
            return f"  [yellow]○[/] {name} [dim]{time}[/]  [dim]{status}[/]"
        else:
            return f"  [dim]✓ {name} {time}[/]"

    def _first_sentence(self, text: str | None, max_len: int) -> str:
        if not text:
            return ""
        # Get first sentence
        sentence = text.split('.')[0].strip()
        if len(sentence) > max_len:
            return sentence[:max_len-1] + "…"
        return sentence


class ClaudeGlassesApp(App):
    CSS = """
    Screen { background: #0d1117; }
    SessionList { margin: 1 2; }
    """

    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("n", "toggle_notif", show=False),
        Binding("r", "refresh", show=False),
        Binding("t", "test_notif", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.session_manager = SessionManager()
        self.notif_manager = NotificationManager()
        self.state_tracker = SessionStateTracker(self.notif_manager)

    def compose(self) -> ComposeResult:
        yield SessionList(self.session_manager, self.state_tracker, self.notif_manager)

    def action_toggle_notif(self) -> None:
        self.notif_manager.toggle()
        self.query_one(SessionList).refresh()

    def action_refresh(self) -> None:
        self.query_one(SessionList)._refresh()

    def action_test_notif(self) -> None:
        self.notif_manager.test_notification()


def main():
    app = ClaudeGlassesApp()
    app.run()
