import os
from pathlib import Path
from dotenv import load_dotenv

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
DATA_FILE = BASE_DIR / "tasks.json"

# Carrega variáveis de ambiente
load_dotenv(dotenv_path=ENV_FILE)
load_dotenv()  # Fallback para ambiente global

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Configurações do Firebase
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "eullon-teste")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyDzWvpxdcJF2Fp5SoCBZwXjKDKMu6ZMIt8")
FIREBASE_CREDENTIALS_FILE = BASE_DIR / "firebase_credentials.json"
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", str(FIREBASE_CREDENTIALS_FILE))
FIREBASE_COLLECTION = os.getenv("FIREBASE_COLLECTION", "tasks")

# Configurações de Áudio
SAMPLE_RATE = 16000  # 16kHz ideal para Whisper
CHANNELS = 1         # Mono
AUDIO_DTYPE = "int16"

# Modelos Groq
GROQ_STT_MODEL = "whisper-large-v3"
GROQ_LLM_MODEL = "llama-3.3-70b-versatile"
GROQ_LANGUAGE = "pt"

# Atalho Global
GLOBAL_HOTKEY = "<ctrl>+<shift>+<space>"

# Configurações Visuais e UI
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 650
WINDOW_ALPHA = 0.96
ALWAYS_ON_TOP = True

# Paleta Dark Mode Minimalista
THEME = {
    "bg_dark": "#121214",
    "card_bg": "#1e1e24",
    "card_hover": "#282830",
    "border": "#2e2e38",
    "text_primary": "#f4f4f5",
    "text_secondary": "#a1a1aa",
    "text_muted": "#71717a",
    "accent": "#6366f1",        # Indigo moderno
    "accent_hover": "#4f46e5",
    "danger": "#ef4444",
    "warning": "#f59e0b",
    "success": "#10b981"
}

# Cores de Prioridades
PRIORITY_COLORS = {
    "alta": {
        "bg": "#451a1a",
        "fg": "#f87171",
        "border": "#ef4444"
    },
    "media": {
        "bg": "#3d2e0a",
        "fg": "#fbbf24",
        "border": "#f59e0b"
    },
    "baixa": {
        "bg": "#132e22",
        "fg": "#34d399",
        "border": "#10b981"
    }
}

# Estados do Microfone
STATUS_CONFIG = {
    "ready": {
        "text": "Pronto",
        "color": "#10b981",
        "subtext": "Clique no mic ou use Ctrl+Shift+Espaço"
    },
    "recording": {
        "text": "Ouvindo...",
        "color": "#ef4444",
        "subtext": "Fale agora... Solte ou clique para enviar"
    },
    "processing": {
        "text": "Processando...",
        "color": "#f59e0b",
        "subtext": "Transcrevendo e interpretando comando..."
    }
}
