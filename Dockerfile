    # Sử dụng base image Python tối ưu cho ARM64 (Raspberry Pi)
FROM python:3.10-slim-bullseye

# Cài đặt các thư viện hệ thống cần thiết cho Xử lý âm thanh và C++ Backend
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libasound2-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc
WORKDIR /app

# Copy requirement và cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Lệnh khởi chạy hệ thống lắng nghe sự kiện
CMD ["python", "main.py"]