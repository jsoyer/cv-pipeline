#!/usr/bin/env python3
"""CV TUI - Terminal User Interface for CV management."""

import os
import subprocess
import sys
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, ScrollableContainer
    from textual.widgets import Header, Footer, Button, Static, Input, Select
    from textual.binding import Binding
    from textual.screen import Screen
    from textual import work
except ImportError:
    print("textual required: pip install textual")
    sys.exit(1)

WORKDIR = os.environ.get("WORKDIR", str(Path(__file__).resolve().parent.parent))


PROVIDER_MODELS = {
    "gemini":  ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"],
    "claude":  ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    "openai":  ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o1-mini"],
    "mistral": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
}

ALL_MODELS: list[tuple[str, str]] = [("Default (provider default)", "")]
for _provider, _models in PROVIDER_MODELS.items():
    for _m in _models:
        ALL_MODELS.append((f"{_m}  [{_provider}]", _m))


def get_app_names() -> list[tuple[str, str]]:
    """List existing application directories as Select options, most recent first."""
    apps_dir = Path(WORKDIR) / "applications"
    if not apps_dir.exists():
        return []
    dirs = sorted([d.name for d in apps_dir.iterdir() if d.is_dir()], reverse=True)
    return [(name, name) for name in dirs]


# ---------------------------------------------------------------------------
# Input Screens
# ---------------------------------------------------------------------------


class NameScreen(Screen):
    """Screen that asks for a NAME= parameter."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, title: str, command: str, button_label: str = "Run",
                 variant: str = "success", extra: str = ""):
        super().__init__()
        self._title = title
        self._command = command
        self._button_label = button_label
        self._variant = variant
        self._extra = extra  # additional fixed flags appended to command

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static(self._title)
            options = get_app_names()
            if options:
                yield Select(options, id="name", prompt="Select application…")
            else:
                yield Input(placeholder="Application name (e.g. 2026-02-snowflake)", id="name")
            yield Button(self._button_label, id="btn-run", variant=self._variant)
        yield Footer()

    def _get_name(self) -> str:
        widget = self.query_one("#name")
        if isinstance(widget, Select):
            return "" if widget.value is Select.BLANK else str(widget.value)
        return widget.value.strip()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            name = self._get_name()
            if name:
                cmd = f"{self._command} NAME={name}"
                if self._extra:
                    cmd += f" {self._extra}"
                self.app.pop_screen()
                self.app.run_make(cmd)


class NewAppScreen(Screen):
    """Screen for scaffolding a new application."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("New Application")
            yield Input(placeholder="Company (e.g. Snowflake)", id="company")
            yield Input(placeholder="Position (e.g. Senior Director SE)", id="position")
            yield Button("Create", id="btn-create", variant="success")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            company = self.query_one("#company", Input).value.strip()
            position = self.query_one("#position", Input).value.strip()
            if company and position:
                self.app.pop_screen()
                self.app.run_make(f'new COMPANY="{company}" POSITION="{position}"')


class ApplyScreen(Screen):
    """Screen for the full apply workflow."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("Full Apply Workflow")
            yield Input(placeholder="Company", id="company")
            yield Input(placeholder="Position", id="position")
            yield Input(placeholder="Job URL (optional)", id="url")
            yield Button("Create Branch + PR", id="btn-apply", variant="success")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-apply":
            company = self.query_one("#company", Input).value.strip()
            position = self.query_one("#position", Input).value.strip()
            url = self.query_one("#url", Input).value.strip()
            if company and position:
                cmd = f'apply COMPANY="{company}" POSITION="{position}"'
                if url:
                    cmd += f' URL="{url}"'
                self.app.pop_screen()
                self.app.run_make(cmd)


class AINameScreen(Screen):
    """Generic screen for commands that accept NAME= + AI= + MODEL= parameters."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, title: str, command: str, extra: str = ""):
        super().__init__()
        self._title = title
        self._command = command
        self._extra = extra

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static(self._title)
            options = get_app_names()
            if options:
                yield Select(options, id="name", prompt="Select application…")
            else:
                yield Input(placeholder="Application name", id="name")
            yield Select(ALL_MODELS, id="model", prompt="Model (default)…")
            yield Button("Gemini (default)", id="btn-gemini", variant="success")
            yield Button("Claude",           id="btn-claude",  variant="primary")
            yield Button("OpenAI",           id="btn-openai")
            yield Button("Mistral",          id="btn-mistral")
            yield Button("Ollama (local)",   id="btn-ollama")
        yield Footer()

    def _get_name(self) -> str:
        widget = self.query_one("#name")
        if isinstance(widget, Select):
            return "" if widget.value is Select.BLANK else str(widget.value)
        return widget.value.strip()

    def _get_model(self) -> str:
        v = self.query_one("#model", Select).value
        return "" if v is Select.BLANK else str(v)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = self._get_name()
        if not name:
            return
        ai_map = {
            "btn-gemini": "gemini", "btn-claude": "claude",
            "btn-openai": "openai", "btn-mistral": "mistral", "btn-ollama": "ollama",
        }
        ai = ai_map.get(event.button.id)
        if ai:
            model = self._get_model()
            cmd = f"{self._command} NAME={name} AI={ai}"
            if model:
                cmd += f" MODEL={model}"
            if self._extra:
                cmd += f" {self._extra}"
            self.app.pop_screen()
            self.app.run_make(cmd)


