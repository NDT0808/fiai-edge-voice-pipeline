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