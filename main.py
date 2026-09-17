import sys
import logging
from pynput import keyboard

from config import GLOBAL_HOTKEY
from storage import TaskStorage
from audio_recorder import AudioRecorder
from groq_client import GroqClient
from ui.app_window import AppWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Main")

def main():
    logger.info("Iniciando Voice Sticky Notes & Tasks App...")

    # Inicialização dos Módulos Core
    storage = TaskStorage()
    recorder = AudioRecorder()
    groq_client = GroqClient()

    # Criação da Janela
    app = AppWindow(storage=storage, recorder=recorder, groq_client=groq_client)

    # Callback do Atalho Global
    def on_hotkey_activated():
        logger.info(f"Atalho global disparado ({GLOBAL_HOTKEY})")
        # Invoca na thread da interface gráfica
        app.after(0, app.toggle_recording)

    # Inicializa Listener Global do Teclado
    hotkey_listener = None
    try:
        hotkey_listener = keyboard.GlobalHotKeys({
            GLOBAL_HOTKEY: on_hotkey_activated
        })
        hotkey_listener.daemon = True
        hotkey_listener.start()
        logger.info(f"Atalho global ativado: {GLOBAL_HOTKEY}")
    except Exception as e:
        logger.warning(f"Não foi possível registrar o atalho global: {e}")

    # Encerramento limpo
    def on_closing():
        logger.info("Encerrando aplicação...")
        if hotkey_listener:
            try:
                hotkey_listener.stop()
            except Exception:
                pass
        if recorder.is_recording:
            try:
                recorder.stop()
            except Exception:
                pass
        app.destroy()
        sys.exit(0)

    app.protocol("WM_DELETE_WINDOW", on_closing)

    # Inicia o loop principal
    try:
        app.mainloop()
    except KeyboardInterrupt:
        on_closing()

if __name__ == "__main__":
    main()
