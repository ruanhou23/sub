import os
import sys
import threading
import time
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, List, Dict, Any

from core.ocr_engine import OCREngine
from core.video_processor import VideoProcessor
from core.srt_writer import format_timestamp, write_subtitles_file
from .preview_widget import PreviewWidget

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SubViet - Trích Xuất Phụ Đề Tiếng Việt Từ Video & M3U8")
        self.geometry("1100x720")
        self.minsize(950, 640)
        self.configure(bg="#1e1e2e")

        # Initialize core components
        self.ocr_engine = OCREngine()
        self.processor = VideoProcessor(self.ocr_engine)

        self.extracted_subtitles: List[Dict[str, Any]] = []
        self.worker_thread: Optional[threading.Thread] = None
        self.current_video_source = ""
        self.video_duration = 0.0
        self._updating_crop_ui = False

        self._setup_styles()
        self._build_ui()
        self._check_tesseract_environment()

    def _setup_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        # Dark theme palette
        self.style.configure(".", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 9))
        self.style.configure("TFrame", background="#1e1e2e")
        self.style.configure("Card.TFrame", background="#181825", relief="flat")
        self.style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4")
        self.style.configure("Card.TLabel", background="#181825", foreground="#cdd6f4")
        self.style.configure("Muted.TLabel", background="#181825", foreground="#a6adc8")
        self.style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), foreground="#cdd6f4", background="#181825")

        # Treeview styling
        self.style.configure(
            "Treeview",
            background="#11111b",
            foreground="#cdd6f4",
            fieldbackground="#11111b",
            rowheight=26,
            font=("Segoe UI", 9)
        )
        self.style.configure(
            "Treeview.Heading",
            background="#313244",
            foreground="#cdd6f4",
            font=("Segoe UI", 9, "bold")
        )
        self.style.map(
            "Treeview",
            background=[("selected", "#45475a")],
            foreground=[("selected", "#a6e3a1")]
        )

        # Progressbar
        self.style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#313244",
            background="#a6e3a1",
            thickness=14
        )

    def _build_ui(self):
        # 1. Top Header Bar
        header = tk.Frame(self, bg="#181825", height=50)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        title_lbl = tk.Label(
            header,
            text="✨ SubViet — Trích xuất phụ đề Hardsub sang SRT/VTT",
            font=("Segoe UI", 13, "bold"),
            fg="#cdd6f4",
            bg="#181825"
        )
        title_lbl.pack(side=tk.LEFT, padx=16)

        self.ocr_status_badge = tk.Label(
            header,
            text="Đang kiểm tra Tesseract...",
            font=("Segoe UI", 9),
            fg="#f9e2af",
            bg="#313244",
            padx=10,
            pady=3
        )
        self.ocr_status_badge.pack(side=tk.RIGHT, padx=16)

        self.btn_download_model = tk.Button(
            header,
            text="⬇ Tải từ điển Tiếng Việt",
            font=("Segoe UI", 9, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            cursor="hand2",
            relief="flat",
            command=self._on_download_model_clicked
        )
        # Hidden unless model is missing

        # Main Layout (Left: Preview & Settings, Right: Table & Realtime Progress)
        main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        # === LEFT PANEL ===
        left_frame = ttk.Frame(main_paned, style="Card.TFrame")
        main_paned.add(left_frame, weight=1)

        # Section: Video Source
        src_box = tk.LabelFrame(
            left_frame,
            text=" Nguồn video đầu vào ",
            fg="#89b4fa",
            bg="#181825",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=8
        )
        src_box.pack(fill=tk.X, padx=8, pady=6)

        self.source_mode = tk.StringVar(value="file")
        rb_frame = tk.Frame(src_box, bg="#181825")
        rb_frame.pack(fill=tk.X, pady=(0, 4))

        tk.Radiobutton(
            rb_frame, text="File video trong máy (MP4, MKV...)",
            variable=self.source_mode, value="file",
            command=self._switch_source_mode,
            bg="#181825", fg="#cdd6f4", selectcolor="#313244",
            activebackground="#181825", activeforeground="#89b4fa"
        ).pack(side=tk.LEFT, padx=(0, 16))

        tk.Radiobutton(
            rb_frame, text="Link phát trực tuyến (M3U8 / HTTP)",
            variable=self.source_mode, value="url",
            command=self._switch_source_mode,
            bg="#181825", fg="#cdd6f4", selectcolor="#313244",
            activebackground="#181825", activeforeground="#89b4fa"
        ).pack(side=tk.LEFT)

        input_row = tk.Frame(src_box, bg="#181825")
        input_row.pack(fill=tk.X, pady=4)

        self.entry_source = tk.Entry(
            input_row,
            bg="#11111b", fg="#cdd6f4", insertbackground="#cdd6f4",
            relief="flat", highlightthickness=1, highlightbackground="#313244"
        )
        self.entry_source.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))

        self.btn_browse = tk.Button(
            input_row, text="Chọn file...", font=("Segoe UI", 9),
            bg="#313244", fg="#cdd6f4", activebackground="#45475a",
            relief="flat", cursor="hand2", padx=10,
            command=self._browse_video_file
        )
        self.btn_browse.pack(side=tk.RIGHT)

        # Preview Widget
        preview_box = tk.LabelFrame(
            left_frame,
            text=" Xem trước & Căn vùng phụ đề ",
            fg="#89b4fa",
            bg="#181825",
            font=("Segoe UI", 10, "bold"),
            padx=6,
            pady=6
        )
        preview_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        self.preview_widget = PreviewWidget(
            preview_box,
            bg_color="#181825",
            on_crop_change=self._on_crop_box_changed
        )
        self.preview_widget.pack(fill=tk.BOTH, expand=True)

        # Sliders Frame
        sliders_frame = tk.Frame(preview_box, bg="#181825")
        sliders_frame.pack(fill=tk.X, pady=(6, 0))

        # Crop presets row
        crop_btn_row = tk.Frame(sliders_frame, bg="#181825")
        crop_btn_row.pack(fill=tk.X, pady=(0, 2))

        btn_preset_bot = tk.Button(
            crop_btn_row, text="📐 Đáy mặc định (18%)", font=("Segoe UI", 8),
            bg="#313244", fg="#cdd6f4", activebackground="#45475a",
            relief="flat", cursor="hand2", padx=6, pady=2,
            command=self._reset_crop_bottom
        )
        btn_preset_bot.pack(side=tk.LEFT, padx=(0, 6))

        btn_preset_full = tk.Button(
            crop_btn_row, text="🔲 Toàn màn hình", font=("Segoe UI", 8),
            bg="#313244", fg="#cdd6f4", activebackground="#45475a",
            relief="flat", cursor="hand2", padx=6, pady=2,
            command=self._reset_crop_full
        )
        btn_preset_full.pack(side=tk.LEFT)

        # Crop Height Slider
        crop_row = tk.Frame(sliders_frame, bg="#181825")
        crop_row.pack(fill=tk.X, pady=2)
        tk.Label(crop_row, text="Độ cao vùng sub đáy:", fg="#a6adc8", bg="#181825").pack(side=tk.LEFT)
        self.lbl_crop_val = tk.Label(crop_row, text="18% (Đáy)", fg="#a6e3a1", bg="#181825", font=("Segoe UI", 9, "bold"))
        self.lbl_crop_val.pack(side=tk.RIGHT)

        self.scale_crop = ttk.Scale(
            sliders_frame, from_=6, to=35, value=18,
            command=self._on_crop_slider_change
        )
        self.scale_crop.pack(fill=tk.X)

        # Threshold Slider
        thresh_row = tk.Frame(sliders_frame, bg="#181825")
        thresh_row.pack(fill=tk.X, pady=2)
        tk.Label(thresh_row, text="Độ nhạy lọc chữ (Trắng & Vàng):", fg="#a6adc8", bg="#181825").pack(side=tk.LEFT)
        self.lbl_thresh_val = tk.Label(thresh_row, text="185", fg="#fab387", bg="#181825", font=("Segoe UI", 9, "bold"))
        self.lbl_thresh_val.pack(side=tk.RIGHT)

        self.scale_thresh = ttk.Scale(
            sliders_frame, from_=140, to=230, value=185,
            command=lambda v: self.lbl_thresh_val.config(text=str(int(float(v))))
        )
        self.scale_thresh.pack(fill=tk.X)

        # AI Engine Selection Combo
        engine_row = tk.Frame(sliders_frame, bg="#181825")
        engine_row.pack(fill=tk.X, pady=4)
        tk.Label(engine_row, text="Mô hình AI:", fg="#a6adc8", bg="#181825").pack(side=tk.LEFT)
        self.combo_engine = ttk.Combobox(
            engine_row,
            values=[
                "🇻🇳 VietOCR (Transformer - Chuẩn dấu 100%)",
                "🤖 EasyOCR (AI Deep Learning - Chuẩn dấu)",
                "⚡ Tesseract (Model Best - Nhanh & Lọc sạch)"
            ],
            state="readonly",
            width=32
        )
        self.combo_engine.current(0)
        self.combo_engine.pack(side=tk.RIGHT)
        self.combo_engine.bind("<<ComboboxSelected>>", self._on_engine_selected)

        # Sampling Speed Combo
        speed_row = tk.Frame(sliders_frame, bg="#181825")
        speed_row.pack(fill=tk.X, pady=4)
        tk.Label(speed_row, text="Tốc độ lấy mẫu:", fg="#a6adc8", bg="#181825").pack(side=tk.LEFT)
        self.combo_speed = ttk.Combobox(
            speed_row,
            values=["1.0 frame/giây (Nhanh & nhẹ)", "2.0 frames/giây (Chuẩn xác)", "0.5 frame/giây (Siêu tốc)"],
            state="readonly",
            width=30
        )
        self.combo_speed.current(1)
        self.combo_speed.pack(side=tk.RIGHT)

        # Output file destination
        out_box = tk.LabelFrame(
            left_frame,
            text=" Đường dẫn xuất file phụ đề ",
            fg="#89b4fa",
            bg="#181825",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=6
        )
        out_box.pack(fill=tk.X, padx=8, pady=6)

        out_row = tk.Frame(out_box, bg="#181825")
        out_row.pack(fill=tk.X)

        self.entry_output = tk.Entry(
            out_row,
            bg="#11111b", fg="#cdd6f4", insertbackground="#cdd6f4",
            relief="flat", highlightthickness=1, highlightbackground="#313244"
        )
        self.entry_output.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))

        btn_save_as = tk.Button(
            out_row, text="Lưu thành...", font=("Segoe UI", 9),
            bg="#313244", fg="#cdd6f4", activebackground="#45475a",
            relief="flat", cursor="hand2", padx=8,
            command=self._browse_output_file
        )
        btn_save_as.pack(side=tk.RIGHT)

        # === RIGHT PANEL ===
        right_frame = ttk.Frame(main_paned, style="Card.TFrame")
        main_paned.add(right_frame, weight=1)

        # Control Buttons
        ctl_frame = tk.Frame(right_frame, bg="#181825")
        ctl_frame.pack(fill=tk.X, padx=8, pady=8)

        self.btn_start = tk.Button(
            ctl_frame, text="▶ BẮT ĐẦU BÓC SUB", font=("Segoe UI", 10, "bold"),
            bg="#a6e3a1", fg="#11111b", activebackground="#94e2d5",
            relief="flat", cursor="hand2", padx=16, pady=6,
            command=self._on_start_clicked
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_pause = tk.Button(
            ctl_frame, text="⏸ Tạm dừng", font=("Segoe UI", 9, "bold"),
            bg="#f9e2af", fg="#11111b", activebackground="#f5c2e7",
            relief="flat", cursor="hand2", padx=12, pady=6, state=tk.DISABLED,
            command=self._on_pause_clicked
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_stop = tk.Button(
            ctl_frame, text="⏹ Dừng hẳn", font=("Segoe UI", 9, "bold"),
            bg="#f38ba8", fg="#11111b", activebackground="#eba0ac",
            relief="flat", cursor="hand2", padx=12, pady=6, state=tk.DISABLED,
            command=self._on_stop_clicked
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_open_folder = tk.Button(
            ctl_frame, text="📂 Mở file SRT", font=("Segoe UI", 9),
            bg="#313244", fg="#cdd6f4", activebackground="#45475a",
            relief="flat", cursor="hand2", padx=10, pady=6,
            command=self._on_open_folder_clicked
        )
        self.btn_open_folder.pack(side=tk.RIGHT)

        # Progress Area
        progress_box = tk.Frame(right_frame, bg="#181825")
        progress_box.pack(fill=tk.X, padx=8, pady=4)

        self.progress_bar = ttk.Progressbar(
            progress_box,
            style="Horizontal.TProgressbar",
            mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))

        stats_row = tk.Frame(progress_box, bg="#181825")
        stats_row.pack(fill=tk.X)

        self.lbl_progress_percent = tk.Label(
            stats_row, text="Tiến độ: 0%", fg="#a6e3a1", bg="#181825", font=("Segoe UI", 9, "bold")
        )
        self.lbl_progress_percent.pack(side=tk.LEFT)

        self.lbl_eta = tk.Label(
            stats_row, text="ETA: --:--", fg="#a6adc8", bg="#181825"
        )
        self.lbl_eta.pack(side=tk.RIGHT)

        self.lbl_speed = tk.Label(
            stats_row, text="Tốc độ: -- FPS", fg="#89b4fa", bg="#181825"
        )
        self.lbl_speed.pack(side=tk.RIGHT, padx=12)

        # Realtime Subtitle Table
        table_label_row = tk.Frame(right_frame, bg="#181825")
        table_label_row.pack(fill=tk.X, padx=8, pady=(8, 2))

        tk.Label(
            table_label_row, text="Danh sách phụ đề bóc tách theo thời gian thực:",
            fg="#cdd6f4", bg="#181825", font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)

        self.lbl_sub_count = tk.Label(
            table_label_row, text="0 câu", fg="#fab387", bg="#181825", font=("Segoe UI", 9, "bold")
        )
        self.lbl_sub_count.pack(side=tk.RIGHT)

        table_frame = tk.Frame(right_frame, bg="#181825")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        columns = ("index", "time", "text")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("index", text="#", anchor=tk.CENTER)
        self.tree.heading("time", text="Thời gian (Bắt đầu -> Kết thúc)", anchor=tk.W)
        self.tree.heading("text", text="Nội dung phụ đề tiếng Việt", anchor=tk.W)

        self.tree.column("index", width=45, minwidth=35, anchor=tk.CENTER)
        self.tree.column("time", width=190, minwidth=150, anchor=tk.W)
        self.tree.column("text", width=360, minwidth=200, anchor=tk.W)

        tree_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Bottom Status Bar
        self.status_bar = tk.Label(
            self,
            text="Sẵn sàng. Hãy chọn file video hoặc dán link M3U8 để bắt đầu.",
            fg="#a6adc8",
            bg="#11111b",
            anchor=tk.W,
            padx=12,
            pady=5,
            font=("Segoe UI", 8)
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _check_tesseract_environment(self):
        if not self.ocr_engine.is_tesseract_available():
            self.ocr_status_badge.config(
                text="❌ Chưa tìm thấy Tesseract OCR!",
                fg="#f38ba8", bg="#313244"
            )
            self.status_bar.config(
                text="Chưa tìm thấy Tesseract OCR. Hãy cài Tesseract vào C:\\Program Files\\Tesseract-OCR"
            )
            return

        if self.ocr_engine.is_vietnamese_model_ready():
            model_info = self.ocr_engine.get_model_info()
            if model_info["type"] == "best":
                self.ocr_status_badge.config(
                    text=f"✔ Model Tesseract: Best ({model_info['size_mb']}MB - Chuẩn dấu)",
                    fg="#a6e3a1", bg="#313244"
                )
                self.btn_download_model.pack_forget()
            else:
                self.ocr_status_badge.config(
                    text="⚠️ Đang dùng bản Fast (Có thể thiếu dấu)",
                    fg="#f9e2af", bg="#313244"
                )
                self.btn_download_model.config(state=tk.NORMAL, text="⬆ Nâng cấp Model Best (~12MB)")
                self.btn_download_model.pack(side=tk.RIGHT, padx=8)
        else:
            self.ocr_status_badge.config(
                text="⚠️ Thiếu từ điển Tiếng Việt (vie.traineddata)",
                fg="#f9e2af", bg="#313244"
            )
            self.btn_download_model.config(state=tk.NORMAL, text="⬇ Tải từ điển Tiếng Việt")
            self.btn_download_model.pack(side=tk.RIGHT, padx=8)

    def _on_download_model_clicked(self):
        self.btn_download_model.config(state=tk.DISABLED, text="Đang tải...")
        self.status_bar.config(text="Đang tải gói từ điển tiếng Việt (vie.traineddata)...")

        def download_worker():
            try:
                def on_dl_progress(downloaded, total, percent):
                    self.after(0, lambda: self.status_bar.config(
                        text=f"Đang tải từ điển Tiếng Việt: {percent:.1f}% ({downloaded // 1024} KB / {total // 1024} KB)"
                    ))

                self.ocr_engine.download_vietnamese_model(on_dl_progress)
                self.after(0, self._on_download_success)
            except Exception as e:
                self.after(0, lambda: self._on_download_failed(str(e)))

        threading.Thread(target=download_worker, daemon=True).start()

    def _on_download_success(self):
        messagebox.showinfo("Thành công", "Đã tải từ điển tiếng Việt thành công vào thư mục tessdata!")
        self._check_tesseract_environment()
        self.status_bar.config(text="Từ điển tiếng Việt đã sẵn sàng!")

    def _on_download_failed(self, error_msg: str):
        messagebox.showerror("Lỗi tải từ điển", f"Không thể tải từ điển: {error_msg}")
        self.btn_download_model.config(state=tk.NORMAL, text="⬇ Tải từ điển Tiếng Việt")
        self.status_bar.config(text="Lỗi tải từ điển tiếng Việt.")

    def _switch_source_mode(self):
        mode = self.source_mode.get()
        if mode == "file":
            self.btn_browse.config(text="Chọn file...", state=tk.NORMAL, command=self._browse_video_file)
            self.entry_source.delete(0, tk.END)
        else:
            self.btn_browse.config(text="Tải preview", state=tk.NORMAL, command=self._load_url_preview)
            self.entry_source.delete(0, tk.END)
            self.entry_source.insert(0, "https://")

    def _browse_video_file(self):
        filepath = filedialog.askopenfilename(
            title="Chọn file video có phụ đề Hardsub",
            filetypes=[
                ("Video Files", "*.mp4 *.mkv *.avi *.ts *.webm *.mov *.m4v"),
                ("All Files", "*.*")
            ]
        )
        if filepath:
            self.entry_source.delete(0, tk.END)
            self.entry_source.insert(0, filepath)
            
            # Default output path alongside video
            base_name = os.path.splitext(filepath)[0]
            self.entry_output.delete(0, tk.END)
            self.entry_output.insert(0, f"{base_name}_sub.srt")

            self._load_video_preview(filepath)

    def _load_url_preview(self):
        url = self.entry_source.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("Nhắc nhở", "Vui lòng dán đường dẫn video hoặc M3U8 hợp lệ!")
            return

        if not self.entry_output.get().strip():
            # Save into current project directory
            desktop_sub = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output_sub.srt")
            self.entry_output.delete(0, tk.END)
            self.entry_output.insert(0, desktop_sub)

        self._load_video_preview(url)

    def _load_video_preview(self, source: str):
        self.status_bar.config(text=f"Đang tải thông tin video: {os.path.basename(source) or source}...")
        self.current_video_source = source

        def worker():
            try:
                info = VideoProcessor.get_video_info(source)
                self.video_duration = info["duration"]
                # Grab a frame around 15% into the video (likely has subtitles)
                preview_sec = min(30.0, self.video_duration * 0.15) if self.video_duration > 0 else 5.0
                frame = VideoProcessor.get_preview_frame(source, preview_sec)
                
                self.after(0, lambda: self._on_preview_loaded(frame, info))
            except Exception as e:
                self.after(0, lambda: self.status_bar.config(text=f"Lỗi đọc video: {str(e)}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_preview_loaded(self, frame, info: Dict[str, Any]):
        if frame is not None:
            self.preview_widget.set_frame(frame)
            dur_str = format_timestamp(info["duration"])[:8]
            self.status_bar.config(
                text=f"Đã nạp video: {info['width']}x{info['height']} | {info['fps']:.1f} FPS | Thời lượng: {dur_str}"
            )
        else:
            self.status_bar.config(text="Không thể trích xuất khung hình xem trước.")

    def _on_engine_selected(self, event=None):
        sel = self.combo_engine.get()
        if "VietOCR" in sel:
            self.ocr_engine.set_engine("vietocr")
            self.status_bar.config(
                text="Đã chọn VietOCR (Transformer - Model tiếng Việt chuẩn xác nhất, nhận diện dấu hoàn hảo)."
            )
        elif "EasyOCR" in sel:
            self.ocr_engine.set_engine("easyocr")
            self.status_bar.config(
                text="Đã chọn EasyOCR (AI Deep Learning - Nhận diện trực tiếp trên ảnh màu, chuẩn dấu 100%)."
            )
        else:
            self.ocr_engine.set_engine("tesseract")
            self.status_bar.config(
                text="Đã chọn Tesseract (Model Best - Tốc độ nhanh và nhẹ)."
            )

    def _on_crop_slider_change(self, val):
        if self._updating_crop_ui:
            return
        self._updating_crop_ui = True
        try:
            ratio = float(val) / 100.0
            self.lbl_crop_val.config(text=f"{int(float(val))}% (Đáy)")
            self.preview_widget.set_crop_ratio(ratio)
        finally:
            self._updating_crop_ui = False

    def _on_crop_box_changed(self, crop_box: Tuple[float, float, float, float]):
        if self._updating_crop_ui:
            return
        self._updating_crop_ui = True
        try:
            x1, y1, x2, y2 = crop_box
            # Kiểm tra nếu là dải đáy (x1=0, x2=1, y2=1)
            if abs(x1 - 0.0) < 0.01 and abs(x2 - 1.0) < 0.01 and abs(y2 - 1.0) < 0.01:
                ratio = 1.0 - y1
                pct = int(round(ratio * 100))
                self.lbl_crop_val.config(text=f"{pct}% (Đáy)")
                if 6 <= pct <= 35:
                    self.scale_crop.set(pct)
            else:
                w_pct = int(round((x2 - x1) * 100))
                h_pct = int(round((y2 - y1) * 100))
                self.lbl_crop_val.config(text=f"Tùy chỉnh ({w_pct}%×{h_pct}%)")
        finally:
            self._updating_crop_ui = False

    def _reset_crop_bottom(self):
        val = 18.0
        self._updating_crop_ui = True
        try:
            self.scale_crop.set(val)
            self.preview_widget.reset_to_bottom(val / 100.0)
            self.lbl_crop_val.config(text=f"{int(val)}% (Đáy)")
        finally:
            self._updating_crop_ui = False

    def _reset_crop_full(self):
        self._updating_crop_ui = True
        try:
            self.preview_widget.reset_to_full()
            self.lbl_crop_val.config(text="Toàn màn hình (100%)")
        finally:
            self._updating_crop_ui = False

    def _browse_output_file(self):
        filepath = filedialog.asksaveasfilename(
            title="Chọn nơi lưu file phụ đề",
            defaultextension=".srt",
            filetypes=[("SRT Subtitle", "*.srt"), ("WebVTT Subtitle", "*.vtt")]
        )
        if filepath:
            self.entry_output.delete(0, tk.END)
            self.entry_output.insert(0, filepath)

    def _on_start_clicked(self):
        source = self.entry_source.get().strip()
        output = self.entry_output.get().strip()

        if not source or source == "https://":
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng chọn file video hoặc dán link video!")
            return

        if not output:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng chỉ định đường dẫn lưu file phụ đề!")
            return

        # Engine validation
        engine_sel = self.combo_engine.get()
        if "VietOCR" in engine_sel:
            if not self.ocr_engine.is_vietocr_available():
                messagebox.showerror("Thiếu thư viện", "VietOCR chưa được cài đặt. Vui lòng cài đặt qua pip install vietocr.")
                return
            self.ocr_engine.set_engine("vietocr")
        elif "EasyOCR" in engine_sel:
            if not self.ocr_engine.is_easyocr_available():
                messagebox.showerror("Thiếu thư viện", "EasyOCR chưa được cài đặt.")
                return
            self.ocr_engine.set_engine("easyocr")
        else:
            self.ocr_engine.set_engine("tesseract")
            if not self.ocr_engine.is_tesseract_available():
                messagebox.showerror("Thiếu Tesseract", "Không tìm thấy Tesseract OCR trên hệ thống!")
                return

            if not self.ocr_engine.is_vietnamese_model_ready():
                resp = messagebox.askyesno(
                    "Chưa có từ điển tiếng Việt",
                    "Chưa có từ điển tiếng Việt (vie.traineddata). Bạn có muốn tự động tải về ngay bây giờ không?"
                )
                if resp:
                    self._on_download_model_clicked()
                return

        # Prepare parameters
        crop_ratio = float(self.scale_crop.get()) / 100.0
        crop_box = self.preview_widget.get_crop_box()
        thresh_val = int(float(self.scale_thresh.get()))
        
        speed_idx = self.combo_speed.current()
        sample_fps = 2.0
        if speed_idx == 0:
            sample_fps = 1.0
        elif speed_idx == 2:
            sample_fps = 0.5

        # Reset UI
        self.tree.delete(*self.tree.get_children())
        self.extracted_subtitles.clear()
        self.lbl_sub_count.config(text="0 câu")
        self.progress_bar["value"] = 0
        self.lbl_progress_percent.config(text="Tiến độ: 0%")

        # Set button states
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸ Tạm dừng")
        self.btn_stop.config(state=tk.NORMAL)

        # Start worker thread
        def run_ocr_task():
            def on_prog(curr_sec, total_sec, percent, fps, eta):
                self.after(0, lambda: self._update_progress_ui(curr_sec, total_sec, percent, fps, eta))

            def on_sub(item):
                self.after(0, lambda: self._add_sub_to_table(item))

            def on_stat(msg):
                self.after(0, lambda: self.status_bar.config(text=msg))

            def on_done(subs, out_file):
                self.after(0, lambda: self._on_processing_complete(subs, out_file))

            def on_err(err):
                self.after(0, lambda: self._on_processing_error(err))

            self.processor.process_video(
                video_source=source,
                output_filepath=output,
                crop_bottom_ratio=crop_ratio,
                crop_box=crop_box,
                sample_fps=sample_fps,
                threshold_val=thresh_val,
                on_progress=on_prog,
                on_sub_found=on_sub,
                on_status=on_stat,
                on_complete=on_done,
                on_error=on_err,
            )

        self.worker_thread = threading.Thread(target=run_ocr_task, daemon=True)
        self.worker_thread.start()

    def _update_progress_ui(self, curr_sec: float, total_sec: float, percent: float, fps: float, eta: float):
        self.progress_bar["value"] = percent
        curr_str = format_timestamp(curr_sec)[:8]
        tot_str = format_timestamp(total_sec)[:8] if total_sec > 0 else "--:--"
        self.lbl_progress_percent.config(text=f"Tiến độ: {percent:.1f}% ({curr_str} / {tot_str})")
        self.lbl_speed.config(text=f"Tốc độ: {fps:.1f} FPS")
        eta_str = format_timestamp(eta)[:8] if eta > 0 else "00:00:00"
        self.lbl_eta.config(text=f"ETA: {eta_str}")

    def _add_sub_to_table(self, item: Dict[str, Any]):
        idx = item["index"]
        time_str = f"{format_timestamp(item['start'])} -> {format_timestamp(item['end'])}"
        text = item["text"].replace("\n", " | ")
        
        row_id = self.tree.insert("", tk.END, values=(idx, time_str, text))
        self.tree.see(row_id)
        self.lbl_sub_count.config(text=f"{len(self.tree.get_children())} câu")

    def _on_pause_clicked(self):
        if self.processor.is_paused():
            self.processor.resume()
            self.btn_pause.config(text="⏸ Tạm dừng", bg="#f9e2af")
            self.status_bar.config(text="Đang tiếp tục xử lý...")
        else:
            self.processor.pause()
            self.btn_pause.config(text="▶ Tiếp tục", bg="#a6e3a1")
            self.status_bar.config(text="Đang tạm dừng...")

    def _on_stop_clicked(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn dừng quá trình bóc sub? Các câu sub đã quét sẽ được lưu lại."):
            self.processor.stop()
            self.btn_stop.config(state=tk.DISABLED)
            self.btn_pause.config(state=tk.DISABLED)
            self.status_bar.config(text="Đang dừng lại...")

    def _on_processing_complete(self, subs: List[Dict[str, Any]], out_file: str):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)

        msg = f"Đã hoàn thành! Đã bóc được {len(subs)} đoạn phụ đề ra file:\n{out_file}"
        messagebox.showinfo("Hoàn tất", msg)

    def _on_processing_error(self, err_msg: str):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        messagebox.showerror("Lỗi xử lý", err_msg)

    def _on_open_folder_clicked(self):
        out_file = self.entry_output.get().strip()
        if out_file and os.path.exists(out_file):
            # Reveal file in Windows Explorer
            subprocess.run(f'explorer /select,"{os.path.abspath(out_file)}"', shell=True)
        elif out_file:
            folder = os.path.dirname(os.path.abspath(out_file))
            if os.path.exists(folder):
                subprocess.run(f'explorer "{folder}"', shell=True)
        else:
            messagebox.showinfo("Thông báo", "Chưa có file phụ đề nào được tạo!")
