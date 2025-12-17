# 🎬 Video Tool Pro

Ứng dụng xử lý video hàng loạt ("Re-up") tối ưu cho TikTok và YouTube Shorts, được xây dựng bằng **Streamlit** và **FFmpeg**.

## 🚀 Tính năng chính

Công cụ giúp tự động hóa việc chỉnh sửa video để tránh các thuật toán quét bản quyền hình ảnh và âm thanh:

*   **Đa nền tảng**: Chế độ tối ưu riêng cho **TikTok** (Tăng bão hòa màu, Speed 1.05x) và **YouTube Shorts** (Tăng độ sáng, Speed 1.02x).
*   **Xử lý Hình ảnh (Visual Effects)**:
    *   Zoom 10% & Crop (chống quét khung hình).
    *   Lật gương (Flip Mirror).
    *   Thêm nhiễu hạt (Add Noise) - chống quét vân tay ảnh (pixel fingerprint).
    *   Hiệu ứng Vignette (làm tối 4 góc).
*   **Xử lý Âm thanh (Audio Effects)**:
    *   Pitch Shifting: Đổi giọng/cao độ (+5%).
    *   Low Cut (Giảm Bass): Cắt tần số < 100Hz.
    *   Tăng tốc độ âm thanh đồng bộ với video.
    *   Tùy chọn tắt tiếng hoàn toàn (Mute).
*   **Giao diện tiện lợi**:
    *   Tải lên nhiều video cùng lúc (Kéo thả).
    *   Xem trước video (Preview) ngay trên web.
    *   Tải xuống từng video hoặc nén ZIP toàn bộ.
    *   Chạy trên Docker container, dễ dàng triển khai.

## 🛠️ Cài đặt & Sử dụng

### Cách 1: Chạy bằng Docker (Khuyến nghị)

Yêu cầu: Đã cài đặt [Docker Desktop](https://www.docker.com/products/docker-desktop).

1.  Clone dự án về máy.
2.  Mở terminal tại thư mục dự án.
3.  Chạy lệnh:
    ```bash
    docker-compose up --build
    ```
4.  Truy cập trình duyệt tại: `http://localhost:8501`

### Cách 2: Chạy trực tiếp (Python)

Yêu cầu:
*   Python 3.9+
*   FFmpeg đã được cài đặt và thêm vào biến môi trường (PATH).

1.  Cài đặt thư viện:
    ```bash
    pip install -r requirements.txt
    ```
2.  Chạy ứng dụng:
    ```bash
    streamlit run app.py
    ```

## 📂 Cấu trúc dự án

```
.
├── app.py              # Mã nguồn chính (Streamlit UI & Logic)
├── assets/
│   └── style.css       # Tùy chỉnh giao diện (CSS)
├── Dockerfile          # Cấu hình build Docker image
├── docker-compose.yml  # Cấu hình Docker Compose
├── requirements.txt    # Các thư viện Python cần thiết
└── README.md           # Hướng dẫn sử dụng
```

## 📝 Ghi chú

*   Ứng dụng xử lý video sử dụng CPU thông qua FFmpeg. Tốc độ xử lý phụ thuộc vào cấu hình máy tính của bạn.
*   Các file tạm sẽ được tự động dọn dẹp khi bắt đầu phiên làm việc mới.
