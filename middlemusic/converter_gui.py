import logging
import sys
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

if __package__:
    from .config import LIBRARY_PATH
    from .converter import BITRATES, analyze_csv, convert_rows
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from middlemusic.config import LIBRARY_PATH
    from middlemusic.converter import BITRATES, analyze_csv, convert_rows

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as error:
        raise RuntimeError(
            "im gonna bluescreen if you dont install a Python build "
            "with Tk support to use the desktop converter."
        ) from error

    class ConverterWindow(tk.Tk):
        def __init__(self) -> None:
            super().__init__()
            self.title("dont you FUCKING dare convert millenial music")
            self.geometry("900x760")
            self.minsize(720, 640)

            self.csv_path = tk.StringVar()
            self.library_path = tk.StringVar(value=str(LIBRARY_PATH))
            self.output_path = tk.StringVar(value=str(LIBRARY_PATH / "Converted Files"))
            self.bitrate = tk.StringVar(value="192k")
            self.analysis = None
            self.events = Queue()
            self.running = False

            self._build_ui(ttk)
            self.protocol("WM_DELETE_WINDOW", self._close)

        def _build_ui(self, ttk) -> None:
            content = ttk.Frame(self, padding=18)
            content.pack(fill="both", expand=True)
            content.columnconfigure(0, weight=1)
            content.rowconfigure(5, weight=1)

            ttk.Label(
                content,
                text="fuck you copilot",
                font=("TkDefaultFont", 16, "bold"),
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(
                content,
                text=(
                    "WHAT DID I SAY ABOUT MILLENIAL MUSIC?. "
                    "Audio URLs and downloads are not supported."
                ),
                wraplength=840,
            ).grid(row=1, column=0, sticky="w", pady=(4, 14))

            paths = ttk.LabelFrame(content, text="Folders and CSV", padding=10)
            paths.grid(row=2, column=0, sticky="ew")
            paths.columnconfigure(1, weight=1)
            self._path_row(
                ttk,
                paths,
                0,
                "CSV file",
                self.csv_path,
                self._choose_csv,
                "Browse…",
                readonly=True,
            )
            self._path_row(
                ttk,
                paths,
                1,
                "Music library",
                self.library_path,
                self._choose_library,
                "Browse…",
            )
            self._path_row(
                ttk,
                paths,
                2,
                "Output folder",
                self.output_path,
                self._choose_output,
                "Browse…",
            )

            preview = ttk.LabelFrame(content, text="Automatic CSV preview", padding=10)
            preview.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
            preview.columnconfigure(0, weight=1)
            preview.rowconfigure(2, weight=1)
            self.preview_summary = tk.StringVar(
                value="Choose a CSV file to analyze and preview its contents."
            )
            ttk.Label(preview, textvariable=self.preview_summary).grid(
                row=0, column=0, sticky="w"
            )
            self.detected_columns = tk.StringVar()
            ttk.Label(
                preview,
                textvariable=self.detected_columns,
                wraplength=840,
            ).grid(row=1, column=0, sticky="w", pady=(4, 8))
            self.preview_table = ttk.Treeview(
                preview,
                columns=("source", "title", "artist", "album"),
                show="headings",
                height=6,
            )
            for field, heading, width in (
                ("source", "Local file", 300),
                ("title", "Title", 180),
                ("artist", "Artist", 160),
                ("album", "Album", 160),
            ):
                self.preview_table.heading(field, text=heading)
                self.preview_table.column(field, width=width, minwidth=90)
            self.preview_table.grid(row=2, column=0, sticky="nsew")
            preview_scrollbar = ttk.Scrollbar(
                preview, orient="vertical", command=self.preview_table.yview
            )
            preview_scrollbar.grid(row=2, column=1, sticky="ns")
            self.preview_table.configure(yscrollcommand=preview_scrollbar.set)

            options = ttk.Frame(content)
            options.grid(row=4, column=0, sticky="ew", pady=12)
            ttk.Label(options, text="MP3 bitrate").pack(side="left")
            ttk.Combobox(
                options,
                textvariable=self.bitrate,
                state="readonly",
                values=sorted(BITRATES, key=lambda value: int(value[:-1])),
                width=10,
            ).pack(side="left", padx=(8, 18))
            self.start_button = ttk.Button(
                options,
                text="Confirm import and convert",
                command=self._start_conversion,
                state="disabled",
            )
            self.start_button.pack(side="left")
            self.progress = ttk.Progressbar(options, mode="determinate", maximum=100)
            self.progress.pack(side="left", fill="x", expand=True, padx=(18, 0))

            results = ttk.LabelFrame(content, text="Progress and results", padding=10)
            results.grid(row=5, column=0, sticky="nsew")
            results.columnconfigure(0, weight=1)
            results.rowconfigure(1, weight=1)
            self.status = tk.StringVar(value="Select a CSV file to begin.")
            ttk.Label(results, textvariable=self.status).grid(
                row=0, column=0, sticky="w", pady=(0, 8)
            )
            log_frame = ttk.Frame(results)
            log_frame.grid(row=1, column=0, sticky="nsew")
            log_frame.columnconfigure(0, weight=1)
            log_frame.rowconfigure(0, weight=1)
            self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
            scrollbar = ttk.Scrollbar(
                log_frame, orient="vertical", command=self.log.yview
            )
            self.log.configure(yscrollcommand=scrollbar.set)
            self.log.grid(row=0, column=0, sticky="nsew")
            scrollbar.grid(row=0, column=1, sticky="ns")

        def _path_row(
            self, ttk, parent, row, label, variable, browse, button_text, readonly=False
        ):
            ttk.Label(parent, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=4
            )
            ttk.Entry(
                parent,
                textvariable=variable,
                state="readonly" if readonly else "normal",
            ).grid(row=row, column=1, sticky="ew", pady=4)
            ttk.Button(parent, text=button_text, command=browse).grid(
                row=row, column=2, padx=(8, 0), pady=4
            )

        def _choose_csv(self) -> None:
            selected = filedialog.askopenfilename(
                title="Choose a CSV file",
                filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
            )
            if selected:
                self.csv_path.set(selected)
                self._analyze_csv(Path(selected))

        def _choose_library(self) -> None:
            selected = filedialog.askdirectory(
                title="Choose your music library",
                initialdir=self.library_path.get() or str(LIBRARY_PATH),
            )
            if selected:
                self.library_path.set(selected)

        def _choose_output(self) -> None:
            selected = filedialog.askdirectory(
                title="Choose the output folder",
                initialdir=self.output_path.get() or str(LIBRARY_PATH),
                mustexist=False,
            )
            if selected:
                self.output_path.set(selected)

        def _analyze_csv(self, csv_path: Path) -> None:
            self.analysis = None
            self.start_button.configure(state="disabled")
            self.detected_columns.set("")
            for item in self.preview_table.get_children():
                self.preview_table.delete(item)
            try:
                self.analysis = analyze_csv(csv_path.read_bytes())
            except (OSError, ValueError) as error:
                self.preview_summary.set(f"Could not analyze CSV: {error}")
                self.status.set("Choose a supported CSV file.")
                messagebox.showerror("Could not analyze CSV", str(error), parent=self)
                return

            columns = ", ".join(
                f"{field.replace('_', ' ').title()}: {column}"
                for field, column in self.analysis.columns.items()
            )
            delimiter = (
                "tab"
                if self.analysis.delimiter == "\t"
                else repr(self.analysis.delimiter)
            )
            self.preview_summary.set(
                f"Detected {len(self.analysis.rows)} files; {delimiter}-separated CSV."
            )
            self.detected_columns.set(f"Detected fields: {columns}.")
            for row in self.analysis.rows[:8]:
                self.preview_table.insert(
                    "",
                    "end",
                    values=(
                        row.get("source", ""),
                        row.get("title", ""),
                        row.get("artist", ""),
                        row.get("album", ""),
                    ),
                )
            self.status.set("Review the preview, then confirm the import.")
            self.start_button.configure(state="normal")

        def _start_conversion(self) -> None:
            if self.running:
                return

            csv_path = Path(self.csv_path.get()).expanduser()
            library = Path(self.library_path.get()).expanduser()
            output = Path(self.output_path.get()).expanduser()
            if not csv_path.is_file():
                messagebox.showerror(
                    "Choose a CSV file", "Select an existing CSV file.", parent=self
                )
                return
            if not library.is_dir():
                messagebox.showerror(
                    "Choose a library",
                    "Select an existing music library folder.",
                    parent=self,
                )
                return
            if not str(self.output_path.get()).strip():
                messagebox.showerror(
                    "Choose an output folder",
                    "Select where converted MP3 files should be saved.",
                    parent=self,
                )
                return

            if self.analysis is None:
                messagebox.showerror(
                    "Analyze CSV first",
                    "Choose a CSV file and review its preview before confirming.",
                    parent=self,
                )
                return
            rows = self.analysis.rows

            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.configure(state="disabled")
            self.progress.configure(maximum=len(rows), value=0)
            self.status.set(f"Converting 0 of {len(rows)} files…")
            self.start_button.configure(state="disabled")
            self.running = True
            Thread(
                target=self._convert,
                args=(rows, library, output, self.bitrate.get()),
                daemon=True,
                name="middlemusic-desktop-converter",
            ).start()
            self.after(100, self._poll_events)

        def _convert(self, rows, library, output, bitrate) -> None:
            def report_progress(completed, total, result) -> None:
                self.events.put(("progress", (completed, total, result)))

            try:
                outputs, errors = convert_rows(
                    rows, library, output, bitrate, report_progress
                )
            except Exception as error:
                logger.exception("Desktop conversion failed")
                self.events.put(("fatal", str(error)))
                return
            self.events.put(("done", (outputs, errors)))

        def _poll_events(self) -> None:
            try:
                while True:
                    event, payload = self.events.get_nowait()
                    if event == "progress":
                        completed, total, result = payload
                        source = result.get("source", "") if result else ""
                        self.progress.configure(value=completed)
                        self.status.set(f"Processed {completed} of {total}: {source}")
                        if result and result["status"] == "completed":
                            self._append_log(f"Converted: {result['output']}")
                        elif result:
                            self._append_log(
                                f"Failed: {source} — {result.get('error', 'Conversion failed.')}"
                            )
                    elif event == "done":
                        outputs, errors = payload
                        self._finish(
                            f"Finished: {len(outputs)} converted, {len(errors)} failed."
                        )
                    elif event == "fatal":
                        self._finish(f"Conversion stopped: {payload}")
            except Empty:
                pass

            if self.running:
                self.after(100, self._poll_events)

        def _finish(self, message: str) -> None:
            self.running = False
            self.start_button.configure(state="normal")
            self.status.set(message)
            self._append_log(message)

        def _append_log(self, message: str) -> None:
            self.log.configure(state="normal")
            self.log.insert("end", f"{message}\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        def _close(self) -> None:
            if self.running:
                messagebox.showinfo(
                    "Conversion in progress",
                    "Wait for the current conversion to finish before closing.",
                    parent=self,
                )
                return
            self.destroy()

    ConverterWindow().mainloop()


if __name__ == "__main__":
    main()
