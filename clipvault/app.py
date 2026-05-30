"""Terminal UI for ClipVault."""

from __future__ import annotations

import argparse
import curses
import fcntl
import os
from queue import Empty, Queue
import signal
import textwrap
from threading import Event, Thread
import time
from pathlib import Path

from .clipboard_backends import ClipboardBackend, ClipboardError
from .history import ClipboardHistory, ClipboardItem, default_history_path

POLL_SECONDS = 0.8
INPUT_TIMEOUT_MS = 25
MAX_KEYS_PER_FRAME = 64
HELP_TEXT = "q quit | ↑/k ↓/j move | enter/c copy | p pin | d delete | x clear | / search | space pause | r read now | ? help"
COW_LOGO_LINES = (
    r"    (__)",
    r"    (oo)",
    r" /---\/",
    r"/| CV||",
    r"*|---||",
    r" ^^  ^^",
)
COW_LOGO = "\n".join(COW_LOGO_LINES)
HEADER_HEIGHT = len(COW_LOGO_LINES) + 1
BRAND = "CK42X // CLIPVAULT"
TAGLINE = "clipboard recovery console // moo-ving clips back into reach"

COLOR_HEADER = 1
COLOR_ACCENT = 2
COLOR_MUTED = 3
COLOR_SELECTED = 4
COLOR_ALERT = 5
COLOR_PIN = 6
COLOR_PANEL = 7


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipvault",
        description="A CK42X-style terminal clipboard-history applet with persistent local history.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=default_history_path(),
        help="Path to the JSON history file. Default: %(default)s",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=100,
        help="Maximum history items to keep. Default: %(default)s",
    )
    parser.add_argument(
        "--print-path",
        action="store_true",
        help="Print the history file path and exit.",
    )
    parser.add_argument(
        "--snapshot-ui",
        action="store_true",
        help="Print a static CK42X-style UI preview and exit.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run headless clipboard capture for startup/background use.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="In daemon mode, read the clipboard once and exit.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=POLL_SECONDS,
        help="Daemon polling interval in seconds. Default: %(default)s",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_path:
        print(args.history)
        return 0
    if args.snapshot_ui:
        print(render_snapshot_ui(width=96))
        return 0
    if args.daemon:
        return run_daemon(args)
    curses.wrapper(lambda stdscr: ClipVaultApp(stdscr, args).run())
    return 0


def daemon_main(argv: list[str] | None = None) -> int:
    """Console entrypoint for the installed clipvaultd command."""

    parser = build_parser()
    args = parser.parse_args(argv)
    args.daemon = True
    return run_daemon(args)


def run_daemon(args: argparse.Namespace) -> int:
    """Run headless clipboard capture for login/startup use."""

    history = ClipboardHistory.load(path=args.history, max_items=args.max_items)
    lock_path = history.path.parent / "daemon.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"clipvault daemon: already running lock={lock_path}", flush=True)
        lock_file.close()
        return 0
    lock_file.write(f"pid={os.getpid()}\n")
    lock_file.flush()

    try:
        backend = ClipboardBackend()
    except ClipboardError as exc:
        print(f"clipvault daemon: {exc}", flush=True)
        lock_file.close()
        return 2

    stop = Event()

    def request_stop(signum, frame):  # noqa: ARG001 - signal handler signature
        stop.set()

    old_sigint = signal.signal(signal.SIGINT, request_stop)
    old_sigterm = signal.signal(signal.SIGTERM, request_stop)
    last_seen: str | None = None
    print(f"clipvault daemon: started backend={backend.name} history={history.path}", flush=True)
    try:
        while not stop.is_set():
            try:
                text = backend.read_text()
            except ClipboardError as exc:
                print(f"clipvault daemon: clipboard read failed: {exc}", flush=True)
            else:
                if text != last_seen:
                    last_seen = text
                    item = history.add(text)
                    if item:
                        history.save()
                        print(f"clipvault daemon: saved item count={len(history.items)}", flush=True)
            if args.once:
                break
            stop.wait(max(0.1, args.interval))
    finally:
        history.save()
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)
        lock_file.close()
        print("clipvault daemon: stopped", flush=True)
    return 0


