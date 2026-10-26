from __future__ import annotations

import platform
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import FileInfo, ScanResult, format_bytes, scan_folder


COLORS = {
    "canvas": "#f3f6f4",
    "surface": "#ffffff",
    "text": "#18251f",
    "muted": "#607069",
    "action": "#176b4d",
    "action_hover": "#10583e",
    "border": "#d9e2dd",
    "warning": "#9a5b13",
    "danger": "#a53636",
}


class ClutterCoachApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Digital Clutter Coach")
        self.geometry("1080x720")
        self.minsize(820, 560)
        self.configure(bg=COLORS["canvas"])
        self._set_window_icon()

        self.folder = tk.StringVar()
        self.status = tk.StringVar(value="Choose a folder to understand what is using its space.")
        self.result: ScanResult | None = None
        self.cancel_event = threading.Event()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.candidate_by_id: dict[str, FileInfo] = {}

        self._configure_styles()
        self._build_ui()
        self.after(100, self._process_events)

    def _set_window_icon(self) -> None:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        icon_path = base / "assets" / "app-icon.png"
        if icon_path.exists():
            try:
                self._window_icon = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self._window_icon)
            except tk.TclError:
                # The packaged macOS .app and Windows .exe still use their native icons.
                pass

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        if platform.system() == "Windows":
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=COLORS["canvas"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("TLabel", background=COLORS["canvas"], foreground=COLORS["text"], font=("TkDefaultFont", 10))
        style.configure("Surface.TLabel", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("Title.TLabel", font=("TkDefaultFont", 22, "bold"), foreground=COLORS["text"])
        style.configure("Subtitle.TLabel", font=("TkDefaultFont", 10), foreground=COLORS["muted"])
        style.configure("Metric.TLabel", background=COLORS["surface"], font=("TkDefaultFont", 18, "bold"), foreground=COLORS["text"])
        style.configure("MetricName.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
        style.configure("Accent.TButton", font=("TkDefaultFont", 10, "bold"), padding=(16, 9))
        style.map("Accent.TButton", foreground=[("!disabled", "#ffffff")], background=[("!disabled", COLORS["action"]), ("active", COLORS["action_hover"])])
        style.configure("TButton", padding=(12, 8))
        style.configure("Treeview", rowheight=30, borderwidth=0, font=("TkDefaultFont", 10))
        style.configure("Treeview.Heading", font=("TkDefaultFont", 10, "bold"), padding=(8, 8))
        style.map("Treeview", background=[("selected", "#d9eee5")], foreground=[("selected", COLORS["text"])])
        style.configure("TNotebook", background=COLORS["canvas"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 9))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Digital Clutter Coach", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="See what is taking up space. Review every suggestion. Nothing is permanently deleted.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))

        chooser = ttk.Frame(outer, style="Surface.TFrame", padding=14)
        chooser.pack(fill="x")
        chooser.columnconfigure(0, weight=1)
        self.folder_entry = ttk.Entry(chooser, textvariable=self.folder, font=("TkDefaultFont", 11))
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=5)
        ttk.Button(chooser, text="Choose folder", command=self._choose_folder).grid(row=0, column=1, padx=(0, 8))
        self.scan_button = ttk.Button(chooser, text="Scan folder", style="Accent.TButton", command=self._start_scan)
        self.scan_button.grid(row=0, column=2)

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(12, 5))
        status_row = ttk.Frame(outer)
        status_row.pack(fill="x", pady=(0, 12))
        ttk.Label(status_row, textvariable=self.status, style="Subtitle.TLabel").pack(side="left")
        self.cancel_button = ttk.Button(status_row, text="Cancel", command=self.cancel_event.set, state="disabled")
        self.cancel_button.pack(side="right")

        metrics = ttk.Frame(outer)
        metrics.pack(fill="x", pady=(0, 14))
        for column in range(3):
            metrics.columnconfigure(column, weight=1)
        self.metric_values: list[ttk.Label] = []
        for column, name in enumerate(("Files scanned", "Space analyzed", "Potential savings")):
            card = ttk.Frame(metrics, style="Surface.TFrame", padding=14)
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 0 if column == 2 else 5))
            value = ttk.Label(card, text="—", style="Metric.TLabel")
            value.pack(anchor="w")
            ttk.Label(card, text=name, style="MetricName.TLabel").pack(anchor="w", pady=(3, 0))
            self.metric_values.append(value)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        self._build_overview_tab()
        self._build_duplicates_tab()

    def _build_overview_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=(0, 12, 0, 0))
        self.notebook.add(frame, text="Storage overview")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.category_tree = ttk.Treeview(frame, columns=("category", "size", "share"), show="headings")
        for key, label, width, anchor in (("category", "File type", 300, "w"), ("size", "Space used", 160, "e"), ("share", "Share", 140, "e")):
            self.category_tree.heading(key, text=label)
            self.category_tree.column(key, width=width, anchor=anchor)
        self.category_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.category_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.category_tree.configure(yscrollcommand=scroll.set)

    def _build_duplicates_tab(self) -> None:
        frame = ttk.Frame(self.notebook, padding=(0, 12, 0, 0))
        self.notebook.add(frame, text="Duplicate review")
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        top = ttk.Frame(frame)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(top, text="The oldest copy in each group is protected. Select candidate rows to move them to Trash.", style="Subtitle.TLabel").pack(side="left")
        self.cleanup_button = ttk.Button(top, text="Review cleanup…", command=self._review_cleanup, state="disabled")
        self.cleanup_button.pack(side="right")
        self.duplicate_tree = ttk.Treeview(frame, columns=("status", "name", "size", "modified", "location"), show="headings", selectmode="extended")
        settings = (
            ("status", "Plan", 100, "w"), ("name", "File", 190, "w"), ("size", "Size", 90, "e"),
            ("modified", "Modified", 140, "w"), ("location", "Location", 440, "w"),
        )
        for key, label, width, anchor in settings:
            self.duplicate_tree.heading(key, text=label)
            self.duplicate_tree.column(key, width=width, anchor=anchor)
        self.duplicate_tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.duplicate_tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.duplicate_tree.configure(yscrollcommand=scroll.set)
        self.duplicate_tree.tag_configure("keep", foreground=COLORS["action"])
        self.duplicate_tree.tag_configure("candidate", foreground=COLORS["warning"])

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose a folder to scan", mustexist=True)
        if selected:
            self.folder.set(selected)

    def _start_scan(self) -> None:
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showinfo("Choose a folder", "Choose the folder you want to analyze first.", parent=self)
            return
        path = Path(folder).expanduser()
        if not path.is_dir():
            messagebox.showerror("Folder unavailable", "That folder does not exist or cannot be accessed.", parent=self)
            return
        self.cancel_event.clear()
        self.result = None
        self.scan_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.cleanup_button.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Scanning safely in read-only mode…")
        threading.Thread(target=self._scan_worker, args=(path,), daemon=True).start()

    def _scan_worker(self, path: Path) -> None:
        try:
            result = scan_folder(path, lambda count, current: self.events.put(("progress", (count, current))), self.cancel_event.is_set)
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _process_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    count, current = payload  # type: ignore[misc]
                    self.status.set(f"Scanned {count:,} files · {current}")
                elif kind == "done":
                    self._finish_scan(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    self._reset_busy_state()
                    messagebox.showerror("Scan failed", str(payload), parent=self)
                    self.status.set("The scan could not be completed.")
        except queue.Empty:
            pass
        self.after(100, self._process_events)

    def _reset_busy_state(self) -> None:
        self.progress.stop()
        self.scan_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def _finish_scan(self, result: ScanResult) -> None:
        self._reset_busy_state()
        if self.cancel_event.is_set():
            self.status.set(f"Scan cancelled after {len(result.files):,} files. No files were changed.")
            return
        self.result = result
        self.metric_values[0].configure(text=f"{len(result.files):,}")
        self.metric_values[1].configure(text=format_bytes(result.total_size))
        self.metric_values[2].configure(text=format_bytes(result.reclaimable_size))
        self._show_categories(result)
        self._show_duplicates(result)
        note = f" · {len(result.errors)} inaccessible item(s) skipped" if result.errors else ""
        self.status.set(f"Scan complete. {len(result.duplicate_groups):,} duplicate group(s) found{note}.")

    def _show_categories(self, result: ScanResult) -> None:
        self.category_tree.delete(*self.category_tree.get_children())
        total = result.total_size or 1
        for category, size in result.category_sizes.most_common():
            self.category_tree.insert("", "end", values=(category, format_bytes(size), f"{size / total:.1%}"))

    def _show_duplicates(self, result: ScanResult) -> None:
        self.duplicate_tree.delete(*self.duplicate_tree.get_children())
        self.candidate_by_id.clear()
        candidate_ids: list[str] = []
        for group_number, group in enumerate(result.duplicate_groups, start=1):
            for index, item in enumerate(group):
                candidate = index > 0
                iid = f"g{group_number}-{index}"
                self.duplicate_tree.insert(
                    "", "end", iid=iid,
                    values=("Candidate" if candidate else "Keep", item.path.name, format_bytes(item.size), datetime.fromtimestamp(item.modified).strftime("%Y-%m-%d %H:%M"), str(item.path.parent)),
                    tags=("candidate" if candidate else "keep",),
                )
                if candidate:
                    self.candidate_by_id[iid] = item
                    candidate_ids.append(iid)
        if candidate_ids:
            self.duplicate_tree.selection_set(candidate_ids)
            self.cleanup_button.configure(state="normal")

    def _review_cleanup(self) -> None:
        selected = [self.candidate_by_id[iid] for iid in self.duplicate_tree.selection() if iid in self.candidate_by_id]
        if not selected:
            messagebox.showinfo("Nothing selected", "Select one or more rows marked Candidate.", parent=self)
            return
        total = sum(item.size for item in selected)
        preview = "\n".join(f"• {item.path.name} — {format_bytes(item.size)}" for item in selected[:8])
        if len(selected) > 8:
            preview += f"\n…and {len(selected) - 8} more"
        approved = messagebox.askyesno(
            "Approve cleanup plan",
            f"Move {len(selected)} selected duplicate file(s) ({format_bytes(total)}) to the system Trash?\n\n{preview}\n\nYou may be able to restore them from Trash until it is emptied.",
            icon="warning", default="no", parent=self,
        )
        if approved:
            self._move_to_trash(selected)

    def _move_to_trash(self, files: list[FileInfo]) -> None:
        try:
            from send2trash import send2trash
        except ImportError:
            messagebox.showerror("Cleanup component missing", "Install the app requirements first: pip install -r requirements.txt", parent=self)
            return
        moved, failures = 0, []
        for item in files:
            try:
                send2trash(str(item.path))
                moved += 1
            except Exception as exc:
                failures.append(f"{item.path}: {exc}")
        if failures:
            messagebox.showwarning("Cleanup partially completed", f"Moved {moved} file(s) to Trash. {len(failures)} could not be moved.\n\n" + "\n".join(failures[:5]), parent=self)
        else:
            messagebox.showinfo("Cleanup complete", f"Moved {moved} file(s) to the system Trash.", parent=self)
        self._start_scan()


def main() -> None:
    app = ClutterCoachApp()
    app.mainloop()


if __name__ == "__main__":
    main()
