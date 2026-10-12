import time
import threading
from difflib import SequenceMatcher
from typing import Optional, Callable, Dict, Any, List, Tuple
import cv2
import numpy as np

from .ocr_engine import OCREngine
from .srt_writer import clean_subtitle_text, write_subtitles_file, is_valid_subtitle

def _get_fingerprint(gray_img: np.ndarray) -> np.ndarray:
    """
    Tạo dấu vân tay khung hình (Downscale + Gaussian Blur) để triệt tiêu
    nhiễu hạt phim (film grain) và nhiễu nén video (macroblocking).
    Giúp phát hiện chính xác khi nào phụ đề xuất hiện mà không bị ảnh hưởng bởi hạt nhiễu.
    """
    down = cv2.resize(gray_img, (160, 40), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(down, (5, 5), 0)

def _should_merge_subtitles(text1: str, text2: str) -> bool:
    """Kiểm tra hai câu có phải là phiên bản nối tiếp / chuỗi con / lặp lại của nhau không"""
    t1 = text1.lower().strip()
    t2 = text2.lower().strip()
    if not t1 or not t2:
        return False
    if t1 == t2:
        return True

    # 1. Chuỗi con / tiền tố (hiệu ứng chạy chữ / fade-in karaoke)
    if t1 in t2 or t2 in t1:
        return True

    # 2. Độ trùng lặp từ vựng (Word overlap >= 50%)
    w1 = set(t1.split())
    w2 = set(t2.split())
    if w1 and w2:
        overlap = len(w1.intersection(w2)) / min(len(w1), len(w2))
        if overlap >= 0.50:
            return True

    # 3. Độ tương đồng mờ (Fuzzy similarity >= 55%)
    sim = SequenceMatcher(None, t1, t2).ratio()
    return sim >= 0.55

def _commit_subtitle(
    sub_item: Optional[Dict[str, Any]],
    subtitles_list: List[Dict[str, Any]],
    on_sub_found: Optional[Callable[[Dict[str, Any]], None]] = None,
):
    """
    Lưu câu phụ đề với cơ chế CHỐNG LẶP CÂU & GỘP TIỀN TỐ (Smart Subtitle Merging):
    - Nếu câu vừa bóc tách có nội dung trùng/tương đồng/chuỗi con với câu trước đó và cách nhau <= 2.5s:
      Tự động gộp thời gian hiển thị và giữ lại bản câu hoàn chỉnh nhất.
    - Loại bỏ các phân đoạn cộc lốc quá ngắn (< 4 ký tự) trừ khi là thán từ có nghĩa.
    """
    if not sub_item:
        return
    text = sub_item.get("text", "").strip()
    if not is_valid_subtitle(text):
        return

    words = text.split()
    # Gộp câu đơn nếu nó là phần nối tiếp hoặc chuỗi con của câu trước đó
    if len(words) < 2:
        if len(subtitles_list) > 0 and _should_merge_subtitles(subtitles_list[-1]["text"], text):
            subtitles_list[-1]["end"] = max(subtitles_list[-1]["end"], sub_item["end"])
            return

    # Cơ chế gộp thông minh (Smart Merging)
    if len(subtitles_list) > 0:
        last_sub = subtitles_list[-1]
        gap = sub_item["start"] - last_sub["end"]
        # Cho phép gối đầu nhẹ (-1.0s) đến cách nhau tối đa 2.5s
        if -1.0 <= gap <= 2.5:
            if _should_merge_subtitles(last_sub["text"], text):
                # Gộp thời gian hiển thị
                last_sub["end"] = max(last_sub["end"], sub_item["end"])
                # Cập nhật phiên bản dịch chuẩn hơn / dài hơn
                if len(text) >= len(last_sub["text"]):
                    last_sub["text"] = text
                return

    sub_item["index"] = len(subtitles_list) + 1
    subtitles_list.append(sub_item)
    if on_sub_found:
        on_sub_found(sub_item)

class VideoProcessor:
    def __init__(self, ocr_engine: OCREngine):
        self.ocr_engine = ocr_engine
        self._stop_requested = threading.Event()
        self._pause_requested = threading.Event()
        self._is_running = False

    def is_running(self) -> bool:
        return self._is_running

    def stop(self):
        self._stop_requested.set()
        self._pause_requested.clear()

    def pause(self):
        self._pause_requested.set()

    def resume(self):
        self._pause_requested.clear()

    def is_paused(self) -> bool:
        return self._pause_requested.is_set()

    @staticmethod
    def get_video_info(source: str) -> Dict[str, Any]:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise ValueError(f"Không thể mở nguồn video: {source}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = (total_frames / fps) if total_frames > 0 and fps > 0 else 0.0

        cap.release()
        return {
            "fps": fps,
            "total_frames": total_frames,
            "duration": duration,
            "width": width,
            "height": height,
        }

    @staticmethod
    def get_preview_frame(source: str, time_seconds: float = 0.0) -> Optional[np.ndarray]:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        target_frame = int(time_seconds * fps)

        if total_frames > 0 and target_frame >= total_frames:
            target_frame = max(0, total_frames // 4)

        if target_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        ret, frame = cap.read()
        cap.release()
        return frame if ret else None

    def process_video(
        self,
        video_source: str,
        output_filepath: str,
        crop_bottom_ratio: float = 0.14,
        crop_box: Optional[Tuple[float, float, float, float]] = None,
        sample_fps: float = 2.0,
        threshold_val: int = 185,
        diff_threshold: float = 1.0,
        start_seconds: float = 0.0,
        end_seconds: Optional[float] = None,
        on_progress: Optional[Callable[[float, float, float, float, float], None]] = None,
        on_sub_found: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[List[Dict[str, Any]], str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self._stop_requested.clear()
        self._pause_requested.clear()
        self._is_running = True

        cap = cv2.VideoCapture(video_source)
        if not cap.isOpened():
            self._is_running = False
            if on_error:
                on_error(f"Không thể mở nguồn video: {video_source}")
            return

        try:
            original_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            total_duration = (total_frames / original_fps) if total_frames > 0 else 0.0

            if end_seconds and end_seconds > 0 and end_seconds < total_duration:
                calc_total_duration = end_seconds - start_seconds
            else:
                calc_total_duration = total_duration - start_seconds if total_duration > 0 else 0.0

            frame_step = max(1, int(round(original_fps / sample_fps)))
            current_frame_idx = int(start_seconds * original_fps)
            end_frame_idx = (
                int(end_seconds * original_fps)
                if (end_seconds and end_seconds > 0)
                else (total_frames if total_frames > 0 else float("inf"))
            )

            if on_status:
                on_status("Đang quét phụ đề video...")

            subtitles: List[Dict[str, Any]] = []
            active_sub: Optional[Dict[str, Any]] = None
            prev_fingerprint: Optional[np.ndarray] = None
            start_wall_time = time.time()
            processed_samples = 0

            while not self._stop_requested.is_set():
                while self._pause_requested.is_set() and not self._stop_requested.is_set():
                    time.sleep(0.2)
                    if on_status:
                        on_status("Đang tạm dừng...")

                if self._stop_requested.is_set() or current_frame_idx >= end_frame_idx:
                    break

                cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                current_timestamp = current_frame_idx / original_fps
                h, w, _ = frame.shape

                # 1. Cắt vùng phụ đề theo ô chọn hoặc theo dải đáy
                if crop_box is not None:
                    bx1, by1, bx2, by2 = crop_box
                    px1 = max(0, min(w - 2, int(bx1 * w)))
                    py1 = max(0, min(h - 2, int(by1 * h)))
                    px2 = max(px1 + 2, min(w, int(bx2 * w)))
                    py2 = max(py1 + 2, min(h, int(by2 * h)))
                    sub_crop = frame[py1:py2, px1:px2]
                else:
                    crop_h = max(10, int(h * crop_bottom_ratio))
                    crop_y = h - crop_h
                    sub_crop = frame[crop_y:h, 0:w]

                # 2. Tiền xử lý ảnh
                gray_crop, thresh_crop = self.ocr_engine.preprocess_image(sub_crop, threshold_val)
                sample_duration = frame_step / original_fps

                # 3. Smart Frame Differencing (miễn nhiễm với hạt nhiễu phim)
                curr_fingerprint = _get_fingerprint(gray_crop)
                is_duplicate = False
                if prev_fingerprint is not None:
                    diff_val = cv2.absdiff(curr_fingerprint, prev_fingerprint).mean()
                    if diff_val < diff_threshold:
                        is_duplicate = True

                prev_fingerprint = curr_fingerprint

                if is_duplicate and active_sub is not None:
                    # Kéo dài thời gian hiển thị của câu sub hiện tại
                    active_sub["end"] = current_timestamp + sample_duration
                elif thresh_crop is None:
                    # Khung hình không chứa chữ (cảnh tối hoặc cháy sáng)
                    if active_sub is not None:
                        _commit_subtitle(active_sub, subtitles, on_sub_found)
                        active_sub = None
                else:
                    # Chạy OCR
                    raw_text = self.ocr_engine.ocr_image(thresh_crop, raw_bgr=sub_crop)
                    cleaned = clean_subtitle_text(raw_text)

                    if cleaned and is_valid_subtitle(cleaned):
                        is_same_text = False
                        if active_sub is not None:
                            if _should_merge_subtitles(active_sub["text"], cleaned):
                                is_same_text = True
                                if len(cleaned) >= len(active_sub["text"]):
                                    active_sub["text"] = cleaned

                        if is_same_text and active_sub is not None:
                            active_sub["end"] = current_timestamp + sample_duration
                        else:
                            # Lưu câu trước đó
                            if active_sub is not None:
                                _commit_subtitle(active_sub, subtitles, on_sub_found)

                            # Bắt đầu câu mới
                            active_sub = {
                                "start": current_timestamp,
                                "end": current_timestamp + sample_duration,
                                "text": cleaned,
                            }
                    else:
                        if active_sub is not None:
                            _commit_subtitle(active_sub, subtitles, on_sub_found)
                            active_sub = None

                processed_samples += 1
                current_frame_idx += frame_step

                # Cập nhật tiến độ
                elapsed = time.time() - start_wall_time
                speed_fps = (processed_samples / elapsed) if elapsed > 0 else 0.0
                curr_progress_sec = current_timestamp - start_seconds
                percent = (
                    (curr_progress_sec / calc_total_duration * 100.0)
                    if calc_total_duration > 0
                    else 0.0
                )
                percent = min(100.0, max(0.0, percent))

                remaining_sec = max(0.0, calc_total_duration - curr_progress_sec)
                video_rate = (curr_progress_sec / elapsed) if elapsed > 0 else 1.0
                eta = (remaining_sec / video_rate) if video_rate > 0 else 0.0

                if on_progress:
                    on_progress(current_timestamp, total_duration, percent, speed_fps, eta)

            # Lưu câu cuối cùng
            if active_sub is not None:
                _commit_subtitle(active_sub, subtitles, on_sub_found)

            # Xuất file kết quả
            if output_filepath and subtitles:
                write_subtitles_file(subtitles, output_filepath)

            if on_status:
                if self._stop_requested.is_set():
                    on_status(f"Đã dừng! Đã bóc được {len(subtitles)} đoạn phụ đề sạch.")
                else:
                    on_status(f"Hoàn thành! Đã trích xuất {len(subtitles)} đoạn phụ đề sạch.")

            if on_complete:
                on_complete(subtitles, output_filepath)

        except Exception as e:
            if on_error:
                on_error(f"Lỗi trong quá trình xử lý: {str(e)}")
        finally:
            cap.release()
            self._is_running = False
