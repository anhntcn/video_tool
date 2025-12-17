# Sử dụng Python 3.9 slim version để tối ưu dung lượng
FROM python:3.9-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Cập nhật và cài đặt FFmpeg
# RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
# User yêu cầu: Crucial: Run apt-get update && apt-get install -y ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Sao chép requirements.txt vào container
COPY requirements.txt .

# Cài đặt các thư viện Python
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn vào container
COPY . .

# Expose port mặc định của Streamlit
EXPOSE 8501

# Lệnh để chạy ứng dụng Streamlit
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