class TailorScreen(Screen):
    """Screen for AI tailoring with provider selection."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("Tailor with AI")
            options = get_app_names()
            if options:
                yield Select(options, id="name", prompt="Select application…")
            else:
                yield Input(placeholder="Application name", id="name")
            yield Select(ALL_MODELS, id="model", prompt="Model (default)…")
            yield Button("Gemini (default)", id="btn-gemini", variant="success")
            yield Button("Claude", id="btn-claude", variant="primary")
            yield Button("OpenAI", id="btn-openai")
            yield Button("Mistral", id="btn-mistral")
            yield Button("Ollama (local)", id="btn-ollama")
        yield Footer()

    def _get_name(self) -> str:
        widget = self.query_one("#name")
        if isinstance(widget, Select):
            return "" if widget.value is Select.BLANK else str(widget.value)
        return widget.value.strip()

    def _get_model(self) -> str:
        widget = self.query_one("#model", Select)
        if widget.value is Select.BLANK:
            return ""
        return str(widget.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = self._get_name()
        if not name:
            return
        ai_map = {
            "btn-gemini": "gemini", "btn-claude": "claude",
            "btn-openai": "openai", "btn-mistral": "mistral", "btn-ollama": "ollama",
        }
        ai = ai_map.get(event.button.id)
        if ai:
            model = self._get_model()
            cmd = f"tailor NAME={name} AI={ai}"
            if model:
                cmd += f" MODEL={model}"
            self.app.pop_screen()
            self.app.run_make(cmd)


class CompareScreen(Screen):
    """Screen for comparing two applications."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("Compare Two Applications")
            options = get_app_names()
            if options:
                yield Select(options, id="name1", prompt="Select application 1…")
                yield Select(options, id="name2", prompt="Select application 2…")
            else:
                yield Input(placeholder="Application 1", id="name1")
                yield Input(placeholder="Application 2", id="name2")
            yield Button("Compare", id="btn-compare", variant="success")
        yield Footer()

    @staticmethod
    def _get_select(widget) -> str:
        if isinstance(widget, Select):
            return "" if widget.value is Select.BLANK else str(widget.value)
        return widget.value.strip()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-compare":
            name1 = self._get_select(self.query_one("#name1"))
            name2 = self._get_select(self.query_one("#name2"))
            if name1 and name2:
                self.app.pop_screen()
                self.app.run_make(f"compare NAME1={name1} NAME2={name2}")


class ExportScreen(Screen):
    """Screen for export format selection."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("Export CV")
            yield Button("JSON", id="btn-json", variant="primary")
            yield Button("Markdown", id="btn-md")
            yield Button("Text", id="btn-text")
            yield Button("JSON Resume (v1.0.0)", id="btn-jsonresume")
            yield Button("ATS Plain Text", id="btn-atstext")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-jsonresume":
            self.app.pop_screen()
            self.app.run_make("json-resume")
            return
        if event.button.id == "btn-atstext":
            self.app.pop_screen()
            self.app.run_make("ats-text")
            return
        fmt = {"btn-json": "json", "btn-md": "markdown", "btn-text": "text"}.get(
            event.button.id
        )
        if fmt:
            self.app.pop_screen()
            self.app.run_make(f"export FORMAT={fmt}")


class LinkedInScreen(Screen):
    """Screen for LinkedIn sync options."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("LinkedIn")
            yield Button("Sync (dry run)", id="btn-dry", variant="primary")
            yield Button("Push to LinkedIn", id="btn-push", variant="success")
            yield Button("Generate Message (recruiter)", id="btn-msg-recruiter")
            yield Button("Generate Message (hiring mgr)", id="btn-msg-hm")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-dry":
            self.app.pop_screen()
            self.app.run_make("linkedin")
        elif event.button.id == "btn-push":
            self.app.pop_screen()
            self.app.run_make("linkedin PUSH=true")
        elif event.button.id in ("btn-msg-recruiter", "btn-msg-hm"):
            msg_type = "recruiter" if event.button.id == "btn-msg-recruiter" else "hm"
            self.app.pop_screen()
            self.push_screen(NameScreen(
                f"LinkedIn Message ({msg_type})",
                f"linkedin-message",
                extra=f"TYPE={msg_type}"
            ))


