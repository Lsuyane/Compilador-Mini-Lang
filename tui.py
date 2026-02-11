#!/usr/bin/env python3
"""
Rich 2x2 live UI with keyboard-controlled per-pane scrolling.
Demo generator now stops after MAX_GEN lines so you can test interactively.
"""
from typing import Callable, Optional, List
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.syntax import Syntax
from rich.text import Text
import io
import threading
import time
import sys
import os
import termios
import tty
import select


class Tui:

    class Mode:
        LEXER = 1
        PARSER = 2
        CODE_GEN = 3

    def __init__(self, mode=Mode.CODE_GEN, theme="monokai"):
        self.console = Console()
        self.mode = mode
        self.theme = theme

        # region Buffers
        self.source_buf = io.StringIO()
        self.tokens_buf = io.StringIO()
        self.ir_buf = io.StringIO()
        self.code_buf = io.StringIO()
        self.log_buf = io.StringIO()
        # endregion

        # region State
        # 0: source, 1: tokens, 2: ir, 3: code, 4: log
        self.selected_pane = 0
        self.scroll_offsets = [0] * 5  # number of lines scrolled up (0 = bottom)
        self.lock = threading.Lock()
        self.running = True
        self.need_refresh = True
        self.last_console_size = self.console.size
        # endregion

        # region Widgets (single creation to avoid flicker)
        self.syntax_widget = Syntax(
            "", "c", line_numbers=True, theme="monokai", word_wrap=False
        )
        self.source_panel = Panel(
            self.syntax_widget, title="Source", border_style="cyan"
        )
        self.tokens_panel = Panel("", title="Tokens", border_style="green")
        self.ir_panel = Panel("", title="IR", border_style="yellow")
        self.code_panel = Panel("", title="Codegen", border_style="magenta")
        self.log_panel = Panel("", title="Debug Output", border_style="indian_red")
        # endregion

        # Build initial layout
        self.layout = self.build_layout()

    def build_layout(self):
        """Build or rebuild layout based on current console size"""
        layout = Layout()
        console_height = self.console.size.height

        # Calculate log panel height (25% of console height, minimum 4 lines)
        log_height = max(4, int(console_height * 0.25))

        # Split main area and log panel
        layout.split(
            Layout(name="main", ratio=(console_height - log_height)),
            Layout(name="log", size=log_height),
        )

        # Now split the main area based on mode
        if self.mode == Tui.Mode.LEXER:
            layout["main"].split_row(
                Layout(name="source", ratio=1),
                Layout(name="tokens", ratio=1),
            )
        elif self.mode == Tui.Mode.PARSER:
            layout["main"].split_row(
                Layout(name="source", ratio=1),
                Layout(name="tokens", ratio=1),
                Layout(name="ir", ratio=1),
            )
        else:  # CODE_GEN
            # For code gen, split main area vertically first
            layout["main"].split(
                Layout(name="upper"),
                Layout(name="lower"),
            )
            layout["main"]["upper"].split_row(
                Layout(name="source", ratio=1),
                Layout(name="tokens", ratio=1),
            )
            layout["main"]["lower"].split_row(
                Layout(name="ir", ratio=1),
                Layout(name="code", ratio=1),
            )

        # Assign panels
        layout["source"].update(self.source_panel)
        layout["tokens"].update(self.tokens_panel)

        if self.mode >= Tui.Mode.PARSER:
            layout["ir"].update(self.ir_panel)

        if self.mode >= Tui.Mode.CODE_GEN:
            layout["code"].update(self.code_panel)

        layout["log"].update(self.log_panel)

        return layout

    # region Helpers
    @staticmethod
    def lines_of(text: str) -> list[str]:
        if not text:
            return []
        return text.rstrip("\n").split("\n")
    
    @staticmethod
    def process_carriage_returns(text: str) -> List[str]:
        """Process text with carriage returns by overwriting previous content."""
        if not text:
            return []
        
        lines = []
        current_line = ""
        
        i = 0
        while i < len(text):
            if text[i] == '\r':
                # Carriage return - move to beginning of line
                # Check if next character is newline
                if i + 1 < len(text) and text[i + 1] == '\n':
                    # \r\n sequence - treat as newline
                    lines.append(current_line)
                    current_line = ""
                    i += 2
                    continue
                else:
                    # Just \r - start new line, overwriting current
                    # Actually, for TUI we want to clear the current line
                    # and start accumulating from beginning
                    current_line = ""
                    i += 1
            elif text[i] == '\n':
                # Newline - save current line and start new one
                lines.append(current_line)
                current_line = ""
                i += 1
            else:
                current_line += text[i]
                i += 1
        
        # Add any remaining content
        if current_line:
            lines.append(current_line)
        
        # Remove empty strings from the list
        return [line for line in lines if line != ""]

    def compute_visible(self, lines: list[str], pane_height: int, offset: int):
        """
        Given a list of lines, a pane height (usable lines), and a scroll offset,
        return the visible lines (bottom-aligned).
        offset == 0 => show bottom-most lines
        offset > 0 => show older lines (scrolled up)
        """
        usable = max(pane_height - 2, 0)  # reserve for borders/title
        total = len(lines)
        # clamp offset
        offset = max(0, min(offset, max(0, total - usable)))
        # start index for visible slice
        start = max(0, total - usable - offset)
        return lines[start : start + usable], offset, start

    def render_box(self, name: str, lines_list: list[str], syntax=False):
        # Check if console was resized and rebuild layout if needed
        if self.console.size != self.last_console_size:
            self.layout = self.build_layout()
            self.last_console_size = self.console.size

        pane_index = {"source": 0, "tokens": 1, "ir": 2, "code": 3, "log": 4}[name]


        # Calculate pane height
        if self.layout.map.get(self.layout[name]) is None:
            # Estimate height based on console size and mode
            console_height = self.console.size.height
            if name == "log":
                height = max(4, int(console_height * 0.25))
            elif self.mode == Tui.Mode.CODE_GEN:
                # Half of main area for upper/lower, then split between panes
                main_height = console_height - max(4, int(console_height * 0.25))
                height = max(6, main_height)
            else:
                height = max(10, console_height)
        else:
            height = self.layout.map[self.layout[name]].region.height

        with self.lock:
            offset: int = self.scroll_offsets[pane_index]

        if syntax:
            # For source panel, we need to compute visible lines and their starting line number
            visible, offset, start_index = self.compute_visible(lines_list, height, offset)
            
            # Update back the clamped offset
            with self.lock:
                self.scroll_offsets[pane_index] = offset
            
            content = "\n".join(visible)
            # Set start_line to the actual line number in the source file (1-indexed)
            start_line = start_index + 1
            syn = Syntax(content, "c", theme=self.theme, line_numbers=True, start_line=start_line)
            style = "bold cyan" if self.selected_pane == 0 else "cyan"
            return Panel(syn, title="Source", border_style=style)
        else:
            visible, offset, _ = self.compute_visible(lines_list, height, offset)
            
            # Update back the clamped offset
            with self.lock:
                self.scroll_offsets[pane_index] = offset

            title = {
                "tokens": "Tokens",
                "ir": "IR",
                "code": "Codegen",
                "log": "Debug Output",
            }[name]
            style_map = {
                "tokens": "green",
                "ir": "yellow",
                "code": "magenta",
                "log": "indian_red",
            }
            idx_map = {"tokens": 1, "ir": 2, "code": 3, "log": 4}
            style = (
                ("bold " + style_map[name])
                if self.selected_pane == idx_map[name]
                else style_map[name]
            )

            # Don't set fixed height on the Panel - let the Layout handle it
            return Panel("\n".join(visible), title=title, border_style=style)

    def render(self):
        # Check for console resize and rebuild layout if needed
        if self.console.size != self.last_console_size:
            self.layout = self.build_layout()
            self.last_console_size = self.console.size

        # Update all panels - ALL text panels need carriage return processing
        self.layout["source"].update(
            self.render_box(
                "source", self.lines_of(self.source_buf.getvalue()), syntax=True
            )
        )
        
        # Process tokens with carriage returns
        tokens_text = self.tokens_buf.getvalue()
        tokens_lines = self.process_carriage_returns(tokens_text)
        self.layout["tokens"].update(
            self.render_box("tokens", tokens_lines)
        )

        if self.mode >= Tui.Mode.PARSER:
            # Process IR with carriage returns
            ir_text = self.ir_buf.getvalue()
            ir_lines = self.process_carriage_returns(ir_text)
            self.layout["ir"].update(
                self.render_box("ir", ir_lines)
            )
            
            # Process log with carriage returns
            log_text = self.log_buf.getvalue()
            log_lines = self.process_carriage_returns(log_text)
            self.layout["log"].update(
                self.render_box("log", log_lines)
            )

        if self.mode >= Tui.Mode.CODE_GEN:
            # Process code with carriage returns
            code_text = self.code_buf.getvalue()
            code_lines = self.process_carriage_returns(code_text)
            self.layout["code"].update(
                self.render_box("code", code_lines)
            )

        return self.layout

    # endregion

    # region API used by your compiler to append data
    def log_source(self, line: str, end="\n", flush=True):
        with self.lock:
            self.source_buf.write(f"{line}{end}")
            self.scroll_offsets[0] = 0
        if flush:
            self.update()
        else:
            self.mark_refresh()

    def log_tokens(self, line: str = "", end="\n", flush=True):
        with self.lock:
            self.tokens_buf.write(f"{line}{end}")
            self.scroll_offsets[1] = 0
        if flush:
            self.update()
        else:
            self.mark_refresh()

    def log_ir(self, line: str, end="\n", flush=True):
        with self.lock:
            self.ir_buf.write(f"{line}{end}")
            self.scroll_offsets[2] = 0
        if flush:
            self.update()
        else:
            self.mark_refresh()

    def log_code(self, line: str, end="\n", flush=True):
        with self.lock:
            self.code_buf.write(f"{line}{end}")
            self.scroll_offsets[3] = 0
        if flush:
            self.update()
        else:
            self.mark_refresh()

    def log_debug(self, line: str, end="\n", flush=True):
        with self.lock:
            self.log_buf.write(f"{line}{end}")
            self.scroll_offsets[4] = 0
        if flush:
            self.update()
        else:
            self.mark_refresh()

    def mark_refresh(self):
        with self.lock:
            self.need_refresh = True

    # endregion

    def update(self):
        if self._live is not None:
            self._live.update(self.render())

    def input_thread(self):
        """Input handling thread (keyboard only)"""
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)  # allow signals (Ctrl-C) but read raw input
            while self.running:
                r, _, _ = select.select([fd], [], [], 0.1)
                if not r:
                    continue
                data = os.read(fd, 32)  # read up to 32 bytes
                if not data:
                    continue
                try:
                    s = data.decode("utf-8", "ignore")
                except:
                    s = ""
                if s in ("q", "\x03"):  # q or Ctrl-C
                    self.running = False
                    break
                if s in ("1", "2", "3", "4", "5"):
                    self.selected_pane = int(s) - 1
                    self.mark_refresh()
                    continue
                # j/k and arrows
                if s in ("j", "\x1b[B"):  # down (newer)
                    with self.lock:
                        self.scroll_offsets[self.selected_pane] = max(
                            0, self.scroll_offsets[self.selected_pane] - 1
                        )
                    self.mark_refresh()
                    continue
                if s in ("k", "\x1b[A"):  # up (older)
                    with self.lock:
                        self.scroll_offsets[self.selected_pane] += 1
                    self.mark_refresh()
                    continue
                if s in ("J", "\x1b[1;2B"):  # shift + down (newer)
                    with self.lock:
                        for i, offset in enumerate(self.scroll_offsets):
                            self.scroll_offsets[i] = max(0, offset - 1)
                    self.mark_refresh()
                    continue
                if s in ("K", "\x1b[1;2A"):  # shift + up (older)
                    with self.lock:
                        for i, offset in enumerate(self.scroll_offsets):
                            self.scroll_offsets[i] += 1
                    self.mark_refresh()
                    continue
                if s == "u":  # page up (older)
                    with self.lock:
                        self.scroll_offsets[self.selected_pane] += 10
                    self.mark_refresh()
                    continue
                if s == "d":  # page down (newer)
                    with self.lock:
                        self.scroll_offsets[self.selected_pane] = max(
                            0, self.scroll_offsets[self.selected_pane] - 10
                        )
                    self.mark_refresh()
                    continue
                if s == "g":  # go top
                    with self.lock:
                        name = ["source", "tokens", "ir", "code", "log"][
                            self.selected_pane
                        ]
                        if name in ["tokens", "ir", "code", "log"]:
                            # These need carriage return processing
                            text = {
                                "tokens": self.tokens_buf.getvalue(),
                                "ir": self.ir_buf.getvalue(),
                                "code": self.code_buf.getvalue(),
                                "log": self.log_buf.getvalue(),
                            }[name]
                            lines = self.process_carriage_returns(text)
                            line_count = len(lines)
                        else:
                            # Source pane
                            lines = self.source_buf.getvalue().splitlines()
                            line_count = len(lines)
                        size = self.console.size
                        # Estimate pane height based on console size and mode
                        if name == "log":
                            h = max(4, int(size.height * 0.25))
                        elif self.mode == Tui.Mode.CODE_GEN and name in [
                            "source",
                            "tokens",
                            "ir",
                            "code",
                        ]:
                            main_height = size.height - max(4, int(size.height * 0.25))
                            h = max(6, main_height // 2)
                        else:
                            h = max(10, size.height // 2)
                        usable = max(h - 2, 1)
                        max_off = max(0, line_count - usable)
                        self.scroll_offsets[self.selected_pane] = max_off
                    self.mark_refresh()
                    continue
                if s == "G":  # go bottom
                    with self.lock:
                        self.scroll_offsets[self.selected_pane] = 0
                    self.mark_refresh()
                    continue
                # ignore other keys
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass

    def _run(self, task: Callable[[], None], hold: bool):
        """Live loop + controlled generator"""

        # start input reader
        t = threading.Thread(target=self.input_thread, daemon=True)
        last_update_time = time.time()
        t.start()

        with Live(
            self.render(), console=self.console, refresh_per_second=20, screen=True
        ) as live:
            self._live = live
            task()

            self.running = hold
            # Holds the process after task run.
            while self.running:
                # refresh UI only when needed (efficient)
                if self.need_refresh or (time.time() - last_update_time) > 0.1:
                    with self.lock:
                        self.need_refresh = False
                    self.update()
                    last_update_time = time.time()

                time.sleep(0.03)  # keep UI responsive, tune as needed

        self.running = False
        t.join(timeout=0.2)

    def run(self, task: Callable[[], None], hold=False):
        try:
            self._run(task, hold)
        except KeyboardInterrupt:
            self.running = False
            print("\nExiting.", file=sys.stderr)


if __name__ == "__main__":
    ui = Tui(mode=Tui.Mode.CODE_GEN)

    def f():
        # Simulate a compiler pipeline with all panels
        source_code = [
            "// Sample program",
            "int main() {",
            "    int x = 5;",
            "    int y = x * 2;",
            "    float z = 3.14;",
            "    if (y > 10) {",
            "        return 1;",
            "    }",
            "    return 0;",
            "}"
        ]
        
        tokens = [
            "<TYPE, int> <ID, main> <'('> <')'> <'{'>",
            "<TYPE, int> <ID, x> <'='> <NUM, 5> <';'>",
            "<TYPE, int> <ID, y> <'='> <ID, x> <'*'> <NUM, 2> <';'>",
            "<TYPE, float> <ID, z> <'='> <NUM, 3> <'.'> <NUM, 14> <';'>",
            "<'if'> <'('> <ID, y> <'>'> <NUM, 10> <')'> <'{'>",
            "<'return'> <NUM, 1> <';'>",
            "<'}'>,"
            "<'return'> <NUM, 0> <';'>",
            "<'}'>",
        ]
        
        ir_code = [
            "function main:",
            "  entry:",
            "    %1 = alloca i32",
            "    %2 = alloca i32",
            "    %3 = alloca float",
            "    store i32 5, i32* %1",
            "    %4 = load i32, i32* %1",
            "    %5 = mul i32 %4, 2",
            "    store i32 %5, i32* %2",
            "    store float 3.140000, float* %3",
            "    %6 = load i32, i32* %2",
            "    %7 = icmp sgt i32 %6, 10",
            "    br i1 %7, label %if_true, label %if_end",
            "  if_true:",
            "    ret i32 1",
            "  if_end:",
            "    ret i32 0"
        ]
        
        asm_code = [
            "main:",
            "    push rbp",
            "    mov rbp, rsp",
            "    sub rsp, 16",
            "    mov DWORD [rbp-4], 5      ; x = 5",
            "    mov eax, DWORD [rbp-4]",
            "    imul eax, eax, 2",
            "    mov DWORD [rbp-8], eax    ; y = x * 2",
            "    mov DWORD [rbp-12], 0x4048f5c3 ; z = 3.14",
            "    mov eax, DWORD [rbp-8]",
            "    cmp eax, 10",
            "    jle .L2",
            "    mov eax, 1",
            "    jmp .L3",
            ".L2:",
            "    mov eax, 0",
            ".L3:",
            "    leave",
            "    ret"
        ]
        
        # Log source code
        for i, line in enumerate(source_code):
            ui.log_source(line)
            ui.log_debug(f"Processing line {i+1}...")
            time.sleep(0.1)
        
        # Log tokens with carriage returns (simulating lexer)
        ui.log_debug("\nStarting tokenization...")
        for i, token_line in enumerate(tokens):
            if i % 2 == 0:
                ui.log_tokens(f"\rTokenizing... {i+1}/{len(tokens)}", end="", flush=True)
            else:
                ui.log_tokens(f"\rTokenized: {token_line}")
            time.sleep(0.05)
        
        # Log IR code
        ui.log_debug("\nGenerating intermediate representation...")
        for i, ir_line in enumerate(ir_code):
            ui.log_ir(ir_line)
            if i % 3 == 0:
                ui.log_debug(f"\rIR generation: {i+1}/{len(ir_code)} lines", end="", flush=True)
            time.sleep(0.03)
        ui.log_debug("\rIR generation complete!")
        
        # Log assembly code
        ui.log_debug("\nGenerating assembly code...")
        for i, asm_line in enumerate(asm_code):
            ui.log_code(asm_line)
            if i % 4 == 0:
                ui.log_debug(f"\rCode generation: {i+1}/{len(asm_code)} lines", end="", flush=True)
            time.sleep(0.02)
        ui.log_debug("\rCode generation complete!")
        
        # Final status
        ui.log_debug("\n" + "="*50)
        ui.log_debug("Compilation successful!")
        ui.log_debug("Use keys 1-5 to select panes, j/k to scroll, q to quit")
        ui.log_debug("Try 'g' to go to top, 'G' to go to bottom of selected pane")

    ui.run(f, hold=True)
