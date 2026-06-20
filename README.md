# Giải Pháp Luồng Voice-to-Voice (Push-to-Talk) Trên Môi Trường CPU ARM (Raspberry Pi 5)

Dự án này trình bày thiết kế kiến trúc hệ thống tương tác giọng nói offline (Local 100%) tối ưu hóa cho thiết bị nhúng phục vụ dự án robot hình người.

## 1. Kiến Trúc Luồng Thực Thi (Pseudo-code)
Toàn bộ logic điều khiển luồng dữ liệu âm thanh in-memory, cơ chế Push-to-Talk và quản lý vòng đời dữ liệu để tránh Memory Leak được tổ chức trong thư mục `src/pipeline.py`.

```
import numpy as np

class EdgeVoicePipeline:
    def __init__(self):
        """
        1. Vị trí khởi tạo mô hình: Chỉ nạp (load) vào RAM đúng 1 lần duy nhất lúc khởi động (Warm-up).
        Điều này loại bỏ hoàn toàn độ trễ khởi động (Cold-start latency) ở các lần bấm nút sau.
        """
        print("Đang khởi tạo hệ thống in-memory...")
        # Load mô hình ASR (Whisper-Tiny Q5 qua backend whisper.cpp / sherpa-onnx)
        self.asr_model = load_asr_model_gguf("models/whisper-tiny-q5.gguf", num_threads=2)
        
        # Load mô hình TTS (Piper TTS Tiếng Việt)
        self.tts_model = load_tts_model("models/piper-vi-model.onnx")
        
        # Khởi tạo buffer chứa dữ liệu âm thanh thô trên RAM
        self.audio_buffer = []
        self.is_recording = False
        print("Khởi tạo hoàn tất. Sẵn sàng nhận lệnh.")

    def on_button_press(self):
        """
        2. Hàm xử lý sự kiện Bấm nút (Bắt đầu Push-to-Talk)
        """
        self.is_recording = True
        self.audio_buffer.clear() # Xóa buffer cũ để tránh Memory Leak
        print("Đang ghi âm...")
        
        # Bắt đầu luồng đọc dữ liệu từ Microphone
        start_microphone_stream(callback=self._audio_callback)

    def _audio_callback(self, raw_pcm_chunk):
        """
        Hàm callback nhận dữ liệu liên tục từ mic khi đang giữ nút
        """
        if self.is_recording:
            # Lưu trực tiếp mảng byte vào RAM (List), không ghi xuống disk
            self.audio_buffer.append(raw_pcm_chunk)

    def on_button_release(self):
        """
        2. Hàm xử lý sự kiện Nhả nút (Kết thúc ghi âm & Xử lý)
        """
        self.is_recording = False
        stop_microphone_stream()
        print("Đang xử lý luồng Voice-to-Voice...")
        
        # 3. Truyền dữ liệu âm thanh thô (Raw PCM) vào mô hình ASR KHÔNG qua file temp.wav
        # Gộp các chunk âm thanh trong RAM thành một mảng NumPy array (16kHz, Float32)
        pcm_array = np.concatenate(self.audio_buffer, axis=0)
        
        # Bước ASR: Suy luận trực tiếp từ mảng PCM trên RAM
        text_result = self.asr_model.transcribe(pcm_array)
        print(f"Nhận diện (ASR): {text_result}")
        
        # Bước TTS: Chuyển văn bản thành audio (trả về mảng byte)
        audio_output_bytes = self.tts_model.synthesize(text_result)
        
        # Xử lý I/O độ trễ thấp (Nếu cần share cho process khác)
        # Lưu ra /dev/shm (RAM Disk) thay vì thẻ nhớ
        # save_to_ramdisk("/dev/shm/tts_output.pcm", audio_output_bytes)
        
        # Đẩy trực tiếp ra loa
        play_to_speaker(audio_output_bytes)
        
        # Dọn dẹp RAM ngay sau khi xong 1 luồng (Tránh Memory Leak)
        del pcm_array
        del audio_output_bytes
```

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