class ClipboardPoller:
    """Poll the system clipboard without blocking the curses input loop."""

    def __init__(self, backend: ClipboardBackend, interval: float = POLL_SECONDS):
        self.backend = backend
        self.interval = interval
        self.events: Queue[tuple[str, str]] = Queue()
        self._stop = Event()
        self._paused = Event()
        self._thread: Thread | None = None
        self._last_seen: str | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = Thread(target=self._run, name="clipvault-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.3)

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._paused.set()
        else:
            self._paused.clear()

    def remember(self, text: str) -> None:
        self._last_seen = text

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self._paused.is_set():
                self._read_once()
            self._stop.wait(self.interval)

    def _read_once(self) -> None:
        try:
            text = self.backend.read_text()
        except ClipboardError as exc:
            message = str(exc)
            if message != self._last_error:
                self.events.put(("error", message))
                self._last_error = message
            return
        self._last_error = None
        if text != self._last_seen:
            self._last_seen = text
            self.events.put(("clipboard", text))


class ClipVaultApp:
    def __init__(self, stdscr, args: argparse.Namespace):
        self.stdscr = stdscr
        self.history = ClipboardHistory.load(path=args.history, max_items=args.max_items)
        self.backend: ClipboardBackend | None = None
        self.status = "Starting ClipVault"
        self.selected = 0
        self.search_query = ""
        self.searching = False
        self.paused = False
        self.show_help = False
        self.last_seen: str | None = None
        self.poller: ClipboardPoller | None = None
        try:
            self.backend = ClipboardBackend()
            self.poller = ClipboardPoller(self.backend)
            self.status = f"Clipboard backend: {self.backend.name}"
        except ClipboardError as exc:
            self.status = str(exc)

    def run(self) -> None:
        curses.curs_set(0)
        try:
            curses.set_escdelay(25)
        except curses.error:
            pass
        self._init_colors()
        self.stdscr.keypad(True)
        self.stdscr.timeout(INPUT_TIMEOUT_MS)
        if self.poller:
            self.poller.start()

        try:
            while True:
                self._drain_clipboard_events()
                self._draw()
                first_key = self.stdscr.getch()
                if first_key == -1:
                    continue
                for key in collect_pending_keys(self.stdscr, first_key):
                    if self._handle_key(key):
                        return
        finally:
            if self.poller:
                self.poller.stop()
            self.history.save()

    def _init_colors(self) -> None:
        if not curses.has_colors():
            return
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        color_pairs = [
            (COLOR_HEADER, curses.COLOR_BLACK, curses.COLOR_CYAN),
            (COLOR_ACCENT, curses.COLOR_CYAN, -1),
            (COLOR_MUTED, curses.COLOR_BLUE, -1),
            (COLOR_SELECTED, curses.COLOR_BLACK, curses.COLOR_YELLOW),
            (COLOR_ALERT, curses.COLOR_YELLOW, -1),
            (COLOR_PIN, curses.COLOR_YELLOW, -1),
            (COLOR_PANEL, curses.COLOR_WHITE, -1),
        ]
        for pair, fg, bg in color_pairs:
            try:
                curses.init_pair(pair, fg, bg)
            except curses.error:
                pass

    def _color(self, pair: int, fallback: int = 0) -> int:
        if curses.has_colors():
            return curses.color_pair(pair)
        return fallback

    def _drain_clipboard_events(self) -> None:
        if self.poller is None:
            return
        while True:
            try:
                kind, payload = self.poller.events.get_nowait()
            except Empty:
                return
            if kind == "error":
                self.status = payload
            elif kind == "clipboard":
                self._accept_clipboard_text(payload)

    def _accept_clipboard_text(self, text: str) -> None:
        self.last_seen = text
        item = self.history.add(text)
        if item:
            self.history.save()
            self.selected = 0
            self.status = "Saved clipboard item"

    def _read_clipboard(self, force: bool) -> None:
        if self.backend is None:
            return
        try:
            text = self.backend.read_text()
        except ClipboardError as exc:
            self.status = str(exc)
            return
        if not force and text == self.last_seen:
            return
        if self.poller:
            self.poller.remember(text)
        self._accept_clipboard_text(text)

    def _handle_key(self, key: int) -> bool:
        if self.searching:
            self._handle_search_key(key)
            return False

        if key in (ord("q"), ord("Q")):
            self.history.save()
            return True
        if key in (curses.KEY_DOWN, ord("j"), ord("J")):
            self._move(1)
        elif key in (curses.KEY_UP, ord("k"), ord("K")):
            self._move(-1)
        elif key in (curses.KEY_ENTER, 10, 13, ord("c"), ord("C")):
            self._copy_selected()
        elif key in (ord("p"), ord("P")):
            self._toggle_pin()
        elif key in (ord("d"), ord("D")):
            self._delete_selected()
        elif key in (ord("x"), ord("X")):
            self.history.clear(include_pinned=False)
            self.history.save()
            self.selected = 0
            self.status = "Cleared unpinned items"
        elif key == ord("/"):
            self.searching = True
            curses.curs_set(1)
        elif key == ord(" "):
            self.paused = not self.paused
            if self.poller:
                self.poller.set_paused(self.paused)
            self.status = "Monitoring paused" if self.paused else "Monitoring resumed"
        elif key in (ord("r"), ord("R")):
            self._read_clipboard(force=True)
        elif key == ord("?"):
            self.show_help = not self.show_help
        elif key == 27:
            self.search_query = ""
            self.selected = 0
        return False

    def _handle_search_key(self, key: int) -> None:
        if key in (curses.KEY_ENTER, 10, 13):
            self.searching = False
            curses.curs_set(0)
        elif key == 27:
            self.searching = False
            self.search_query = ""
            self.selected = 0
            curses.curs_set(0)
        elif key in (curses.KEY_BACKSPACE, 8, 127):
            self.search_query = self.search_query[:-1]
            self.selected = 0
        elif 32 <= key <= 126:
            self.search_query += chr(key)
            self.selected = 0

    def _visible_items(self) -> list[ClipboardItem]:
        return self.history.search(self.search_query)

    def _move(self, delta: int) -> None:
        visible = self._visible_items()
        if not visible:
            self.selected = 0
            return
        self.selected = max(0, min(len(visible) - 1, self.selected + delta))

    def _selected_item(self) -> ClipboardItem | None:
        visible = self._visible_items()
        if not visible:
            return None
        self.selected = max(0, min(len(visible) - 1, self.selected))
        return visible[self.selected]

    def _copy_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            self.status = "No item selected"
            return
        if self.backend is None:
            self.status = "No clipboard backend available"
            return
        try:
            self.backend.write_text(item.text)
        except ClipboardError as exc:
            self.status = str(exc)
            return
        self.last_seen = item.text
        if self.poller:
            self.poller.remember(item.text)
        self.status = "Copied selected item back to clipboard"

    def _toggle_pin(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        self.history.pin(item.id, not item.pinned)
        self.history.save()
        self.status = "Pinned item" if item.pinned else "Unpinned item"

    def _delete_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        self.history.delete(item.id)
        self.history.save()
        self.selected = max(0, self.selected - 1)
        self.status = "Deleted item"

    def _draw(self) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        if height < 15 or width < 62:
            self._addstr(0, 0, "Make the terminal at least 62x15 for the CK42X console UI.", curses.A_BOLD)
            self.stdscr.refresh()
            return

        state = "PAUSED" if self.paused else "LIVE"
        state_attr = self._color(COLOR_ALERT if self.paused else COLOR_HEADER, curses.A_REVERSE)
        self._draw_header(width, state, state_attr)

        footer_y = height - 2
        body_top = HEADER_HEIGHT
        body_bottom = footer_y - 1
        body_height = max(3, body_bottom - body_top + 1)
        side_width = 28 if width >= 92 else 0
        gap = 2 if side_width else 0
        list_width = width - side_width - gap

        self._draw_history_panel(body_top, 0, body_height, list_width)
        if side_width:
            self._draw_side_panel(body_top, list_width + gap, body_height, side_width)

        self._addstr(footer_y, 0, f" STATUS  {self.status}"[: width - 1], self._color(COLOR_MUTED, curses.A_DIM))
        self._addstr(height - 1, 0, HELP_TEXT[: width - 1], self._color(COLOR_HEADER, curses.A_REVERSE))
        self.stdscr.refresh()

    def _draw_header(self, width: int, state: str, state_attr: int) -> None:
        logo_width = max(len(line) for line in COW_LOGO_LINES)
        text_x = logo_width + 6
        self._addstr(0, 0, " " * (width - 1), self._color(COLOR_HEADER, curses.A_REVERSE))
        self._addstr(0, max(0, width - len(state) - 4), f" {state} ", state_attr | curses.A_BOLD)
        for row, logo_line in enumerate(COW_LOGO_LINES):
            self._addstr(row, 2, logo_line, self._color(COLOR_ACCENT, curses.A_BOLD))
        self._addstr(0, text_x, BRAND[: max(0, width - text_x - 8)], self._color(COLOR_HEADER, curses.A_REVERSE | curses.A_BOLD))
        self._addstr(1, text_x, TAGLINE[: max(0, width - text_x - 2)], self._color(COLOR_ACCENT, curses.A_BOLD))
        search_prompt = "/" + self.search_query if self.searching or self.search_query else "press / to filter"
        search_attr = self._color(COLOR_ALERT if self.searching else COLOR_MUTED, curses.A_BOLD if self.searching else curses.A_DIM)
        self._addstr(3, text_x, f"FILTER  {search_prompt}"[: max(0, width - text_x - 2)], search_attr)
        self._addstr(HEADER_HEIGHT - 1, 0, "─" * (width - 1), self._color(COLOR_MUTED, curses.A_DIM))

    def _draw_history_panel(self, y: int, x: int, height: int, width: int) -> None:
        self._draw_box(y, x, height, width, "HISTORY BUFFER")
        visible = self._visible_items()
        content_y = y + 2
        max_rows = max(0, height - 3)
        inner_width = max(8, width - 4)

        if not visible:
            self._addstr(content_y, x + 2, "No captured clipboard items yet."[:inner_width], self._color(COLOR_MUTED, curses.A_DIM))
            self._addstr(content_y + 1, x + 2, "Copy text, or press r to read now."[:inner_width], self._color(COLOR_MUTED, curses.A_DIM))
            return

        self.selected = max(0, min(len(visible) - 1, self.selected))
        start = max(0, self.selected - max_rows + 1)
        for row_offset, item in enumerate(visible[start : start + max_rows]):
            row = content_y + row_offset
            actual_index = start + row_offset
            marker = "▶" if actual_index == self.selected else " "
            pin = "★" if item.pinned else " "
            preview = make_preview(item.text, inner_width - 11)
            line = f"{marker} {pin} {actual_index + 1:03d} │ {preview}"
            if actual_index == self.selected:
                attr = self._color(COLOR_SELECTED, curses.A_REVERSE | curses.A_BOLD)
            elif item.pinned:
                attr = self._color(COLOR_PIN, curses.A_BOLD)
            else:
                attr = self._color(COLOR_PANEL)
            self._addstr(row, x + 2, line.ljust(inner_width)[:inner_width], attr)

    def _draw_side_panel(self, y: int, x: int, height: int, width: int) -> None:
        self._draw_box(y, x, height, width, "OPS")
        visible_count = len(self._visible_items())
        pinned_count = sum(1 for item in self.history.items if item.pinned)
        backend = self.backend.name if self.backend else "unavailable"
        lines = [
            ("items", str(len(self.history.items))),
            ("visible", str(visible_count)),
            ("pinned", str(pinned_count)),
            ("backend", backend),
            ("mode", "paused" if self.paused else "monitoring"),
            ("filter", self.search_query or "none"),
        ]
        row = y + 2
        for label, value in lines:
            self._addstr(row, x + 2, f"{label:<8} {value}"[: width - 4], self._color(COLOR_PANEL))
            row += 1

        selected = self._selected_item()
        row += 1
        self._addstr(row, x + 2, "SELECTED"[: width - 4], self._color(COLOR_ACCENT, curses.A_BOLD))
        row += 1
        if selected is None:
            self._addstr(row, x + 2, "none"[: width - 4], self._color(COLOR_MUTED, curses.A_DIM))
        else:
            for line in textwrap.wrap(make_preview(selected.text, 120), width=max(12, width - 4))[: max(1, height - row + y - 2)]:
                self._addstr(row, x + 2, line[: width - 4], self._color(COLOR_PANEL))
                row += 1

        if self.show_help and row < y + height - 2:
            row += 1
            self._addstr(row, x + 2, "COMMANDS"[: width - 4], self._color(COLOR_ACCENT, curses.A_BOLD))
            for command in ["enter copy", "p pin", "d delete", "x clear", "/ filter"]:
                row += 1
                if row >= y + height - 1:
                    break
                self._addstr(row, x + 2, command[: width - 4], self._color(COLOR_MUTED, curses.A_DIM))

    def _draw_box(self, y: int, x: int, height: int, width: int, title: str) -> None:
        if height < 2 or width < 4:
            return
        attr = self._color(COLOR_MUTED, curses.A_DIM)
        top = "┌" + "─" * (width - 2) + "┐"
        bottom = "└" + "─" * (width - 2) + "┘"
        self._addstr(y, x, top, attr)
        self._addstr(y + height - 1, x, bottom, attr)
        for row in range(y + 1, y + height - 1):
            self._addstr(row, x, "│", attr)
            self._addstr(row, x + width - 1, "│", attr)
        label = f" {title} "
        self._addstr(y, x + 2, label[: max(0, width - 4)], self._color(COLOR_ACCENT, curses.A_BOLD))

    def _addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass


def collect_pending_keys(stdscr, first_key: int, max_keys: int = MAX_KEYS_PER_FRAME) -> list[int]:
    """Collect a burst of queued keypresses so fast arrow repeats are not dropped."""

    keys = [first_key]
    if hasattr(stdscr, "nodelay"):
        stdscr.nodelay(True)
    try:
        while len(keys) < max_keys:
            key = stdscr.getch()
            if key == -1:
                break
            keys.append(key)
    finally:
        if hasattr(stdscr, "timeout"):
            stdscr.timeout(INPUT_TIMEOUT_MS)
    return keys


def make_preview(text: str, width: int) -> str:
    single_line = " ".join(text.replace("\x00", "").split())
    if len(single_line) <= width:
        return single_line
    return single_line[: max(0, width - 1)] + "…"


def render_snapshot_header(width: int, state: str) -> list[str]:
    """Render the multi-line cow header for non-interactive verification."""

    logo_width = max(len(line) for line in COW_LOGO_LINES)
    text_x = logo_width + 6
    rows = ["" for _ in range(HEADER_HEIGHT)]
    for row, logo_line in enumerate(COW_LOGO_LINES):
        rows[row] = f"  {logo_line}"
    rows[0] = rows[0].ljust(text_x) + BRAND
    rows[0] = rows[0].ljust(max(0, width - len(state) - 2)) + f" {state} "
    rows[1] = rows[1].ljust(text_x) + TAGLINE
    rows[3] = rows[3].ljust(text_x) + "FILTER  press / to filter"
    rows[HEADER_HEIGHT - 1] = "─" * width
    return [row[:width] for row in rows]


def render_snapshot_ui(width: int = 96) -> str:
    """Return a static terminal preview for non-interactive verification."""

    width = max(72, width)
    history_width = width - 31
    samples = [
        ("▶", "★", "001", "release notes: polish clipboard history UI"),
        (" ", " ", "002", "python3 -m clipvault --history ./history.json"),
        (" ", " ", "003", "support reply: thanks, I will test this today"),
    ]
    lines = render_snapshot_header(width, state="LIVE") + [
        "┌" + "─" * (history_width - 2) + "┐  ┌" + "─" * 25 + "┐",
        "│ HISTORY BUFFER".ljust(history_width - 1) + "│  │ OPS".ljust(28) + "│",
    ]
    for index, (marker, pin, number, text) in enumerate(samples):
        right = ["items    42", "visible  42", "pinned   3"][index]
        left = f"│  {marker} {pin} {number} │ {make_preview(text, history_width - 13)}".ljust(history_width - 1) + "│"
        lines.append(left + f"  │  {right}".ljust(28) + "│")
    lines.extend(
        [
            "│" + " " * (history_width - 2) + "│  │  backend windows-wsl".ljust(28) + "│",
            "└" + "─" * (history_width - 2) + "┘  └" + "─" * 25 + "┘",
            " STATUS  Copied selected item back to clipboard",
            HELP_TEXT[:width],
        ]
    )
    return "\n".join(line[:width] for line in lines)