class MatchScreen(Screen):
    """Screen for reverse ATS scoring."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("Reverse ATS Score")
            yield Input(placeholder="Job URL or file path", id="source")
            yield Button("Score", id="btn-score", variant="success")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-score":
            source = self.query_one("#source", Input).value.strip()
            if source:
                self.app.pop_screen()
                self.app.run_make(f'match SOURCE="{source}"')


class ArchiveScreen(Screen):
    """Screen for archiving an application with outcome."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("Archive Application")
            options = get_app_names()
            if options:
                yield Select(options, id="name", prompt="Select application…")
            else:
                yield Input(placeholder="Application name (e.g. 2026-02-snowflake)", id="name")
            yield Static("Outcome:")
            yield Button("✅ Offer",    id="btn-offer",    variant="success")
            yield Button("❌ Rejected", id="btn-rejected", variant="error")
            yield Button("👻 Ghosted",  id="btn-ghosted")
            yield Button("🗣️ Interview (ongoing)", id="btn-interview")
            yield Button("Archive (no outcome change)", id="btn-nooutcome")
        yield Footer()

    def _get_name(self) -> str:
        widget = self.query_one("#name")
        if isinstance(widget, Select):
            return "" if widget.value is Select.BLANK else str(widget.value)
        return widget.value.strip()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = self._get_name()
        if not name:
            return
        outcome_map = {
            "btn-offer":      "offer",
            "btn-rejected":   "rejected",
            "btn-ghosted":    "ghosted",
            "btn-interview":  "interview",
            "btn-nooutcome":  "",
        }
        if event.button.id in outcome_map:
            outcome = outcome_map[event.button.id]
            cmd = f"archive-app NAME={name}"
            if outcome:
                cmd += f" OUTCOME={outcome}"
            self.app.pop_screen()
            self.app.run_make(cmd)


class ReferencesScreen(Screen):
    """Screen for references management."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("References")
            yield Button("List All",    id="btn-list",    variant="primary")
            yield Button("Request Emails for Application", id="btn-request")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-list":
            self.app.pop_screen()
            self.app.run_make("references")
        elif event.button.id == "btn-request":
            self.app.pop_screen()
            self.push_screen(NameScreen("Reference Request Emails", "references ACTION=request"))


class CVVersionsScreen(Screen):
    """Screen for CV versions management."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("CV Versions")
            yield Button("List Versions",  id="btn-list",  variant="primary")
            yield Button("Save Current",   id="btn-save")
            yield Button("Activate",       id="btn-activate")
            yield Button("Diff",           id="btn-diff")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.app.pop_screen()
        if event.button.id == "btn-list":
            self.app.run_make("cv-versions")
        elif event.button.id == "btn-save":
            self.push_screen(_VersionNameScreen("save"))
        elif event.button.id == "btn-activate":
            self.push_screen(_VersionNameScreen("activate"))
        elif event.button.id == "btn-diff":
            self.push_screen(_VersionNameScreen("diff"))


class _VersionNameScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def __init__(self, action: str):
        super().__init__()
        self._action = action

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static(f"CV Versions — {self._action}")
            yield Input(placeholder="Version name (e.g. vp-se)", id="ver")
            yield Button("Run", id="btn-run", variant="success")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            ver = self.query_one("#ver", Input).value.strip()
            if ver:
                self.app.pop_screen()
                self.app.run_make(f"cv-versions ACTION={self._action} VERSION={ver}")


