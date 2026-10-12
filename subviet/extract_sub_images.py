# -*- coding: utf-8 -*-
"""
SubViet - Ứng dụng trích xuất ảnh phụ đề video độc lập
Cho phép kéo ô vuông chọn vùng phụ đề và tự động lưu danh sách ảnh vào thư mục chỉ định.
"""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageTk

# Đảm bảo đường dẫn import
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ui.preview_widget import PreviewWidget

DEFAULT_OUTPUT_DIR = r"C:\Users\hau\Desktop\New folder\anhsub"

def format_time_str(seconds: float) -> str:
    secs = int(seconds)
    mins = secs // 60
    rem_secs = secs % 60
    hours = mins // 60
    rem_mins = mins % 60
    if hours > 0:
        return f"{hours:02d}h{rem_mins:02d}m{rem_secs:02d}s"
    return f"{rem_mins:02d}m{rem_secs:02d}s"

class SubImageExtractorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SubViet - Trích Xuất Ảnh Phụ Đề Video (Image Cropper)")
        self.root.geometry("1100x820")
        self.root.minsize(900, 700)
        self.root.configure(bg="#1e1e2e")

        # Trạng thái
        self.video_path: Optional[str] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.total_frames = 0
        self.fps = 25.0
        self.duration_sec = 0.0
        self.video_w = 0
        self.video_h = 0
        self.is_running = False
        self.is_paused = False
        self.worker_thread: Optional[threading.Thread] = None

        # Thiết lập thư mục mặc định
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)

        self._build_ui()

    def _build_ui(self):
        # 1. Header
        header = tk.Frame(self.root, bg="#181825", height=50)
        header.pack(fill=tk.X, side=tk.TOP)
        
        tk.Label(
            header,
            text="📸 TRÍCH XUẤT ẢNH PHỤ ĐỀ VIDEO (SUBTITLE CROPPER)",
            font=("Segoe UI", 13, "bold"),
            fg="#cdd6f4",
            bg="#181825"
        ).pack(side=tk.LEFT, padx=16, pady=10)

        tk.Label(
            header,
            text="Kéo ô vuông chọn vùng sub và tự động lưu danh sách ảnh",
            font=("Segoe UI", 9, "italic"),
            fg="#a6adc8",
            bg="#181825"
        ).pack(side=tk.LEFT, padx=5, pady=10)

        # 2. Main Content
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#1e1e2e", sashwidth=4)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Cột trái: Khung xem trước video và kéo ô chọn
        left_frame = tk.Frame(main_paned, bg="#181825", bd=1, relief=tk.SOLID)
        main_paned.add(left_frame, minsize=550, stretch="always")

        # Thanh chọn nguồn video
        src_box = tk.Frame(left_frame, bg="#181825")
        src_box.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(src_box, text="Video nguồn:", fg="#cdd6f4", bg="#181825", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.entry_src = tk.Entry(src_box, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief=tk.FLAT)
        self.entry_src.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, ipady=4)

        btn_browse = tk.Button(
            src_box,
            text="📂 Chọn File...",
            command=self._browse_video,
            bg="#89b4fa",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=8,
            cursor="hand2"
        )
        btn_browse.pack(side=tk.RIGHT)

        # Widget xem trước có ô vuông kéo thả
        self.preview_widget = PreviewWidget(left_frame, bg_color="#11111b")
        self.preview_widget.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Thanh điều hướng tua thời gian (Seek Bar)
        seek_box = tk.Frame(left_frame, bg="#181825")
        seek_box.pack(fill=tk.X, padx=10, pady=4)

        tk.Label(seek_box, text="Tua đến frame:", fg="#a6adc8", bg="#181825", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.scale_seek = ttk.Scale(seek_box, from_=0, to=100, orient=tk.HORIZONTAL, command=self._on_seek_change)
        self.scale_seek.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.lbl_seek_time = tk.Label(seek_box, text="00m00s / 00m00s", fg="#a6adc8", bg="#181825", font=("Segoe UI", 9))
        self.lbl_seek_time.pack(side=tk.RIGHT)

        # Các nút preset vùng chọn
        preset_box = tk.Frame(left_frame, bg="#181825")
        preset_box.pack(fill=tk.X, padx=10, pady=6)

        tk.Label(preset_box, text="Vị trí mẫu:", fg="#a6adc8", bg="#181825").pack(side=tk.LEFT)
        tk.Button(
            preset_box,
            text="📐 Đáy chuẩn (18%)",
            command=lambda: self.preview_widget.reset_to_bottom(0.18),
            bg="#313244",
            fg="#cdd6f4",
            relief=tk.FLAT,
            padx=6,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            preset_box,
            text="📐 Đáy nhỏ (12%)",
            command=lambda: self.preview_widget.reset_to_bottom(0.12),
            bg="#313244",
            fg="#cdd6f4",
            relief=tk.FLAT,
            padx=4,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            preset_box,
            text="🔲 Toàn màn hình",
            command=self.preview_widget.reset_to_full,
            bg="#313244",
            fg="#cdd6f4",
            relief=tk.FLAT,
            padx=6,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=4)

        # Cột phải: Cài đặt, điều khiển và danh sách ảnh vừa cắt
        right_frame = tk.Frame(main_paned, bg="#181825", bd=1, relief=tk.SOLID, width=380)
        main_paned.add(right_frame, minsize=320, stretch="never")

        # Thư mục lưu ảnh
        out_box = tk.LabelFrame(right_frame, text="Thư mục lưu ảnh phụ đề", bg="#181825", fg="#cdd6f4", font=("Segoe UI", 9, "bold"))
        out_box.pack(fill=tk.X, padx=10, pady=8)

        self.entry_out = tk.Entry(out_box, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", relief=tk.FLAT)
        self.entry_out.pack(fill=tk.X, padx=6, pady=4, ipady=3)
        self.entry_out.insert(0, DEFAULT_OUTPUT_DIR)

        out_btn_row = tk.Frame(out_box, bg="#181825")
        out_btn_row.pack(fill=tk.X, padx=6, pady=4)

        tk.Button(
            out_btn_row,
            text="📂 Đổi thư mục...",
            command=self._browse_output_dir,
            bg="#45475a",
            fg="#cdd6f4",
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.LEFT)

        tk.Button(
            out_btn_row,
            text="🔍 Mở thư mục ảnh",
            command=self._open_output_dir,
            bg="#a6e3a1",
            fg="#11111b",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        ).pack(side=tk.RIGHT)

        # Cài đặt trích xuất
        cfg_box = tk.LabelFrame(right_frame, text="Cài đặt trích xuất thông minh", bg="#181825", fg="#cdd6f4", font=("Segoe UI", 9, "bold"))
        cfg_box.pack(fill=tk.X, padx=10, pady=8)

        # Tốc độ lấy mẫu
        fps_row = tk.Frame(cfg_box, bg="#181825")
        fps_row.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(fps_row, text="Tần số quét:", fg="#a6adc8", bg="#181825").pack(side=tk.LEFT)
        self.combo_sample = ttk.Combobox(
            fps_row,
            values=["2.0 frame/giây (Khuyên dùng)", "1.0 frame/giây (Nhanh)", "3.0 frame/giây (Đầy đủ)", "0.5 frame/giây (Siêu tốc)"],
            state="readonly",
            width=24
        )
        self.combo_sample.current(0)
        self.combo_sample.pack(side=tk.RIGHT)

        # Độ nhạy phát hiện câu mới
        sens_row = tk.Frame(cfg_box, bg="#181825")
        sens_row.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(sens_row, text="Độ nhạy đổi sub:", fg="#a6adc8", bg="#181825").pack(side=tk.LEFT)
        self.combo_sens = ttk.Combobox(
            sens_row,
            values=["Trung bình (Ngưỡng 4.5)", "Cao - Dễ nhận sub mới (Ngưỡng 3.5)", "Thấp - Chống lặp tốt (Ngưỡng 6.0)"],
            state="readonly",
            width=24
        )
        self.combo_sens.current(0)
        self.combo_sens.pack(side=tk.RIGHT)

        # Tùy chọn checkbox
        self.var_skip_empty = tk.BooleanVar(value=True)
        tk.Checkbutton(
            cfg_box,
            text="Tự động bỏ qua khung hình trống / không có chữ",
            variable=self.var_skip_empty,
            fg="#cdd6f4",
            bg="#181825",
            selectcolor="#313244",
            activebackground="#181825",
            activeforeground="#cdd6f4"
        ).pack(anchor=tk.W, padx=6, pady=2)

        self.var_save_binary = tk.BooleanVar(value=False)
        tk.Checkbutton(
            cfg_box,
            text="Lưu kèm ảnh nhị phân đã làm sạch nét chữ (b/w)",
            variable=self.var_save_binary,
            fg="#cdd6f4",
            bg="#181825",
            selectcolor="#313244",
            activebackground="#181825",
            activeforeground="#cdd6f4"
        ).pack(anchor=tk.W, padx=6, pady=2)

        # Khung xem trước ảnh vừa cắt
        recent_box = tk.LabelFrame(right_frame, text="Ảnh phụ đề vừa cắt gần nhất", bg="#181825", fg="#cdd6f4", font=("Segoe UI", 9, "bold"))
        recent_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self.lbl_thumb = tk.Label(recent_box, text="Chưa có ảnh nào được trích xuất", fg="#6c7086", bg="#11111b")
        self.lbl_thumb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.lbl_thumb_info = tk.Label(recent_box, text="", fg="#fab387", bg="#181825", font=("Segoe UI", 9, "bold"))
        self.lbl_thumb_info.pack(fill=tk.X, padx=6, pady=2)

        # Nút điều khiển
        ctrl_box = tk.Frame(right_frame, bg="#181825")
        ctrl_box.pack(fill=tk.X, padx=10, pady=8)

        self.btn_start = tk.Button(
            ctrl_box,
            text="🚀 BẮT ĐẦU TRÍCH XUẤT ẢNH",
            command=self._start_extract,
            bg="#a6e3a1",
            fg="#11111b",
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.btn_start.pack(fill=tk.X, pady=3, ipady=6)

        self.btn_stop = tk.Button(
            ctrl_box,
            text="⏹ DỪNG LẠI",
            command=self._stop_extract,
            bg="#f38ba8",
            fg="#11111b",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.btn_stop.pack(fill=tk.X, pady=3)

        # 3. Footer / Progress bar
        footer = tk.Frame(self.root, bg="#11111b", height=36)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.progress_bar = ttk.Progressbar(footer, mode="determinate")
        self.progress_bar.pack(fill=tk.X, side=tk.TOP)

        self.lbl_status = tk.Label(
            footer,
            text="Sẵn sàng. Vui lòng chọn file video để bắt đầu.",
            fg="#a6adc8",
            bg="#11111b",
            font=("Segoe UI", 9)
        )
        self.lbl_status.pack(side=tk.LEFT, padx=10, pady=4)

        self.lbl_count = tk.Label(
            footer,
            text="Đã lưu: 0 ảnh",
            fg="#a6e3a1",
            bg="#11111b",
            font=("Segoe UI", 9, "bold")
        )
        self.lbl_count.pack(side=tk.RIGHT, padx=10, pady=4)

    def _browse_video(self):
        filepath = filedialog.askopenfilename(
            title="Chọn video để trích xuất phụ đề",
            filetypes=[
                ("Video Files", "*.mp4 *.mkv *.avi *.ts *.webm *.mov *.flv *.m4v"),
                ("All Files", "*.*")
            ]
        )
        if filepath:
            self.entry_src.delete(0, tk.END)
            self.entry_src.insert(0, filepath)
            self._load_video(filepath)

    def _load_video(self, path: str):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            messagebox.showerror("Lỗi", f"Không thể mở video:\\n{path}")
            return

        self.video_path = path
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.duration_sec = self.total_frames / self.fps if self.fps > 0 else 0
        self.video_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Hiển thị frame đầu tiên
        self._seek_and_show(0)

        dur_str = format_time_str(self.duration_sec)
        self.lbl_status.config(
            text=f"Đã nạp video: {self.video_w}x{self.video_h} | {self.fps:.1f} FPS | Thời lượng: {dur_str}"
        )
        self.scale_seek.config(to=max(1, self.total_frames - 1))
        self.scale_seek.set(0)

    def _on_seek_change(self, val):
        frame_idx = int(float(val))
        self._seek_and_show(frame_idx)

    def _seek_and_show(self, frame_idx: int):
        if not self.cap or not self.cap.isOpened():
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        if ret:
            self.preview_widget.set_frame(frame)
            cur_sec = frame_idx / self.fps if self.fps > 0 else 0
            self.lbl_seek_time.config(
                text=f"{format_time_str(cur_sec)} / {format_time_str(self.duration_sec)}"
            )

    def _browse_output_dir(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu ảnh phụ đề")
        if folder:
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, folder)

    def _open_output_dir(self):
        out_dir = self.entry_out.get().strip()
        if not out_dir:
            out_dir = DEFAULT_OUTPUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        try:
            os.startfile(out_dir)
        except Exception as e:
            messagebox.showinfo("Thư mục", f"Đường dẫn:\\n{out_dir}")

    def _start_extract(self):
        src = self.entry_src.get().strip()
        out_dir = self.entry_out.get().strip()
        if not src:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn file video!")
            return
        if not out_dir:
            out_dir = DEFAULT_OUTPUT_DIR
            self.entry_out.insert(0, out_dir)

        os.makedirs(out_dir, exist_ok=True)

        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

        # Lấy tham số
        crop_box = self.preview_widget.get_crop_box()
        sample_str = self.combo_sample.get()
        sample_fps = 2.0
        if "1.0" in sample_str:
            sample_fps = 1.0
        elif "3.0" in sample_str:
            sample_fps = 3.0
        elif "0.5" in sample_str:
            sample_fps = 0.5

        sens_str = self.combo_sens.get()
        diff_threshold = 4.5
        if "3.5" in sens_str:
            diff_threshold = 3.5
        elif "6.0" in sens_str:
            diff_threshold = 6.0

        skip_empty = self.var_skip_empty.get()
        save_binary = self.var_save_binary.get()

        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(src, out_dir, crop_box, sample_fps, diff_threshold, skip_empty, save_binary),
            daemon=True
        )
        self.worker_thread.start()

    def _stop_extract(self):
        self.is_running = False
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text="Đang dừng tiến trình...")

    def _worker_loop(
        self,
        video_path: str,
        out_dir: str,
        crop_box: Tuple[float, float, float, float],
        sample_fps: float,
        diff_threshold: float,
        skip_empty: bool,
        save_binary: bool
    ):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.root.after(0, lambda: messagebox.showerror("Lỗi", "Không thể đọc video!"))
            self.root.after(0, self._on_finish)
            return

        total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step_frames = max(1, int(round(orig_fps / sample_fps)))
        v_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        v_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Tọa độ pixel crop
        x1_ratio, y1_ratio, x2_ratio, y2_ratio = crop_box
        px1 = max(0, min(v_w - 1, int(x1_ratio * v_w)))
        py1 = max(0, min(v_h - 1, int(y1_ratio * v_h)))
        px2 = max(px1 + 10, min(v_w, int(x2_ratio * v_w)))
        py2 = max(py1 + 10, min(v_h, int(y2_ratio * v_h)))

        last_fingerprint: Optional[np.ndarray] = None
        saved_count = 0
        cur_frame_idx = 0

        while self.is_running and cur_frame_idx < total_f:
            cap.set(cv2.CAP_PROP_POS_FRAMES, cur_frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            cur_sec = cur_frame_idx / orig_fps if orig_fps > 0 else 0.0

            # Cắt vùng phụ đề đã chọn
            crop = frame[py1:py2, px1:px2]
            if crop.size == 0:
                cur_frame_idx += step_frames
                continue

            # Tạo fingerprint thu nhỏ để so sánh
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            down = cv2.resize(gray, (160, 40), interpolation=cv2.INTER_AREA)
            blurred = cv2.GaussianBlur(down, (5, 5), 0)

            # Kiểm tra xem có chữ không (nếu bật skip_empty)
            has_content = True
            bin_img = None
            if skip_empty:
                # Phóng to và lọc nhị phân màu sáng (chữ thường màu trắng hoặc vàng)
                _, thresh = cv2.threshold(gray, 175, 255, cv2.THRESH_BINARY)
                white_count = cv2.countNonZero(thresh)
                density = white_count / thresh.size
                # Nếu quá tối (< 0.08%) hoặc quá sáng (> 45%) -> không có phụ đề
                if density < 0.0008 or density > 0.45:
                    has_content = False
                bin_img = thresh

            if has_content:
                # Kiểm tra khác biệt với câu sub trước
                is_new_sub = False
                if last_fingerprint is None:
                    is_new_sub = True
                else:
                    diff = cv2.absdiff(blurred, last_fingerprint)
                    mean_diff = float(np.mean(diff))
                    if mean_diff >= diff_threshold:
                        is_new_sub = True

                if is_new_sub:
                    saved_count += 1
                    time_tag = format_time_str(cur_sec)
                    filename = f"sub_{saved_count:04d}_{time_tag}.png"
                    filepath = os.path.join(out_dir, filename)

                    # Lưu ảnh crop gốc
                    cv2.imwrite(filepath, crop)

                    # Nếu người dùng muốn lưu kèm ảnh nhị phân
                    if save_binary and bin_img is not None:
                        bin_filename = f"sub_{saved_count:04d}_{time_tag}_bw.png"
                        cv2.imwrite(os.path.join(out_dir, bin_filename), bin_img)

                    last_fingerprint = blurred

                    # Cập nhật giao diện thumbnail
                    self._update_thumbnail(crop, filename, saved_count)

            # Cập nhật tiến độ
            pct = (cur_frame_idx / total_f) * 100 if total_f > 0 else 0
            self._update_progress(pct, cur_sec, saved_count)

            cur_frame_idx += step_frames

        cap.release()
        self.root.after(0, lambda: self._on_finish(saved_count, out_dir))

    def _update_thumbnail(self, crop_bgr: np.ndarray, filename: str, count: int):
        h, w = crop_bgr.shape[:2]
        max_w = 340
        max_h = 140
        scale = min(max_w / w, max_h / h, 1.0)
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))

        thumb = cv2.resize(crop_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        thumb_rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(thumb_rgb)

        def do_update():
            tk_img = ImageTk.PhotoImage(pil_img)
            self.lbl_thumb.config(image=tk_img, text="")
            self.lbl_thumb.image = tk_img
            self.lbl_thumb_info.config(text=f"Ảnh #{count:04d}: {filename}")

        self.root.after(0, do_update)

    def _update_progress(self, percent: float, cur_sec: float, saved_count: int):
        def do_update():
            self.progress_bar['value'] = percent
            self.lbl_status.config(
                text=f"Đang trích xuất: {percent:.1f}% | Thời gian: {format_time_str(cur_sec)}"
            )
            self.lbl_count.config(text=f"Đã lưu: {saved_count} ảnh")
        self.root.after(0, do_update)

    def _on_finish(self, count: int = 0, out_dir: str = ""):
        self.is_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.progress_bar['value'] = 100
        self.lbl_status.config(text=f"Hoàn tất! Đã lưu thành công {count} ảnh phụ đề.")
        
        resp = messagebox.askyesno(
            "Hoàn tất trích xuất ảnh",
            f"Đã trích xuất thành công {count} ảnh phụ đề vào thư mục:\\n{out_dir}\\n\\nBạn có muốn mở thư mục ảnh ngay bây giờ không?"
        )
        if resp:
            self._open_output_dir()

def main():
    root = tk.Tk()
    app = SubImageExtractorApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()