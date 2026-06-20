# fiai-edge-voice-pipeline
# Giải Pháp Luồng Voice-to-Voice (Push-to-Talk) Trên Môi Trường CPU ARM (Raspberry Pi 5)

Dự án này trình bày thiết kế kiến trúc hệ thống tương tác giọng nói offline (Local 100%) tối ưu hóa cho thiết bị nhúng phục vụ dự án robot hình người.

## 1. Kiến Trúc Luồng Thực Thi (Pseudo-code)
Toàn bộ logic điều khiển luồng dữ liệu âm thanh in-memory, cơ chế Push-to-Talk và quản lý vòng đời dữ liệu để tránh Memory Leak được tổ chức trong thư mục `src/pipeline.py`.

## 2. Giải Trình Thiết Kế Hệ Thống (Documentation)

### Câu 1: Lựa chọn Backend (whisper.cpp vs sherpa-onnx)
* **Lựa chọn:** `whisper.cpp`
* **Giải thích:** Hỗ trợ native (gốc) tốt nhất cho định dạng GGUF, được viết bằng C/C++ thuần túy giúp loại bỏ các dependency nặng nề. Do bài toán yêu cầu cơ chế Push-to-Talk (suy luận dạng Batch/Offline sau khi nhả nút), `whisper.cpp` kết hợp tập lệnh ARM NEON mang lại tốc độ xử lý vượt trội và quản lý RAM cực kỳ ổn định.

### Câu 2: Cấu hình luồng (Thread Allocation)
* **Thiết lập:** `num_threads = 2` (hoặc tối đa là 3) trên tổng số 4 nhân của Pi 5.
* **Lý do không chọn tối đa (4 nhân):**
  1. *Nghẽn cổ chai băng thông bộ nhớ (Memory Bandwidth):* Suy luận AI trên CPU bị giới hạn lớn bởi tốc độ nạp dữ liệu từ RAM lên Cache. 2 luồng đã đủ bão hòa băng thông này; tăng thêm luồng sẽ khiến các nhân rơi vào trạng thái chờ luân phiên.
  2. *Tranh chấp tài nguyên & Context Switching:* OS và các luồng I/O (micro, loa) cần CPU để xử lý. Ép 4 nhân chạy mô hình sẽ gây nghẽn hệ thống do chuyển đổi ngữ cảnh liên tục.
  3. *Quá nhiệt (Thermal Throttling):* Không gian robot hạn chế, chạy 100% công suất 4 nhân sẽ làm CPU quá nhiệt nhanh chóng, hệ thống tự động hạ xung nhịp làm tăng tổng thời gian suy luận (RTF).

### Câu 3: Xử lý I/O Độ trễ thấp
* **Giải pháp:** Lưu trữ các file audio tạm (nếu bắt buộc) tại thư mục **`/dev/shm`** (Shared Memory - RAM Disk dưới dạng `tmpfs`).
* **Lý do:** Tốc độ đọc/ghi trên RAM đạt hàng chục GB/s (gần như bằng 0 về độ trễ I/O). Đồng thời, việc này bảo vệ tuổi thọ của thẻ MicroSD trên Raspberry Pi bằng cách tránh các chu kỳ ghi xóa liên tục (Write Cycles).

### Câu 4: Lựa chọn chuẩn lượng tử hóa (Quantization)
* **Lựa chọn:** `Q5` (Định dạng `GGUF Q5_0` hoặc `Q5_1`).
* **Lý do loại trừ các mức khác:**
  * *Không chọn Q4:* Mô hình Whisper-Tiny rất nhỏ (~39M tham số), nén xuống 4-bit (Q4) sẽ mất mát trọng số nghiêm trọng, đẩy tỷ lệ lỗi từ vựng (WER) vượt ngưỡng ràng buộc 2%.
  * *Không chọn FP16/INT8:* Khối lượng mô hình Q5 đủ nhỏ để giảm tải băng thông truyền dữ liệu từ RAM vào CPU cache giúp tối ưu tốc độ thực thi (RTF < 0.3) tốt hơn nhiều so với FP16, đồng thời không cần tập dữ liệu hiệu chuẩn phức tạp như INT8.