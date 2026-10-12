import os
import shutil
import urllib.request
import cv2
import numpy as np
import pytesseract
from typing import Optional, Callable, Tuple, Dict, Any, List

# Common installation paths on Windows
TESSERACT_COMMON_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]

# Official Tesseract Best Model (Full unquantized LSTM weights for maximum diacritic precision)
MODEL_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/vie.traineddata"
FALLBACK_MODEL_URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/vie.traineddata"

class OCREngine:
    def __init__(self, project_root: Optional[str] = None):
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.project_root = project_root
        self.local_tessdata_dir = os.path.join(self.project_root, "tessdata")
        os.makedirs(self.local_tessdata_dir, exist_ok=True)
        
        self.engine_type = "tesseract"
        self._easyocr_reader = None
        self._vietocr_predictor = None

        self.tesseract_cmd = self._find_tesseract()
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        self._sync_tessdata_prefix()

    def _sync_tessdata_prefix(self):
        tess_dir = self.get_tessdata_dir()
        if tess_dir and os.path.exists(tess_dir):
            os.environ["TESSDATA_PREFIX"] = os.path.abspath(tess_dir)

    @staticmethod
    def is_easyocr_available() -> bool:
        try:
            import easyocr
            return True
        except ImportError:
            return False

    @staticmethod
    def is_vietocr_available() -> bool:
        try:
            from vietocr.tool.predictor import Predictor
            from vietocr.tool.config import Cfg
            return True
        except ImportError:
            return False

    def get_easyocr_reader(self):
        if self._easyocr_reader is None:
            import easyocr
            self._easyocr_reader = easyocr.Reader(["vi"], gpu=False, verbose=False)
        return self._easyocr_reader

    def get_vietocr_predictor(self):
        """Khởi tạo VietOCR predictor (lazy init - chỉ tải model khi cần)"""
        if self._vietocr_predictor is None:
            from vietocr.tool.predictor import Predictor
            from vietocr.tool.config import Cfg
            config = Cfg.load_config_from_name('vgg_transformer')
            config['cnn']['pretrained'] = True
            config['device'] = 'cpu'
            # Dùng greedy decode cho tốc độ cao trên CPU
            config['predictor']['beamsearch'] = False
            self._vietocr_predictor = Predictor(config)
        return self._vietocr_predictor

    def set_engine(self, engine_name: str):
        engine_name = engine_name.lower().strip()
        if "vietocr" in engine_name or "viet" in engine_name:
            self.engine_type = "vietocr"
        elif "easy" in engine_name:
            self.engine_type = "easyocr"
        else:
            self.engine_type = "tesseract"

    def _find_tesseract(self) -> Optional[str]:
        cmd = shutil.which("tesseract")
        if cmd and os.path.exists(cmd):
            return cmd
            
        for path in TESSERACT_COMMON_PATHS:
            if os.path.exists(path):
                return path
                
        return None

    def is_tesseract_available(self) -> bool:
        return self.tesseract_cmd is not None and os.path.exists(self.tesseract_cmd)

    def is_vietnamese_model_ready(self) -> bool:
        local_model = os.path.join(self.local_tessdata_dir, "vie.traineddata")
        if os.path.exists(local_model) and os.path.getsize(local_model) > 100000:
            return True

        if self.tesseract_cmd:
            tess_dir = os.path.dirname(self.tesseract_cmd)
            sys_tessdata = os.path.join(tess_dir, "tessdata", "vie.traineddata")
            if os.path.exists(sys_tessdata) and os.path.getsize(sys_tessdata) > 100000:
                return True

        return False

    def get_model_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "easyocr_ready": self.is_easyocr_available(),
            "tesseract_ready": self.is_tesseract_available(),
            "type": "none",
            "tess_type": "none",
            "size_mb": 0,
        }
        local_model = os.path.join(self.local_tessdata_dir, "vie.traineddata")
        if os.path.exists(local_model):
            size = os.path.getsize(local_model)
            info["size_mb"] = round(size / (1024 * 1024), 1)
            if size > 10_000_000:
                info["type"] = "best"
                info["tess_type"] = "best"
            else:
                info["type"] = "fast"
                info["tess_type"] = "fast"
        return info

    def get_tessdata_dir(self) -> Optional[str]:
        local_model = os.path.join(self.local_tessdata_dir, "vie.traineddata")
        if os.path.exists(local_model):
            return self.local_tessdata_dir

        if self.tesseract_cmd:
            tess_dir = os.path.dirname(self.tesseract_cmd)
            sys_tessdata = os.path.join(tess_dir, "tessdata", "vie.traineddata")
            if os.path.exists(sys_tessdata):
                return os.path.join(tess_dir, "tessdata")

        return self.local_tessdata_dir

    def download_vietnamese_model(self, progress_callback: Optional[Callable[[int, int, float], None]] = None) -> bool:
        target_path = os.path.join(self.local_tessdata_dir, "vie.traineddata")
        temp_path = target_path + ".tmp"
        
        urls_to_try = [MODEL_URL, FALLBACK_MODEL_URL]
        last_err = None

        for url in urls_to_try:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=45) as response, open(temp_path, "wb") as out_file:
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    chunk_size = 65536
                    
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            percent = min(100.0, (downloaded / total_size) * 100)
                            progress_callback(downloaded, total_size, percent)
                            
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.rename(temp_path, target_path)
                self._sync_tessdata_prefix()
                return True
            except Exception as e:
                last_err = e
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                continue

        raise RuntimeError(f"Lỗi tải từ điển tiếng Việt: {last_err}")

    def preprocess_image(self, bgr_image: np.ndarray, threshold_val: int = 185) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Quy trình tiền xử lý chống nhiễu nâng cao (v2):
        1. Tạo ảnh xám nhỏ để so sánh frame differencing.
        2. Phóng to 3x + CLAHE để tăng chi tiết dấu tiếng Việt.
        3. Bilateral filter giữ biên chữ sắc nét, xóa nhiễu nền.
        4. Tách màu trắng & vàng.
        5. Lọc hạt nhiễu (Morphological Opening & Connected Components siết chặt).
        6. Kiểm tra mật độ pixel: loại bỏ nền trống hoặc quá sáng.
        """
        raw_gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
        
        # 1. Phóng to 3x (tăng từ 2x lên 3x để dấu tiếng Việt rõ hơn)
        up_bgr = cv2.resize(bgr_image, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)

        # 2. Bilateral filter: giữ biên chữ, xóa nhiễu nền (ưu việt hơn Gaussian)
        up_bgr = cv2.bilateralFilter(up_bgr, d=5, sigmaColor=50, sigmaSpace=50)

        up_gray = cv2.cvtColor(up_bgr, cv2.COLOR_BGR2GRAY)

        # 3. CLAHE: tăng tương phản cục bộ giúp phân biệt dấu tiếng Việt trên nền phức tạp
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        up_gray = clahe.apply(up_gray)

        # 4. Lọc nhị phân màu trắng (ngưỡng an toàn 150-230)
        effective_thresh = max(150, min(230, threshold_val))
        _, white_mask = cv2.threshold(up_gray, effective_thresh, 255, cv2.THRESH_BINARY)

        # 5. Lọc màu vàng (Hue 15-38, Sat 45-255, Val 130-255)
        hsv = cv2.cvtColor(up_bgr, cv2.COLOR_BGR2HSV)
        yellow_mask = cv2.inRange(hsv, np.array([15, 45, 130]), np.array([38, 255, 255]))

        combined = cv2.bitwise_or(white_mask, yellow_mask)

        # 6. Kiểm tra mật độ pixel (siết chặt: giảm ngưỡng tối đa từ 45% xuống 30%)
        white_count = cv2.countNonZero(combined)
        total_pixels = combined.size
        density = white_count / total_pixels

        if density < 0.0005 or density > 0.30:
            return raw_gray, None

        # 7. Xóa hạt nhiễu li ti (mở rộng kernel 3x3)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opened = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)

        # 8. Connected Components lọc nghiêm ngặt hơn
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
        if num_labels <= 1:
            return raw_gray, None

        widths = stats[1:, cv2.CC_STAT_WIDTH]
        heights = stats[1:, cv2.CC_STAT_HEIGHT]
        areas = stats[1:, cv2.CC_STAT_AREA]

        # Siết chặt: area >= 12 (tăng từ 6), thêm kiểm tra aspect ratio
        # Loại bỏ đốm quá vuông/tròn nhỏ (aspect ratio width/height ngoài [0.1, 15])
        aspect_ratios = widths.astype(float) / np.maximum(heights.astype(float), 1)
        valid_indices = np.where(
            (heights >= 7) & (heights <= 200) &
            (widths >= 3) & (widths <= 900) &
            (areas >= 12) &
            (aspect_ratios >= 0.1) & (aspect_ratios <= 15.0)
        )[0] + 1

        if len(valid_indices) == 0:
            return raw_gray, None

        char_mask = np.isin(labels, valid_indices).astype(np.uint8) * 255

        if cv2.countNonZero(char_mask) < 40:
            return raw_gray, None

        # 9. Thêm viền đệm 25px để OCR đọc trọn vẹn ký tự ở biên
        padded = cv2.copyMakeBorder(char_mask, 25, 25, 25, 25, cv2.BORDER_CONSTANT, value=0)

        return raw_gray, padded

    def _segment_text_lines(self, binary_image: np.ndarray) -> List[np.ndarray]:
        """
        Tách ảnh nhị phân chứa phụ đề thành từng dòng text riêng biệt.
        Sử dụng horizontal projection profile kết hợp kiểm định kích thước và mật độ nét chữ.
        Loại bỏ hoàn toàn các dải ảnh rỗng/vệt mờ - nguyên nhân gây hallucination cho VietOCR.
        """
        h, w = binary_image.shape[:2]
        row_sums = np.sum(binary_image > 0, axis=1)

        # Ngưỡng phát hiện dòng có chữ: tối thiểu 1.0% pixel trên bề ngang
        threshold = max(3, int(w * 0.010))
        in_text = row_sums > threshold

        lines = []
        start = None
        for i in range(h):
            if in_text[i] and start is None:
                start = i
            elif not in_text[i] and start is not None:
                # Chiều cao dòng phụ đề tối thiểu 16px (trên ảnh phóng to 3x)
                line_h = i - start
                if 16 <= line_h <= 220:
                    y1 = max(0, start - 6)
                    y2 = min(h, i + 6)
                    line_img = binary_image[y1:y2, :]
                    # Crop theo chiều ngang x1..x2 của nét chữ
                    col_sums = np.sum(line_img > 0, axis=0)
                    cols_with_text = np.where(col_sums > 0)[0]
                    if len(cols_with_text) > 0:
                        x1 = max(0, cols_with_text[0] - 12)
                        x2 = min(w, cols_with_text[-1] + 13)
                        line_w = x2 - x1
                        cropped_line = line_img[:, x1:x2]
                        # Một dòng chữ phải rộng >= 30px và có >= 40 pixel trắng
                        white_pixels = cv2.countNonZero(cropped_line)
                        if line_w >= 30 and white_pixels >= 40:
                            lines.append(cropped_line)
                start = None

        if start is not None:
            line_h = h - start
            if 16 <= line_h <= 220:
                y1 = max(0, start - 6)
                line_img = binary_image[y1:h, :]
                col_sums = np.sum(line_img > 0, axis=0)
                cols_with_text = np.where(col_sums > 0)[0]
                if len(cols_with_text) > 0:
                    x1 = max(0, cols_with_text[0] - 12)
                    x2 = min(w, cols_with_text[-1] + 13)
                    line_w = x2 - x1
                    cropped_line = line_img[:, x1:x2]
                    white_pixels = cv2.countNonZero(cropped_line)
                    if line_w >= 30 and white_pixels >= 40:
                        lines.append(cropped_line)

        return lines

    def ocr_image(self, processed_image: Optional[np.ndarray], raw_bgr: Optional[np.ndarray] = None) -> str:
        """
        Trích xuất chữ từ ảnh phụ đề đã tiền xử lý.
        Hỗ trợ 3 engine: VietOCR (Transformer), EasyOCR (Deep Learning), Tesseract (LSTM).
        """
        if processed_image is None:
            return ""

        # VietOCR engine (Transformer - chuẩn dấu tiếng Việt tốt nhất)
        if self.engine_type == "vietocr" and self.is_vietocr_available():
            try:
                from PIL import Image
                predictor = self.get_vietocr_predictor()

                # VietOCR nhận diện từng dòng text → cần tách dòng trước
                text_lines = self._segment_text_lines(processed_image)
                results = []
                for line_img in text_lines:
                    # Đảo ngược: VietOCR mong đợi chữ đen trên nền trắng
                    if len(line_img.shape) == 2:
                        inverted = cv2.bitwise_not(line_img)
                    else:
                        inverted = line_img

                    pil_img = Image.fromarray(inverted)
                    text = predictor.predict(pil_img)
                    text = text.strip()
                    if text and len(text) >= 2:
                        results.append(text)

                return "\n".join(results).strip() if results else ""
            except Exception as e:
                print(f"[OCR Warning] VietOCR error: {e}")
                # Fallback sang Tesseract nếu VietOCR lỗi
                pass

        # EasyOCR engine (nếu người dùng chọn)
        if self.engine_type == "easyocr" and self.is_easyocr_available():
            try:
                reader = self.get_easyocr_reader()
                img_to_feed = raw_bgr if raw_bgr is not None else processed_image
                results = reader.readtext(img_to_feed, detail=1)
                if results:
                    sorted_items = sorted(results, key=lambda item: (int(item[0][0][1] / 15), item[0][0][0]))
                    texts = [item[1].strip() for item in sorted_items if item[2] > 0.35 and len(item[1].strip()) > 1]
                    return " ".join(texts).strip()
            except Exception as e:
                print(f"[OCR Warning] EasyOCR error: {e}")

        # Tesseract engine (fallback)
        if not self.is_tesseract_available():
            return ""

        self._sync_tessdata_prefix()

        try:
            raw_text = pytesseract.image_to_string(processed_image, lang="vie", config="--psm 6")
            return raw_text.strip()
        except Exception as e:
            try:
                raw_text = pytesseract.image_to_string(processed_image, lang="vie", config="--psm 11")
                return raw_text.strip()
            except Exception:
                return ""