class PrepQuizScreen(Screen):
    """Screen for interview prep quiz."""

    BINDINGS = [Binding("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="form"):
            yield Static("Interview Prep Quiz")
            yield Input(placeholder="Application name (blank = all apps)", id="name")
            yield Button("All Categories",  id="btn-all",       variant="primary")
            yield Button("Behavioral Only", id="btn-behavioral")
            yield Button("Technical Only",  id="btn-technical")
            yield Button("Company Only",    id="btn-company")
            yield Button("Questions to Ask",id="btn-toask")
            yield Button("List Questions",  id="btn-list")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = self.query_one("#name", Input).value.strip()
        name_part = f" NAME={name}" if name else ""
        self.app.pop_screen()
        if event.button.id == "btn-all":
            self.app.run_make(f"prep-quiz{name_part}")
        elif event.button.id == "btn-list":
            self.app.run_make(f"prep-quiz{name_part} LIST=true")
        else:
            cat_map = {
                "btn-behavioral": "behavioral",
                "btn-technical":  "technical",
                "btn-company":    "company",
                "btn-toask":      "to-ask",
            }
            cat = cat_map.get(event.button.id, "all")
            self.app.run_make(f"prep-quiz{name_part} CAT={cat}")


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


class CVApp(App):
    CSS = """
    Screen { background: $surface; }
    #sidebar { width: 38; background: $panel; border-right: solid $border; padding: 1; overflow-y: scroll; }
    #main { padding: 1 2; }
    Button { width: 100%; margin: 0 0 1 0; }
    #output { border: solid $border; height: 100%; background: $surface-darken-1; padding: 1; }
    .section-title { color: $accent; text-style: bold; margin: 1 0 0 0; }
    #form { width: 60; padding: 2; }
    Input { margin: 1 0; }
    """

    TITLE = "CV Manager"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "build", "Build"),
        Binding("o", "open", "Open"),
        Binding("b", "board", "Board"),
        Binding("h", "help_make", "Help"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with ScrollableContainer(id="sidebar"):

                yield Static("Build", classes="section-title")
                yield Button("Build All",    id="btn-all",    variant="primary")
                yield Button("Build & Open", id="btn-open")
                yield Button("Render YAML",  id="btn-render")
                yield Button("French CV",    id="btn-render-fr")
                yield Button("Convert DOCX", id="btn-docx")

                yield Static("Workflow", classes="section-title")
                yield Button("New Application",   id="btn-new")
                yield Button("Full Apply",        id="btn-apply")
                yield Button("Fetch Job",         id="btn-fetch")
                yield Button("Tailor with AI",    id="btn-tailor")
                yield Button("Build App",         id="btn-app")
                yield Button("Review",            id="btn-review")
                yield Button("Archive (enhanced)",id="btn-archive-app")
                yield Button("Archive (simple)",  id="btn-archive")

                yield Static("Intelligence", classes="section-title")
                yield Button("Company Research",  id="btn-research")
                yield Button("Contacts",          id="btn-contacts")
                yield Button("Competitor Map",    id="btn-competitor-map")
                yield Button("Network Map",       id="btn-network-map")
                yield Button("URL Check",         id="btn-url-check")

                yield Static("Outreach", classes="section-title")
                yield Button("LinkedIn Profile",  id="btn-linkedin-profile")
                yield Button("LinkedIn Message",  id="btn-linkedin-msg")
                yield Button("Recruiter Email",   id="btn-recruiter-email")
                yield Button("References",        id="btn-references")

                yield Static("Interview Prep", classes="section-title")
                yield Button("Elevator Pitch",    id="btn-elevator-pitch")
                yield Button("Interview Sim",     id="btn-interview-sim")
                yield Button("Interview Brief",   id="btn-interview-brief")
                yield Button("STAR Stories",      id="btn-prep-star")
                yield Button("Interview Prep",    id="btn-prep")
                yield Button("Prep Quiz",         id="btn-prep-quiz")
                yield Button("Cover Angles",      id="btn-cover-angles")
                yield Button("Translate FR (AI)", id="btn-cv-fr-tailor")

                yield Static("Post-Interview", classes="section-title")
                yield Button("Interview Debrief", id="btn-interview-debrief")
                yield Button("Cover Critique",    id="btn-cover-critique")
                yield Button("Onboarding Plan",   id="btn-onboarding-plan")
                yield Button("LinkedIn Post",     id="btn-linkedin-post")
                yield Button("Thank-You Email",   id="btn-thankyou")
                yield Button("Negotiate",         id="btn-negotiate")
                yield Button("Salary Benchmark",  id="btn-salary-bench")
                yield Button("Log Milestone",     id="btn-milestone")

                yield Static("Analysis", classes="section-title")
                yield Button("CV Keywords",       id="btn-cv-keywords")
                yield Button("Blind Spots",       id="btn-blind-spots")
                yield Button("ATS Score",         id="btn-score")
                yield Button("ATS Ranking",       id="btn-ats-rank")
                yield Button("Reverse ATS",       id="btn-match")
                yield Button("Job Fit",           id="btn-job-fit")
                yield Button("CV Health",         id="btn-cv-health")
                yield Button("Skills Gap",        id="btn-skills")
                yield Button("CV Length",         id="btn-length")
                yield Button("Effectiveness",     id="btn-effectiveness")

                yield Static("Reporting", classes="section-title")
                yield Button("Apply Board",       id="btn-apply-board")
                yield Button("Status",            id="btn-status")
                yield Button("Stats",             id="btn-stats")
                yield Button("Report",            id="btn-report")
                yield Button("Digest",            id="btn-digest")
                yield Button("Changelog",         id="btn-changelog")
                yield Button("Timeline",          id="btn-timeline")
                yield Button("Question Bank",     id="btn-question-bank")
                yield Button("Deadline Alerts",   id="btn-deadline-alert")

                yield Static("Quality", classes="section-title")
                yield Button("Lint",              id="btn-lint")
                yield Button("Check All",         id="btn-check")
                yield Button("Diff",              id="btn-diff")
                yield Button("Compare",           id="btn-compare")
                yield Button("Visual Diff",       id="btn-visual-diff")

                yield Static("CV Management", classes="section-title")
                yield Button("CV Versions",       id="btn-cv-versions")

                yield Static("Export", classes="section-title")
                yield Button("Export",            id="btn-export")
                yield Button("Export CSV",        id="btn-export-csv")
                yield Button("LinkedIn Sync",     id="btn-linkedin")

                yield Static("System", classes="section-title")
                yield Button("Follow-up Email",   id="btn-followup")
                yield Button("Doctor",            id="btn-doctor")
                yield Button("Install Hooks",     id="btn-hooks")
                yield Button("Help",              id="btn-help")
                yield Button("Clean",             id="btn-clean")
                yield Button("Quit",              id="btn-quit", variant="error")

            with Vertical(id="main"):
                yield Static(
                    "Welcome to CV Manager\n\n"
                    "Use sidebar buttons or hotkeys:\n"
                    "  [r] Build  [o] Open  [b] Board  [h] Help  [q] Quit\n\n"
                    "Press ESC to go back from any input screen.\n\n"
                    "Sections: Build · Workflow · Intelligence · Outreach\n"
                    "          Interview Prep · Post-Interview · Analysis\n"
                    "          Reporting · Quality · CV Management · Export · System",
                    id="info",
                )
                with ScrollableContainer(id="output"):
                    yield Static("", id="output-text")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id

        # Simple commands (no parameters needed)
        simple = {
            "btn-all":          "",
            "btn-open":         "open",
            "btn-render":       "render",
            "btn-render-fr":    "render LANG=fr",
            "btn-status":       "status",
            "btn-stats":        "stats",
            "btn-skills":       "skills",
            "btn-length":       "length",
            "btn-effectiveness":"effectiveness",
            "btn-report":       "report",
            "btn-changelog":    "changelog",
            "btn-timeline":     "timeline",
            "btn-followup":     "followup",
            "btn-doctor":       "doctor",
            "btn-hooks":        "hooks",
            "btn-clean":        "clean",
            "btn-apply-board":  "apply-board",
            "btn-url-check":    "url-check",
            "btn-digest":       "digest",
            "btn-question-bank":"question-bank",
            "btn-deadline-alert":"deadline-alert --dry-run",
            "btn-network-map":  "network-map",
            "btn-ats-rank":     "ats-rank",
            "btn-export-csv":   "export-csv",
            "btn-linkedin-post":"linkedin-post",
            "btn-elevator-pitch":"elevator-pitch",
            "btn-cv-keywords":  "cv-keywords",
            "btn-help":         "help",
        }
        if btn in simple:
            target = simple[btn]
            self.run_make(target if target else None)
            return

        # Commands needing NAME= + AI= + MODEL= parameters
        ai_name_screens = {
            "btn-blind-spots":    ("Blind Spot Analysis",        "blind-spots"),
            "btn-cover-angles":   ("Cover Letter Angles (AI)",   "cover-angles"),
            "btn-cover-critique": ("Cover Letter Critique",      "cover-critique"),
            "btn-cv-fr-tailor":   ("Translate CV to French",     "cv-fr-tailor"),
            "btn-prep-star":      ("STAR Stories",               "prep-star"),
            "btn-interview-debrief": ("Interview Debrief",       "interview-debrief"),
            "btn-interview-sim":  ("Interview Simulator",        "interview-sim"),
            "btn-onboarding-plan":("Onboarding Plan",            "onboarding-plan"),
            "btn-salary-bench":   ("Salary Benchmark",           "salary-bench"),
            "btn-negotiate":      ("Negotiation Script",         "negotiate"),
            "btn-linkedin-profile":("LinkedIn Profile (AI)",     "linkedin-profile"),
            "btn-thankyou":       ("Thank-You Email",            "thankyou"),
            "btn-recruiter-email":("Recruiter Email (AI)",       "recruiter-email"),
            "btn-competitor-map": ("Competitor Map",             "competitor-map"),
        }
        if btn in ai_name_screens:
            title, cmd = ai_name_screens[btn]
            self.push_screen(AINameScreen(title, cmd))
            return

        # Commands needing NAME= parameter only
        name_screens = {
            "btn-fetch":         ("Fetch Job Description",      "fetch"),
            "btn-app":           ("Build Application",          "app"),
            "btn-review":        ("Full Review",                "review"),
            "btn-score":         ("ATS Score",                  "score"),
            "btn-prep":          ("Interview Prep",             "prep"),
            "btn-lint":          ("LaTeX Lint",                 "lint"),
            "btn-check":         ("Run All Validations",        "check"),
            "btn-diff":          ("Diff Master vs Tailored",    "diff"),
            "btn-visual-diff":   ("Visual Diff",                "visual-diff"),
            "btn-archive":       ("Archive Application (simple)","archive"),
            "btn-docx":          ("Convert to DOCX",            "docx"),
            "btn-research":      ("Company Research",           "research"),
            "btn-contacts":      ("Find Contacts",              "contacts"),
            "btn-job-fit":       ("Job Fit Score",              "job-fit"),
            "btn-cv-health":     ("CV Health Audit",            "cv-health"),
            "btn-milestone":     ("Log Interview Milestone",    "milestone"),
            "btn-linkedin-msg":  ("LinkedIn Message",           "linkedin-message"),
            "btn-interview-brief": ("Interview Brief",          "interview-brief"),
        }
        if btn in name_screens:
            title, cmd = name_screens[btn]
            self.push_screen(NameScreen(title, cmd))
            return

        # Special screens
        if btn == "btn-new":
            self.push_screen(NewAppScreen())
        elif btn == "btn-apply":
            self.push_screen(ApplyScreen())
        elif btn == "btn-tailor":
            self.push_screen(TailorScreen())
        elif btn == "btn-compare":
            self.push_screen(CompareScreen())
        elif btn == "btn-export":
            self.push_screen(ExportScreen())
        elif btn == "btn-linkedin":
            self.push_screen(LinkedInScreen())
        elif btn == "btn-match":
            self.push_screen(MatchScreen())
        elif btn == "btn-archive-app":
            self.push_screen(ArchiveScreen())
        elif btn == "btn-references":
            self.push_screen(ReferencesScreen())
        elif btn == "btn-cv-versions":
            self.push_screen(CVVersionsScreen())
        elif btn == "btn-prep-quiz":
            self.push_screen(PrepQuizScreen())
        elif btn == "btn-quit":
            self.exit()

    @work(exclusive=True, thread=True)
    def run_make(self, target: str | None = None) -> None:
        cmd = f"make -C {WORKDIR}" if target is None else f"make -C {WORKDIR} {target}"
        output = self.query_one("#output-text", Static)
        output.update(f"Running: {cmd}...\n")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=300
            )
            out = result.stdout + ("\n" + result.stderr if result.stderr else "")
            output.update(f"$ {cmd}\n\n{out}")
        except subprocess.TimeoutExpired:
            output.update(f"$ {cmd}\n\nTimeout after 300s")
        except Exception as e:
            output.update(f"Error: {e}")

    def action_quit(self) -> None:
        self.exit()

    def action_build(self) -> None:
        self.run_make()

    def action_open(self) -> None:
        self.run_make("open")

    def action_board(self) -> None:
        self.run_make("apply-board")

    def action_help_make(self) -> None:
        self.run_make("help")


if __name__ == "__main__":
    app = CVApp()
    app.run()
