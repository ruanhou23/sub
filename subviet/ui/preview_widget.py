import tkinter as tk
from typing import Optional, Tuple, Callable, Dict
import cv2
import numpy as np
from PIL import Image, ImageTk

class PreviewWidget(tk.Frame):
    """
    Widget hiển thị khung hình xem trước của video và cho phép người dùng
    dùng chuột kéo ô vuông (bounding box), co giãn các góc/cạnh hoặc di chuyển
    vùng nhận diện phụ đề một cách trực quan, mượt mà.
    """
    HANDLE_RADIUS = 4       # Bán kính điểm neo (pixel)
    MIN_BOX_PX = 15         # Kích thước tối thiểu của ô chọn (pixel)

    def __init__(self, master, bg_color="#181825", on_crop_change: Optional[Callable[[Tuple[float, float, float, float]], None]] = None, **kwargs):
        super().__init__(master, bg=bg_color, **kwargs)
        self.bg_color = bg_color
        self.on_crop_change = on_crop_change

        self.current_frame: Optional[np.ndarray] = None
        # Vùng chọn chuẩn hóa: [x1, y1, x2, y2] với giá trị từ 0.0 đến 1.0
        # Mặc định: dải đáy 18% (y từ 0.82 đến 1.0)
        self.crop_box: list = [0.0, 0.82, 1.0, 1.0]
        self.tk_image = None

        # Thông số hình ảnh hiển thị trên canvas
        self._img_w = 0
        self._img_h = 0
        self._offset_x = 0
        self._offset_y = 0
        self._new_w = 0
        self._new_h = 0

        # Trạng thái tương tác chuột
        self._drag_mode: Optional[str] = None
        self._drag_start_mouse = (0, 0)
        self._drag_start_box = [0.0, 0.82, 1.0, 1.0]

        self.canvas = tk.Canvas(
            self,
            bg="#11111b",
            highlightthickness=1,
            highlightbackground="#313244",
            cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Gán các sự kiện chuột
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Motion>", self._on_mouse_move)

    def set_frame(self, frame_bgr: Optional[np.ndarray]):
        self.current_frame = frame_bgr
        self._redraw_full()

    def set_crop_box(self, x1: float, y1: float, x2: float, y2: float):
        """Đặt vùng chọn phụ đề theo tỉ lệ chuẩn hóa [0..1]"""
        nx1 = max(0.0, min(1.0, min(x1, x2)))
        ny1 = max(0.0, min(1.0, min(y1, y2)))
        nx2 = max(0.0, min(1.0, max(x1, x2)))
        ny2 = max(0.0, min(1.0, max(y1, y2)))

        # Đảm bảo không quá nhỏ
        if nx2 - nx1 < 0.02:
            nx2 = min(1.0, nx1 + 0.05)
        if ny2 - ny1 < 0.02:
            ny2 = min(1.0, ny1 + 0.05)

        self.crop_box = [nx1, ny1, nx2, ny2]
        self._redraw_overlay()
        if self.on_crop_change:
            self.on_crop_change(tuple(self.crop_box))

    def get_crop_box(self) -> Tuple[float, float, float, float]:
        """Trả về tọa độ (x1, y1, x2, y2) chuẩn hóa [0..1]"""
        return (self.crop_box[0], self.crop_box[1], self.crop_box[2], self.crop_box[3])

    def set_crop_ratio(self, ratio: float):
        """Đặt vùng chọn dải đáy theo tỉ lệ (VD: 0.18 -> đáy 18%)"""
        r = max(0.05, min(0.60, ratio))
        self.set_crop_box(0.0, 1.0 - r, 1.0, 1.0)

    def reset_to_bottom(self, ratio: float = 0.18):
        """Khôi phục vùng chọn đáy mặc định"""
        self.set_crop_ratio(ratio)

    def reset_to_full(self):
        """Chọn toàn bộ khung hình"""
        self.set_crop_box(0.0, 0.0, 1.0, 1.0)

    def _on_resize(self, event):
        self._redraw_full()

    # --- CHUYỂN ĐỔI TỌA ĐỘ ---
    def _canvas_to_normalized(self, cx: int, cy: int) -> Tuple[float, float]:
        if self._new_w <= 0 or self._new_h <= 0:
            return 0.0, 0.0
        nx = (cx - self._offset_x) / self._new_w
        ny = (cy - self._offset_y) / self._new_h
        return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))

    def _normalized_to_canvas(self, nx: float, ny: float) -> Tuple[int, int]:
        cx = self._offset_x + int(nx * self._new_w)
        cy = self._offset_y + int(ny * self._new_h)
        return cx, cy

    def _get_box_canvas_rect(self) -> Tuple[int, int, int, int]:
        bx1, by1 = self._normalized_to_canvas(self.crop_box[0], self.crop_box[1])
        bx2, by2 = self._normalized_to_canvas(self.crop_box[2], self.crop_box[3])
        return bx1, by1, bx2, by2

    def _get_handles_positions(self) -> Dict[str, Tuple[int, int]]:
        bx1, by1, bx2, by2 = self._get_box_canvas_rect()
        mx = (bx1 + bx2) // 2
        my = (by1 + by2) // 2
        return {
            "nw": (bx1, by1),
            "n":  (mx, by1),
            "ne": (bx2, by1),
            "e":  (bx2, my),
            "se": (bx2, by2),
            "s":  (mx, by2),
            "sw": (bx1, by2),
            "w":  (bx1, my),
        }

    # --- SỰ KIỆN CHUỘT ---
    def _hit_test(self, cx: int, cy: int) -> Tuple[str, str]:
        """
        Xác định con trỏ chuột đang nằm trên phần tử nào:
        Trả về (mode, cursor_style).
        """
        if self.current_frame is None or self._new_w <= 0:
            return "none", "arrow"

        # 1. Kiểm tra 8 điểm neo
        handles = self._get_handles_positions()
        tol = self.HANDLE_RADIUS + 4
        cursor_map = {
            "nw": "size_nw_se",
            "se": "size_nw_se",
            "ne": "size_ne_sw",
            "sw": "size_ne_sw",
            "n":  "size_ns",
            "s":  "size_ns",
            "w":  "size_we",
            "e":  "size_we",
        }
        for name, (hx, hy) in handles.items():
            if abs(cx - hx) <= tol and abs(cy - hy) <= tol:
                return f"resize_{name}", cursor_map[name]

        # 2. Kiểm tra bên trong ô vuông
        bx1, by1, bx2, by2 = self._get_box_canvas_rect()
        if bx1 <= cx <= bx2 and by1 <= cy <= by2:
            return "move", "fleur"

        # 3. Nằm trên vùng hiển thị video
        if (self._offset_x <= cx <= self._offset_x + self._new_w and
            self._offset_y <= cy <= self._offset_y + self._new_h):
            return "create", "crosshair"

        return "none", "arrow"

    def _on_mouse_move(self, event):
        if self._drag_mode is not None:
            return
        _, cursor = self._hit_test(event.x, event.y)
        self.canvas.config(cursor=cursor)

    def _on_mouse_down(self, event):
        if self.current_frame is None or self._new_w <= 0:
            return

        mode, _ = self._hit_test(event.x, event.y)
        if mode == "none":
            return

        self._drag_mode = mode
        self._drag_start_mouse = (event.x, event.y)
        self._drag_start_box = list(self.crop_box)

        if mode == "create":
            # Bắt đầu vẽ ô vuông mới từ điểm bấm
            nx, ny = self._canvas_to_normalized(event.x, event.y)
            self.crop_box = [nx, ny, nx, ny]
            self._redraw_overlay()

    def _on_mouse_drag(self, event):
        if self._drag_mode is None or self.current_frame is None or self._new_w <= 0:
            return

        mode = self._drag_mode
        curr_nx, curr_ny = self._canvas_to_normalized(event.x, event.y)
        min_w_norm = self.MIN_BOX_PX / max(1, self._new_w)
        min_h_norm = self.MIN_BOX_PX / max(1, self._new_h)

        if mode == "create":
            # Kéo vẽ ô vuông mới
            start_nx, start_ny = self._canvas_to_normalized(
                self._drag_start_mouse[0], self._drag_start_mouse[1]
            )
            self.crop_box = [
                min(start_nx, curr_nx),
                min(start_ny, curr_ny),
                max(start_nx, curr_nx),
                max(start_ny, curr_ny),
            ]
        elif mode == "move":
            # Di chuyển cả ô vuông
            start_cx, start_cy = self._drag_start_mouse
            dx = (event.x - start_cx) / self._new_w
            dy = (event.y - start_cy) / self._new_h

            ox1, oy1, ox2, oy2 = self._drag_start_box
            box_w = ox2 - ox1
            box_h = oy2 - oy1

            nx1 = ox1 + dx
            ny1 = oy1 + dy

            # Chặn không vượt quá khung hình
            if nx1 < 0.0:
                nx1 = 0.0
            elif nx1 + box_w > 1.0:
                nx1 = 1.0 - box_w

            if ny1 < 0.0:
                ny1 = 0.0
            elif ny1 + box_h > 1.0:
                ny1 = 1.0 - box_h

            self.crop_box = [nx1, ny1, nx1 + box_w, ny1 + box_h]
        elif mode.startswith("resize_"):
            handle = mode[len("resize_"):]
            ox1, oy1, ox2, oy2 = self._drag_start_box
            nx1, ny1, nx2, ny2 = ox1, oy1, ox2, oy2

            if "w" in handle:
                nx1 = min(curr_nx, ox2 - min_w_norm)
            if "e" in handle:
                nx2 = max(curr_nx, ox1 + min_w_norm)
            if "n" in handle:
                ny1 = min(curr_ny, oy2 - min_h_norm)
            if "s" in handle:
                ny2 = max(curr_ny, oy1 + min_h_norm)

            self.crop_box = [nx1, ny1, nx2, ny2]

        self._redraw_overlay()
        if self.on_crop_change:
            self.on_crop_change(tuple(self.crop_box))

    def _on_mouse_up(self, event):
        if self._drag_mode is not None:
            # Chuẩn hóa lại tọa độ
            x1, y1, x2, y2 = self.crop_box
            nx1 = max(0.0, min(1.0, min(x1, x2)))
            ny1 = max(0.0, min(1.0, min(y1, y2)))
            nx2 = max(0.0, min(1.0, max(x1, x2)))
            ny2 = max(0.0, min(1.0, max(y1, y2)))

            # Đảm bảo kích thước tối thiểu
            min_w_norm = self.MIN_BOX_PX / max(1, self._new_w) if self._new_w > 0 else 0.05
            min_h_norm = self.MIN_BOX_PX / max(1, self._new_h) if self._new_h > 0 else 0.05
            if nx2 - nx1 < min_w_norm:
                nx2 = min(1.0, nx1 + min_w_norm)
            if ny2 - ny1 < min_h_norm:
                ny2 = min(1.0, ny1 + min_h_norm)

            self.crop_box = [nx1, ny1, nx2, ny2]
            self._drag_mode = None
            self._redraw_overlay()

            if self.on_crop_change:
                self.on_crop_change(tuple(self.crop_box))

        # Cập nhật lại con trỏ chuột
        _, cursor = self._hit_test(event.x, event.y)
        self.canvas.config(cursor=cursor)

    # --- VẼ GIAO DIỆN ---
    def _redraw_full(self):
        """Vẽ lại toàn bộ canvas gồm cả ảnh nền và khung chọn"""
        self.canvas.delete("all")
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w < 10 or canvas_h < 10:
            return

        if self.current_frame is None:
            self.canvas.create_text(
                canvas_w // 2, canvas_h // 2,
                text="Chưa có video được chọn\n(Chọn file video hoặc dán link M3U8 để xem trước)",
                fill="#a6adc8",
                font=("Segoe UI", 10),
                justify=tk.CENTER
            )
            return

        # Tính toán kích thước co giãn giữ nguyên tỉ lệ video
        self._img_h, self._img_w, _ = self.current_frame.shape
        scale = min(canvas_w / self._img_w, canvas_h / self._img_h)
        self._new_w = max(1, int(self._img_w * scale))
        self._new_h = max(1, int(self._img_h * scale))

        self._offset_x = (canvas_w - self._new_w) // 2
        self._offset_y = (canvas_h - self._new_h) // 2

        # Chuyển đổi BGR sang RGB và hiển thị ảnh
        rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
        resized_frame = cv2.resize(rgb_frame, (self._new_w, self._new_h), interpolation=cv2.INTER_AREA)

        pil_img = Image.fromarray(resized_frame)
        self.tk_image = ImageTk.PhotoImage(image=pil_img)

        self.canvas.create_image(
            self._offset_x, self._offset_y,
            anchor=tk.NW,
            image=self.tk_image,
            tags="video_bg"
        )

        self._redraw_overlay()

    def _redraw_overlay(self):
        """Chỉ vẽ lại khung chọn phụ đề và các điểm neo (tối ưu hiệu năng cực cao)"""
        self.canvas.delete("crop_overlay")

        if self.current_frame is None or self._new_w <= 0:
            return

        bx1, by1, bx2, by2 = self._get_box_canvas_rect()
        vx1 = self._offset_x
        vy1 = self._offset_y
        vx2 = self._offset_x + self._new_w
        vy2 = self._offset_y + self._new_h

        # 1. Làm tối nhẹ 4 góc ngoài ô chọn (Dimming overlay)
        dim_tag = "crop_overlay"
        # Top
        if by1 > vy1:
            self.canvas.create_rectangle(vx1, vy1, vx2, by1, fill="#000000", stipple="gray50", outline="", tags=dim_tag)
        # Bottom
        if by2 < vy2:
            self.canvas.create_rectangle(vx1, by2, vx2, vy2, fill="#000000", stipple="gray50", outline="", tags=dim_tag)
        # Left
        if bx1 > vx1:
            self.canvas.create_rectangle(vx1, by1, bx1, by2, fill="#000000", stipple="gray50", outline="", tags=dim_tag)
        # Right
        if bx2 < vx2:
            self.canvas.create_rectangle(bx2, by1, vx2, by2, fill="#000000", stipple="gray50", outline="", tags=dim_tag)

        # 2. Khung viền ngoài màu tối + Viền trong màu xanh lá nổi bật
        self.canvas.create_rectangle(
            bx1 - 1, by1 - 1, bx2 + 1, by2 + 1,
            outline="#11111b",
            width=3,
            tags=dim_tag
        )
        self.canvas.create_rectangle(
            bx1, by1, bx2, by2,
            outline="#a6e3a1",
            width=2,
            tags=dim_tag
        )

        # 3. Vẽ 8 điểm neo co giãn
        r = self.HANDLE_RADIUS
        handles = self._get_handles_positions()
        for hx, hy in handles.values():
            self.canvas.create_rectangle(
                hx - r, hy - r, hx + r, hy + r,
                fill="#a6e3a1",
                outline="#11111b",
                width=1,
                tags=dim_tag
            )

        # 4. Nhãn thông tin vùng quét (Pixel & Tỉ lệ)
        real_crop_w = int((self.crop_box[2] - self.crop_box[0]) * self._img_w)
        real_crop_h = int((self.crop_box[3] - self.crop_box[1]) * self._img_h)
        badge_text = f" Vùng quét: {real_crop_w}×{real_crop_h} px "

        # Vị trí tag: phía trên nếu đủ chỗ, ngược lại vẽ bên trong mép trên
        badge_y = by1 - 11 if by1 - 22 >= vy1 else by1 + 11
        badge_x = bx1 + 6

        # Tạo nhãn chữ trước để đo độ rộng hoặc dùng x anchor
        text_id = self.canvas.create_text(
            badge_x, badge_y,
            text=badge_text,
            fill="#11111b",
            font=("Segoe UI", 9, "bold"),
            anchor=tk.W,
            tags=dim_tag
        )
        bbox = self.canvas.bbox(text_id)
        if bbox:
            # Tạo nền cho nhãn phía dưới text
            bg_rect = self.canvas.create_rectangle(
                bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1,
                fill="#a6e3a1",
                outline="#11111b",
                tags=dim_tag
            )
            self.canvas.tag_lower(bg_rect, text_id)

        # 5. Dòng gợi ý thao tác ở đáy canvas
        canvas_h = self.canvas.winfo_height()
        self.canvas.create_text(
            self.canvas.winfo_width() // 2, canvas_h - 10,
            text="💡 Nhấn & kéo chuột để vẽ vùng | Kéo góc/cạnh để đổi cỡ | Kéo giữa để di chuyển",
            fill="#6c7086",
            font=("Segoe UI", 8),
            tags=dim_tag
        )
