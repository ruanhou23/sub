# -*- coding: utf-8 -*-
"""
SUBVIET IMAGE-TO-SRT - Ứng Dụng Nhận Diện Ảnh Phụ Đề Xuất File SRT
Đọc danh sách ảnh đã crop từ thư mục, nhận diện tiếng Việt bằng AI VietOCR và xuất file SRT chuẩn.
"""
import os
import sys
import re
import time
import threading
from datetime import timedelta
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, List, Dict, Any, Tuple
import cv2
import numpy as np
from PIL import Image, ImageTk

# Thiết lập đường dẫn dữ liệu
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(CURRENT_DIR, "data")
SYLLABLES_FILE = os.path.join(DATA_DIR, "vietnamese_syllables.txt")
DEFAULT_IMG_DIR = r"C:\Users\hau\Desktop\New folder\anhsub\output_images"

# Nạp từ điển tiếng Việt
VIETNAMESE_SYLLABLES = set()
EXTRA_WORDS = {
    "doraemon", "nobita", "shizuka", "jaian", "suneo", "dorami", "dekisugi",
    "ok", "bye", "alo", "ừ", "hả", "nhé", "nè", "ha", "ô", "ơ", "a", "u", "ừm", "ơi", "à", "dạ", "vâng",
    "thôi", "nào", "chứ", "đó", "đây", "kia", "rồi", "chưa", "nhỉ", "nhá", "nghe",
    "chú", "bác", "cô", "dì", "anh", "chị", "em", "con", "cháu", "ông", "bà", "mẹ", "ba",
    "tớ", "cậu", "mình", "chúng", "nó", "họ", "ai", "gì", "sao", "đâu", "nào",
    "chuẩn", "bị", "triển", "khai", "dừng", "lại", "tiến", "hành", "khảo", "sát",
    "tọa", "độ", "mục", "tiêu", "khung", "xin", "hết", "bơi", "thích", "đi", "hơn",
    "thiên", "nhiên", "xanh", "mát", "sáng", "thức", "dậy", "tiếng", "chim", "hót",
    "quả", "nhiên", "núi", "vẫn", "nhất", "đúng", "thỉnh", "thoảng", "đổi", "gió",
    "hay", "hòa", "đều", "quyết", "trái", "tim", "vẽ", "nên", "chiếc", "bản", "đồ",
    "thế", "giới", "đong", "đầy", "những", "giấc", "mơ", "riêng"
}

if os.path.exists(SYLLABLES_FILE):
    try:
        with open(SYLLABLES_FILE, "r", encoding="utf-8") as f:
            VIETNAMESE_SYLLABLES = set(l.strip().lower() for l in f if l.strip())
    except Exception:
        pass
VIETNAMESE_SYLLABLES.update(EXTRA_WORDS)

STANDALONE_WORDS = {"hay", "đúng", "khoan", "thôi", "được", "tuyệt", "chuẩn", "chạy", "đi", "a", "hả", "ơi", "ừ", "sao", "gì"}

ENGLISH_HALLUCINATIONS = {
    "contransitionalization", "contractionalized", "contractionalists", "contransitionalists",
    "complicationalists", "interpressionalized", "interrectionalized", "anticulation",
    "contenderation", "contransitionalism"
}

