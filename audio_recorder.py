import io
import wave
import queue
import threading
import numpy as np
import sounddevice as sd
from typing import Optional
from config import SAMPLE_RATE, CHANNELS

class AudioRecorder:
    """
    Gerenciador de gravação de áudio em buffer de memória não-bloqueante.
    Captura áudio do microfone padrão usando sounddevice e exporta diretamente
    para bytes WAV (16kHz, mono, 16-bit PCM) compatíveis com Groq Whisper.
    """
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self._stream: Optional[sd.InputStream] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._current_rms = 0.0

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback executado pelo sounddevice em thread de áudio nativa."""
        if status:
            print(f"[AudioRecorder] Alerta de stream: {status}")
        
        if self.is_recording:
            # Clona os dados e enfileira
            data_copy = indata.copy()
            self._audio_queue.put(data_copy)
            
            # Calcula energia RMS para alimentar indicador visual da UI
            try:
                # indata é int16 [-32768, 32767]
                float_data = data_copy.astype(np.float32) / 32768.0
                rms = np.sqrt(np.mean(float_data ** 2))
                self._current_rms = float(rms)
            except Exception:
                self._current_rms = 0.0

    def start(self) -> bool:
        """Inicia a captura de áudio."""
        with self._lock:
            if self.is_recording:
                return False

            # Limpa qualquer resíduo da fila
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

            self.is_recording = True
            self._current_rms = 0.0

            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="int16",
                    callback=self._audio_callback
                )
                self._stream.start()
                return True
            except Exception as e:
                self.is_recording = False
                print(f"[AudioRecorder] Falha ao iniciar gravação de áudio: {e}")
                return False

    def stop(self) -> Optional[bytes]:
        """
        Finaliza a captura de áudio e compila os dados gravados em um buffer WAV na memória.
        Retorna bytes do arquivo WAV ou None se a gravação for vazia/muito curta.
        """
        with self._lock:
            if not self.is_recording:
                return None

            self.is_recording = False
            self._current_rms = 0.0

            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    print(f"[AudioRecorder] Erro ao fechar stream de áudio: {e}")
                self._stream = None

        # Coleta todos os chunks capturados
        chunks = []
        while not self._audio_queue.empty():
            try:
                chunks.append(self._audio_queue.get_nowait())
            except queue.Empty:
                break

        if not chunks:
            return None

        # Concatena em um array numpy único
        full_audio = np.concatenate(chunks, axis=0)

        # Mínimo de 0.25 segundos de áudio gravado
        min_samples = int(self.sample_rate * 0.25)
        if len(full_audio) < min_samples:
            print("[AudioRecorder] Áudio muito curto descartado.")
            return None

        # Grava diretamente em um buffer de memória BytesIO no formato WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(full_audio.tobytes())

        wav_bytes = wav_buffer.getvalue()
        wav_buffer.close()
        return wav_bytes

    def get_rms_level(self) -> float:
        """Retorna o nível de amplitude RMS atual (0.0 a 1.0) para animações."""
        return self._current_rms if self.is_recording else 0.0
