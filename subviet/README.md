# SubViet — Ứng Dụng Trích Xuất Phụ Đề Tiếng Việt (Hardsub to SRT/VTT)

Ứng dụng Desktop Python chạy trên máy tính Windows giúp bóc tách phụ đề tiếng Việt in sẵn trên video (Hardsub) hoặc từ luồng phát trực tuyến M3U8 thành file phụ đề rời chuẩn `.srt` hoặc `.vtt`.

---

## 🚀 Cách khởi động ứng dụng

### Cách 1: Click đúp (Khuyên dùng)
* Vào thư mục `C:\Users\hau\Desktop\New folder\subviet\`
* **Click đúp vào file `run.bat`** để mở ứng dụng ngay lập tức.

### Cách 2: Chạy từ Terminal / PowerShell
```powershell
cd "C:\Users\hau\Desktop\New folder\subviet"
python app.py
```

---

## 🛠 Yêu cầu hệ thống & Thư viện

* **Python:** 3.10+ (Máy bạn hiện đang có Python 3.14 sẵn sàng).
* **Tesseract OCR:** Đã được cài đặt tại `C:\Program Files\Tesseract-OCR\tesseract.exe`.
* **Từ điển tiếng Việt (`vie.traineddata`):** Đã được tải sẵn vào thư mục `tessdata/` của dự án. Nếu chuyển sang máy khác, app có sẵn nút bấm 1-click để tự động tải về.

Nếu cài đặt trên máy mới, chỉ cần chạy lệnh:
```bash
pip install -r requirements.txt
```

---

## 📖 Hướng dẫn sử dụng chi tiết

1. **Chọn nguồn video:**
   * **File trong máy:** Chọn tab *File video trong máy* $\rightarrow$ bấm *Chọn file...* và chọn video `.mp4`, `.mkv`, `.avi`...
   * **Link phát online:** Chọn tab *Link phát trực tuyến* $\rightarrow$ dán URL `.m3u8` (từ API phim) $\rightarrow$ bấm *Tải preview*.
2. **Căn chỉnh vùng phụ đề (Preview):**
   * Khung xem trước sẽ hiển thị một đường viền đứt đoạn màu xanh lá: **"Vùng quét sub"**.
   * Kéo thanh trượt **Độ cao vùng sub đáy** (mặc định 18%) sao cho khung màu xanh bao trọn chữ phụ đề tiếng Việt ở đáy màn hình.
   * Kéo thanh trượt **Độ nhạy lọc chữ trắng** (mặc định 190) để làm sạch nền cảnh phim, chỉ giữ lại chữ trắng.
3. **Bắt đầu quét:**
   * Chọn nơi lưu file `.srt` (mặc định sẽ lưu cùng tên và cùng thư mục với video).
   * Bấm nút màu xanh **▶ BẮT ĐẦU BÓC SUB**.
   * Theo dõi tiến trình %, tốc độ FPS và danh sách các câu sub vừa nhận diện được hiển thị theo thời gian thực ở bảng bên phải.
   * Bạn có thể bấm **⏸ Tạm dừng** hoặc **⏹ Dừng hẳn** bất cứ lúc nào.
4. **Hoàn tất:**
   * Bấm **📂 Mở file SRT** để mở trực tiếp file phụ đề vừa xuất ra trên máy tính.

---

## 📂 Cấu trúc thư mục

```text
subviet/
├── app.py                 # File khởi động chính
├── run.bat                # Phím tắt click đúp chạy trên Windows
├── requirements.txt       # Danh sách thư viện Python
├── tessdata/              # Chứa file mô hình vie.traineddata
├── core/                  # Bộ xử lý lõi
│   ├── ocr_engine.py      # Tesseract OCR & tiền xử lý hình ảnh
│   ├── video_processor.py # Đọc video, kiểm tra frame trùng & luồng xử lý nền
│   └── srt_writer.py      # Format mốc thời gian và ghi file .srt/.vtt
└── ui/                    # Giao diện người dùng
    ├── main_window.py     # Cửa sổ chính Dark Modern Theme
    └── preview_widget.py  # Widget hiển thị khung hình preview & vùng crop
```