def levenshtein_dist(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_dist(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dele = curr[j] + 1
            sub = prev[j] + (c1 != c2)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]

_diacritic_cache = {}
def correct_vietnamese_diacritics(text: str) -> str:
    if not text: return text
    def replace_word(match):
        word = match.group(0)
        wl = word.lower()
        if len(word) < 3 or wl in VIETNAMESE_SYLLABLES:
            return word
        if wl in _diacritic_cache:
            corr = _diacritic_cache[wl]
        else:
            best, bdist = None, 3
            cands = [s for s in VIETNAMESE_SYLLABLES if abs(len(s) - len(wl)) <= 2 and s[0] == wl[0]]
            for c in cands:
                d = levenshtein_dist(wl, c)
                if d < bdist:
                    bdist, best = d, c
                    if d <= 1: break
            corr = best if (best and bdist <= 2) else wl
            _diacritic_cache[wl] = corr
        if corr == wl: return word
        if word.istitle(): return corr.capitalize()
        if word.isupper(): return corr.upper()
        return corr
    return re.sub(r'[a-zA-ZÀ-ỹ]+', replace_word, text)

def correct_vietnamese_ocr(text: str) -> str:
    if not text: return ""
    text = text.replace('dqùýê†', '').replace('dqùýê', '').replace('†', '')
    text = re.sub(r'\bChuốôn\b', 'Chuẩn', text)
    text = re.sub(r'\bchuốôn\b', 'chuẩn', text)
    text = re.sub(r'\bdừnà\b', 'dừng', text)
    text = re.sub(r'\bVôn(?=\s+còn\b)', 'Vẫn', text)
    text = re.sub(r'\btiền(?=\s+(?:tới|hành)\b)', 'tiến', text)
    text = re.sub(r'\bTiền(?=\s+(?:tới|hành)\b)', 'Tiến', text)
    text = re.sub(r'\bkhỏo sót\b', 'khảo sát', text)
    text = re.sub(r'\btoa đô\b', 'tọa độ', text, flags=re.I)
    text = re.sub(r'\bmúc tiêu\b', 'mục tiêu', text, flags=re.I)
    text = re.sub(r'\btiên tới\b', 'tiến tới', text, flags=re.I)
    text = re.sub(r'\btiên hành\b', 'tiến hành', text, flags=re.I)
    text = re.sub(r'\bThành Xin hết\b', 'Xin hết!', text, flags=re.I)
    text = re.sub(r'\bVăn còn\b', 'Vẫn còn', text, flags=re.I)
    text = re.sub(r'\bđong đẩy\b', 'đong đầy', text, flags=re.I)
    text = re.sub(r'\bgiắc mơ\b', 'giấc mơ', text, flags=re.I)
    text = re.sub(r'\bquện đi\b', 'quên đi', text, flags=re.I)
    text = re.sub(r'\bLiêu rằng\b', 'Liệu rằng', text, flags=re.I)
    text = re.sub(r'\bThình thoảng\b', 'Thỉnh thoảng', text, flags=re.I)
    text = re.sub(r'\bđổi gia\b', 'đổi gió', text, flags=re.I)
    text = re.sub(r'\bChuẩn bi\b', 'Chuẩn bị', text)
    text = re.sub(r'\bCũng đúng nhi\b', 'Cũng đúng nhỉ', text, flags=re.I)
    text = re.sub(r'\bđều rõ\b', 'đều rồi', text, flags=re.I)
    text = re.sub(r'\bChong Chóng Treo\b', 'Chong Chóng Tre', text, flags=re.I)
    text = re.sub(r'\bTUNG MATXA.*$', '', text, flags=re.I)
    return text

def is_valid_line(line: str) -> bool:
    if not line: return False
    raw = line.strip()
    if len(raw) < 2: return False
    lower = raw.lower()
    for hal in ENGLISH_HALLUCINATIONS:
        if hal in lower: return False
    words = re.findall(r'[a-zA-ZÀ-ỹ0-9]+', raw)
    if not words: return False
    for w in words:
        if len(w) >= 8 and re.match(r'^[a-zA-Z]+$', w) and w.lower() not in EXTRA_WORDS:
            return False
    if len(words) >= 3:
        wc = {}
        for w in words:
            wl = w.lower()
            wc[wl] = wc.get(wl, 0) + 1
        if max(wc.values()) >= 3 and (max(wc.values()) / len(words)) >= 0.30:
            return False
        if re.search(r'\b([a-zA-ZÀ-ỹ]+)\s+\1\s+\1\b', raw, flags=re.I):
            return False
    if re.search(r'\b\d{6,}\b', raw) or re.search(r'\bID\s+\d', raw, flags=re.I):
        return False
    vowels = re.compile(r'[aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]', re.I)
    for w in words:
        if re.search(r'[a-zA-ZÀ-ỹ]', w) and not vowels.search(w) and len(words) <= 2:
            return False
    valid_count = sum(1 for w in words if w.lower() in VIETNAMESE_SYLLABLES or w.lower() in STANDALONE_WORDS)
    if len(words) >= 3 and (valid_count / len(words)) < 0.35:
        return False
    return True

def clean_ocr_text(text: str) -> str:
    if not text: return ""
    text = text.replace("\r", "").strip()
    text = re.sub(r'[†‹„®°™]', '', text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) > 4: return ""
    cleaned = []
    for line in lines:
        l = line.strip()
        l = re.sub(r'^[=+<>¬~`_^|\-—_.,;:*#\s⁄ˆ”"“]+', '', l)
        l = re.sub(r'[=+<>¬~`_^|\-—_.,;:*#\s⁄ˆ”"“]+$', '', l)
        l = re.sub(r'[=+<>¬~«»§±²³ø¿`^|*#\\⁄ˆ”"“_;:/\'\[\]{}]+', ' ', l)
        l = re.sub(r'\s+', ' ', l).strip()
        l = correct_vietnamese_ocr(l)
        l = correct_vietnamese_diacritics(l)
        if l and is_valid_line(l):
            cleaned.append(l)
    return "\n".join(cleaned)

def format_timestamp_srt(seconds: float) -> str:
    if seconds < 0: seconds = 0
    td = timedelta(seconds=seconds)
    total_secs = int(td.total_seconds())
    h = total_secs // 3600
    m = (total_secs % 3600) // 60
    s = total_secs % 60
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def parse_time_from_filename(fname: str) -> Optional[float]:
    """Trích xuất mốc thời gian từ tên file (vd: sub_0001_01m24s.png hoặc sub_0001_1h02m14s.png)"""
    # 1. Định dạng: XhYmZs
    m_hms = re.search(r'(\d+)h(\d+)m(\d+)s', fname, flags=re.I)
    if m_hms:
        h, m, s = int(m_hms.group(1)), int(m_hms.group(2)), int(m_hms.group(3))
        return h * 3600.0 + m * 60.0 + s * 1.0

    # 2. Định dạng: XmYs
    m_ms = re.search(r'(\d+)m(\d+)s', fname, flags=re.I)
    if m_ms:
        m, s = int(m_ms.group(1)), int(m_ms.group(2))
        return m * 60.0 + s * 1.0

    # 3. Định dạng: Xs
    m_s = re.search(r'_(\d+)s\.', fname, flags=re.I)
    if m_s:
        return float(m_s.group(1))

    return None

def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

class ImageToSRTApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SubViet - Nhận Diện Ảnh Phụ Đề Xuất File SRT")
        self.root.geometry("1120x800")
        self.root.minsize(920, 680)
        self.root.configure(bg="#1e1e2e")

        self.img_folder: str = ""
        self.image_files: List[str] = []
        self.ocr_results: List[Dict[str, Any]] = []
        self.is_processing = False
        self.worker_thread: Optional[threading.Thread] = None

        self._vietocr_predictor = None
        self._easyocr_reader = None

        self._build_ui()

    def get_vietocr_predictor(self):
        if self._vietocr_predictor is None:
            from vietocr.tool.predictor import Predictor
            from vietocr.tool.config import Cfg
            config = Cfg.load_config_from_name('vgg_transformer')
            config['cnn']['pretrained'] = True
            config['device'] = 'cpu'
            config['predictor']['beamsearch'] = False
            self._vietocr_predictor = Predictor(config)
        return self._vietocr_predictor

    def get_easyocr_reader(self):
        if self._easyocr_reader is None:
            import easyocr
            self._easyocr_reader = easyocr.Reader(["vi"], gpu=False, verbose=False)
        return self._easyocr_reader

    def _build_ui(self):
        # 1. Header
        header = tk.Frame(self.root, bg="#181825", height=50)
        header.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            header,
            text="📑 NHẬN DIỆN ẢNH PHỤ ĐỀ XUẤT FILE SRT (IMAGE-TO-SRT)",
            font=("Segoe UI", 13, "bold"),
            fg="#cdd6f4",
            bg="#181825"
        ).pack(side=tk.LEFT, padx=16, pady=10)

        # 2. Control Panel
        top_panel = tk.Frame(self.root, bg="#1e1e2e")
        top_panel.pack(fill=tk.X, padx=12, pady=6)

        # Hàng 1: Thư mục ảnh
        row1 = tk.Frame(top_panel, bg="#1e1e2e")
        row1.pack(fill=tk.X, pady=4)
        tk.Label(row1, text="Thư mục ảnh crop:", fg="#cdd6f4", bg="#1e1e2e", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.entry_folder = tk.Entry(row1, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief=tk.FLAT)
        self.entry_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, ipady=4)
        default_dir = DEFAULT_IMG_DIR if os.path.exists(DEFAULT_IMG_DIR) else CURRENT_DIR
        self.entry_folder.insert(0, default_dir)

        tk.Button(
            row1,
            text="📂 Chọn thư mục...",
            command=self._browse_folder,
            bg="#89b4fa",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.RIGHT, padx=2)

        tk.Button(
            row1,
            text="🔄 Quét ảnh",
            command=self._scan_images,
            bg="#b4befe",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.RIGHT, padx=4)

        # Hàng 2: Mô hình AI & Xuất SRT
        row2 = tk.Frame(top_panel, bg="#1e1e2e")
        row2.pack(fill=tk.X, pady=4)

        tk.Label(row2, text="Mô hình AI:", fg="#a6adc8", bg="#1e1e2e").pack(side=tk.LEFT)
        self.combo_engine = ttk.Combobox(
            row2,
            values=[
                "🇻🇳 VietOCR (Transformer - Chuẩn dấu 100%)",
                "🤖 EasyOCR (AI Deep Learning)",
                "⚡ Tesseract OCR (Nhanh & nhẹ)"
            ],
            state="readonly",
            width=32
        )
        self.combo_engine.current(0)
        self.combo_engine.pack(side=tk.LEFT, padx=6)

        self.btn_export = tk.Button(
            row2,
            text="💾 XUẤT FILE SRT...",
            command=self._export_srt,
            bg="#a6e3a1",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_export.pack(side=tk.RIGHT, padx=4)

        self.btn_start = tk.Button(
            row2,
            text="🚀 BẮT ĐẦU NHẬN DIỆN",
            command=self._start_ocr,
            bg="#f9e2af",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_start.pack(side=tk.RIGHT, padx=4)

        self.btn_stop = tk.Button(
            row2,
            text="⏹ Dừng",
            command=self._stop_ocr,
            bg="#f38ba8",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.btn_stop.pack(side=tk.RIGHT, padx=4)

        # 3. Content: Split Table & Image Preview
        main_split = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#1e1e2e", sashwidth=4)
        main_split.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        # Bảng Treeview
        table_frame = tk.Frame(main_split, bg="#181825")
        main_split.add(table_frame, minsize=550, stretch="always")

        columns = ("stt", "file", "time", "text")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("stt", text="#")
        self.tree.heading("file", text="Tên file ảnh")
        self.tree.heading("time", text="Mốc thời gian (SRT)")
        self.tree.heading("text", text="Nội dung phụ đề tiếng Việt (Nhấp đúp để sửa)")

        self.tree.column("stt", width=45, anchor=tk.CENTER)
        self.tree.column("file", width=160, anchor=tk.W)
        self.tree.column("time", width=180, anchor=tk.CENTER)
        self.tree.column("text", width=360, anchor=tk.W)

        scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # Cột phải: Preview ảnh phóng to và chi tiết
        preview_frame = tk.Frame(main_split, bg="#181825", width=340)
        main_split.add(preview_frame, minsize=280, stretch="never")

        tk.Label(preview_frame, text="Ảnh phụ đề đang chọn:", fg="#cdd6f4", bg="#181825", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=10, pady=6)
        
        self.lbl_preview_img = tk.Label(preview_frame, text="Chọn dòng để xem ảnh", fg="#6c7086", bg="#11111b")
        self.lbl_preview_img.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Text Editor box cho dòng đang chọn
        tk.Label(preview_frame, text="Chỉnh sửa nội dung phụ đề:", fg="#cdd6f4", bg="#181825", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=10, pady=4)
        self.txt_edit = tk.Text(preview_frame, height=4, bg="#313244", fg="#cdd6f4", font=("Segoe UI", 10), insertbackground="#cdd6f4", relief=tk.FLAT)
        self.txt_edit.pack(fill=tk.X, padx=8, pady=4)

        btn_save_edit = tk.Button(
            preview_frame,
            text="✔️ Áp dụng sửa dòng này",
            command=self._apply_text_edit,
            bg="#89b4fa",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        )
        btn_save_edit.pack(fill=tk.X, padx=8, pady=4)

        # 4. Footer & Progress Bar
        footer = tk.Frame(self.root, bg="#11111b", height=36)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.progress_bar = ttk.Progressbar(footer, mode="determinate")
        self.progress_bar.pack(fill=tk.X, side=tk.TOP)

        self.lbl_status = tk.Label(footer, text="Sẵn sàng.", fg="#a6adc8", bg="#11111b", font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.LEFT, padx=12, pady=4)

        self.lbl_count = tk.Label(footer, text="Ảnh tìm thấy: 0", fg="#a6e3a1", bg="#11111b", font=("Segoe UI", 9, "bold"))
        self.lbl_count.pack(side=tk.RIGHT, padx=12, pady=4)

        # Tự động quét ban đầu
        self.root.after(300, self._scan_images)

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục chứa ảnh phụ đề")
        if folder:
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)
            self._scan_images()

    def _scan_images(self):
        folder = self.entry_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            return
        self.img_folder = folder
        exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        all_files = [f for f in os.listdir(folder) if f.lower().endswith(exts) and not f.lower().endswith('_bw.png')]
        self.image_files = sorted(all_files, key=natural_sort_key)

        self.tree.delete(*self.tree.get_children())
        self.ocr_results.clear()

        # Tạo danh sách sơ bộ
        prev_time = 0.0
        for idx, fname in enumerate(self.image_files, 1):
            t_start = parse_time_from_filename(fname)
            if t_start is None:
                t_start = prev_time + 2.5
            t_end = t_start + 2.5
            prev_time = t_start

            item_data = {
                "stt": idx,
                "file": fname,
                "start": t_start,
                "end": t_end,
                "text": ""
            }
            self.ocr_results.append(item_data)

            time_str = f"{format_timestamp_srt(t_start)} --> {format_timestamp_srt(t_end)}"
            self.tree.insert("", tk.END, iid=str(idx), values=(idx, fname, time_str, "(Chưa nhận diện)"))

        # Tinh chỉnh lại t_end dựa theo t_start của câu tiếp theo
        for i in range(len(self.ocr_results) - 1):
            cur = self.ocr_results[i]
            nxt = self.ocr_results[i + 1]
            if nxt["start"] > cur["start"]:
                cur["end"] = min(cur["start"] + 4.0, nxt["start"])
            time_str = f"{format_timestamp_srt(cur['start'])} --> {format_timestamp_srt(cur['end'])}"
            self.tree.set(str(cur["stt"]), "time", time_str)

        self.lbl_count.config(text=f"Ảnh tìm thấy: {len(self.image_files)}")
        self.lbl_status.config(text=f"Đã nạp {len(self.image_files)} ảnh từ thư mục. Bấm 'Bắt đầu nhận diện' để chạy.")

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        iid = sel[0]
        idx = int(iid) - 1
        if 0 <= idx < len(self.ocr_results):
            data = self.ocr_results[idx]
            fname = data["file"]
            img_path = os.path.join(self.img_folder, fname)
            if os.path.exists(img_path):
                img_bgr = cv2.imread(img_path)
                if img_bgr is not None:
                    h, w = img_bgr.shape[:2]
                    scale = min(320 / w, 200 / h, 1.5)
                    nw = max(1, int(w * scale))
                    nh = max(1, int(h * scale))
                    resized = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)
                    tk_img = ImageTk.PhotoImage(pil_img)
                    self.lbl_preview_img.config(image=tk_img, text="")
                    self.lbl_preview_img.image = tk_img

            self.txt_edit.delete("1.0", tk.END)
            self.txt_edit.insert("1.0", data["text"])

    def _apply_text_edit(self):
        sel = self.tree.selection()
        if not sel: return
        iid = sel[0]
        idx = int(iid) - 1
        if 0 <= idx < len(self.ocr_results):
            new_text = self.txt_edit.get("1.0", tk.END).strip()
            self.ocr_results[idx]["text"] = new_text
            self.tree.set(iid, "text", new_text)

    def _on_tree_double_click(self, event):
        self.txt_edit.focus_set()

    def _start_ocr(self):
        if not self.image_files:
            messagebox.showwarning("Trống", "Không tìm thấy ảnh nào trong thư mục!")
            return

        self.is_processing = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        engine = self.combo_engine.get()

        self.worker_thread = threading.Thread(target=self._ocr_worker, args=(engine,), daemon=True)
        self.worker_thread.start()

    def _stop_ocr(self):
        self.is_processing = False
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text="Đang dừng...")

    def _ocr_worker(self, engine_sel: str):
        is_vietocr = "VietOCR" in engine_sel
        is_easyocr = "EasyOCR" in engine_sel
        predictor = None
        reader = None

        if is_vietocr:
            try:
                self.root.after(0, lambda: self.lbl_status.config(text="Đang nạp mô hình VietOCR..."))
                predictor = self.get_vietocr_predictor()
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Lỗi", f"Không thể nạp VietOCR:\n{e}"))
                self.root.after(0, self._on_finish_ocr)
                return
        elif is_easyocr:
            try:
                self.root.after(0, lambda: self.lbl_status.config(text="Đang nạp mô hình EasyOCR..."))
                reader = self.get_easyocr_reader()
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Lỗi", f"Không thể nạp EasyOCR:\n{e}"))
                self.root.after(0, self._on_finish_ocr)
                return

        total = len(self.ocr_results)
        for i, item in enumerate(self.ocr_results):
            if not self.is_processing: break
            fname = item["file"]
            img_path = os.path.join(self.img_folder, fname)
            if not os.path.exists(img_path): continue

            img = cv2.imread(img_path)
            if img is None or img.size == 0: continue

            raw_text = ""
            if is_vietocr and predictor:
                # Phóng to và tiền xử lý
                up = cv2.resize(img, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
                gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
                # Tách dòng text
                lines = self._segment_lines(gray)
                line_texts = []
                for l_img in lines:
                    inv = cv2.bitwise_not(l_img) if len(l_img.shape) == 2 else l_img
                    pil_im = Image.fromarray(inv)
                    t = predictor.predict(pil_im).strip()
                    if t and len(t) >= 2:
                        line_texts.append(t)
                raw_text = "\n".join(line_texts)
            elif is_easyocr and reader:
                res = reader.readtext(img, detail=0)
                raw_text = " ".join([r.strip() for r in res if len(r.strip()) > 1])
            else:
                import pytesseract
                up = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                raw_text = pytesseract.image_to_string(up, lang="vie", config="--psm 6")

            # Hậu xử lý làm sạch văn bản
            cleaned = clean_ocr_text(raw_text)
            item["text"] = cleaned

            # Cập nhật GUI
            pct = ((i + 1) / total) * 100
            self._update_row(item["stt"], cleaned, pct, i + 1, total)

        self.root.after(0, self._on_finish_ocr)

    def _segment_lines(self, gray_img: np.ndarray) -> List[np.ndarray]:
        _, thresh = cv2.threshold(gray_img, 175, 255, cv2.THRESH_BINARY)
        h, w = thresh.shape[:2]
        row_sums = np.sum(thresh > 0, axis=1)
        in_text = row_sums > max(3, int(w * 0.010))

        lines = []
        start = None
        for i in range(h):
            if in_text[i] and start is None:
                start = i
            elif not in_text[i] and start is not None:
                if 14 <= (i - start) <= 220:
                    y1 = max(0, start - 5)
                    y2 = min(h, i + 5)
                    line_crop = thresh[y1:y2, :]
                    col_sums = np.sum(line_crop > 0, axis=0)
                    cols = np.where(col_sums > 0)[0]
                    if len(cols) > 0:
                        x1 = max(0, cols[0] - 10)
                        x2 = min(w, cols[-1] + 11)
                        if (x2 - x1) >= 25 and cv2.countNonZero(line_crop[:, x1:x2]) >= 30:
                            lines.append(line_crop[:, x1:x2])
                start = None

        if start is not None and 14 <= (h - start) <= 220:
            y1 = max(0, start - 5)
            line_crop = thresh[y1:h, :]
            col_sums = np.sum(line_crop > 0, axis=0)
            cols = np.where(col_sums > 0)[0]
            if len(cols) > 0:
                x1 = max(0, cols[0] - 10)
                x2 = min(w, cols[-1] + 11)
                if (x2 - x1) >= 25 and cv2.countNonZero(line_crop[:, x1:x2]) >= 30:
                    lines.append(line_crop[:, x1:x2])

        if not lines:
            lines = [thresh]
        return lines

    def _update_row(self, stt: int, text: str, pct: float, cur: int, total: int):
        def do_update():
            display_text = text if text else "(Trống / Nhiễu đã lọc)"
            self.tree.set(str(stt), "text", display_text)
            self.progress_bar['value'] = pct
            self.lbl_status.config(text=f"Đang nhận diện: {cur}/{total} ảnh ({pct:.1f}%)")
        self.root.after(0, do_update)

    def _on_finish_ocr(self):
        self.is_processing = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.progress_bar['value'] = 100
        valid_subs = sum(1 for item in self.ocr_results if item["text"].strip())
        self.lbl_status.config(text=f"Hoàn tất! Đã trích xuất được {valid_subs} câu phụ đề hợp lệ.")
        messagebox.showinfo("Hoàn tất", f"Đã nhận diện xong toàn bộ danh sách ảnh!\nThu được {valid_subs} câu phụ đề hợp lệ.\nBấm 'Xuất file SRT' để lưu file.")

    def _export_srt(self):
        valid_items = [it for it in self.ocr_results if it["text"].strip()]
        if not valid_items:
            messagebox.showwarning("Trống", "Chưa có nội dung phụ đề nào được nhận diện!")
            return

        filepath = filedialog.asksaveasfilename(
            title="Lưu file phụ đề SRT",
            defaultextension=".srt",
            filetypes=[("SRT Subtitle", "*.srt"), ("WebVTT Subtitle", "*.vtt")]
        )
        if not filepath: return

        is_vtt = filepath.lower().endswith(".vtt")
        with open(filepath, "w", encoding="utf-8") as f:
            if is_vtt:
                f.write("WEBVTT\n\n")

            idx = 1
            for item in valid_items:
                text = item["text"].strip()
                start_str = format_timestamp_srt(item["start"]).replace(",", ".") if is_vtt else format_timestamp_srt(item["start"])
                end_str = format_timestamp_srt(item["end"]).replace(",", ".") if is_vtt else format_timestamp_srt(item["end"])

                if not is_vtt:
                    f.write(f"{idx}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{text}\n\n")
                idx += 1

        messagebox.showinfo("Thành công", f"Đã xuất thành công {idx - 1} câu phụ đề vào file:\n{filepath}")

def main():
    root = tk.Tk()
    app = ImageToSRTApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()