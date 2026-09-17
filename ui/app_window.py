import threading
import time
import json
import customtkinter as ctk
from typing import Optional, Dict, Any

from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_ALPHA, ALWAYS_ON_TOP,
    THEME, STATUS_CONFIG, GLOBAL_HOTKEY, SETTINGS_FILE, DEFAULT_FONT_SIZE
)
from storage import TaskStorage
from audio_recorder import AudioRecorder
from groq_client import GroqClient
from ui.components import TaskItemCard, PulsingMicButton

class AppWindow(ctk.CTk):
    def __init__(self, storage: TaskStorage, recorder: AudioRecorder, groq_client: GroqClient):
        super().__init__()
        
        self.storage = storage
        self.recorder = recorder
        self.groq_client = groq_client

        # Configurações de Aparência
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Configuração da Janela
        self.title("Voice Tasks • Groq AI")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(360, 520)
        self.configure(fg_color=THEME["bg_dark"])

        # Always on Top & Translucidez
        self.always_on_top = ALWAYS_ON_TOP
        self.attributes("-topmost", self.always_on_top)
        try:
            self.attributes("-alpha", WINDOW_ALPHA)
        except Exception:
            pass  # Fallback caso OS não suporte alpha

        # Variáveis de Estado
        self.current_status = "ready"
        self._feedback_timer = None
        self._rms_timer = None

        # Tamanho de Fonte Configurável & Persistente
        self.font_size = self._load_font_setting()

        # Atalhos de Teclado para Zoom de Fonte (Ctrl + / Ctrl -)
        self.bind("<Control-plus>", lambda e: self._increase_font_size())
        self.bind("<Control-equal>", lambda e: self._increase_font_size())
        self.bind("<Control-minus>", lambda e: self._decrease_font_size())

        # Constrói a interface
        self._build_ui()
        self._refresh_tasks_view()
        self._update_status_ui("ready")

    def _build_ui(self):
        # 1. Header Superior (Barra Minimalista)
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent", height=44)
        self.header_frame.pack(fill="x", padx=16, pady=(12, 4))
        self.header_frame.pack_propagate(False)

        # Título do App
        self.logo_label = ctk.CTkLabel(
            self.header_frame,
            text="⚡ Voice Tasks",
            font=("Segoe UI", 16, "bold"),
            text_color=THEME["text_primary"]
        )
        self.logo_label.pack(side="left")

        # Botão Pin (Always on Top)
        self.pin_btn = ctk.CTkButton(
            self.header_frame,
            text="📌 Fixado" if self.always_on_top else "📍 Livre",
            width=68,
            height=26,
            font=("Segoe UI", 10, "bold"),
            fg_color=THEME["card_bg"],
            hover_color=THEME["card_hover"],
            text_color=THEME["accent"] if self.always_on_top else THEME["text_muted"],
            command=self._toggle_always_on_top
        )
        self.pin_btn.pack(side="right", padx=(6, 0))

        # Botão Status do Banco (Firebase / Local)
        is_fb = self.storage.is_firebase_connected()
        self.db_btn = ctk.CTkButton(
            self.header_frame,
            text="🔥 Cloud" if is_fb else "💾 Local",
            width=58,
            height=26,
            font=("Segoe UI", 10, "bold"),
            fg_color="#132e22" if is_fb else THEME["card_bg"],
            hover_color="#1a4030" if is_fb else THEME["card_hover"],
            text_color="#34d399" if is_fb else THEME["text_muted"],
            command=self._show_firebase_info_dialog
        )
        self.db_btn.pack(side="right", padx=(6, 0))

        # Botão Configurar API Key
        self.key_btn = ctk.CTkButton(
            self.header_frame,
            text="🔑 API",
            width=50,
            height=26,
            font=("Segoe UI", 10, "bold"),
            fg_color=THEME["card_bg"],
            hover_color=THEME["card_hover"],
            text_color=THEME["text_secondary"],
            command=self._prompt_api_key_dialog
        )
        self.key_btn.pack(side="right")

        # 2. Painel de Gravação de Voz (Voice Bar)
        self.voice_card = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            border_width=1,
            border_color=THEME["border"],
            corner_radius=12
        )
        self.voice_card.pack(fill="x", padx=14, pady=8)

        voice_content = ctk.CTkFrame(self.voice_card, fg_color="transparent")
        voice_content.pack(fill="x", padx=12, pady=10)

        # Botão do Microfone Pulsante
        self.mic_btn = PulsingMicButton(voice_content, on_click=self.toggle_recording)
        self.mic_btn.pack(side="left", padx=(0, 10))

        # Labels de Status
        status_text_frame = ctk.CTkFrame(voice_content, fg_color="transparent")
        status_text_frame.pack(side="left", fill="both", expand=True)

        self.status_title = ctk.CTkLabel(
            status_text_frame,
            text="Pronto",
            font=("Segoe UI", 13, "bold"),
            text_color=THEME["success"],
            anchor="w"
        )
        self.status_title.pack(fill="x")

        self.status_sub = ctk.CTkLabel(
            status_text_frame,
            text="Ctrl+Shift+Espaço ou clique no mic",
            font=("Segoe UI", 10),
            text_color=THEME["text_muted"],
            anchor="w"
        )
        self.status_sub.pack(fill="x")

        # Barra de Nível de Áudio (Feedback Visual de Onda)
        self.audio_level_bar = ctk.CTkProgressBar(
            self.voice_card,
            height=4,
            corner_radius=2,
            fg_color="#18181b",
            progress_color=THEME["danger"]
        )
        self.audio_level_bar.set(0.0)
        self.audio_level_bar.pack(fill="x", padx=12, pady=(0, 8))

        # 3. Toast / Banner de Feedback Instantâneo
        self.feedback_banner = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 11, "bold"),
            fg_color="transparent",
            text_color=THEME["accent"],
            height=0
        )
        self.feedback_banner.pack(fill="x", padx=16, pady=0)

        # 4. Container de Listas com Scroll
        self.scroll_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=THEME["border"],
            scrollbar_button_hover_color=THEME["accent"]
        )
        self.scroll_container.pack(fill="both", expand=True, padx=10, pady=4)

        # 5. Barra Inferior de Entrada Manual Rápida
        self.bottom_bar = ctk.CTkFrame(self, fg_color=THEME["card_bg"], height=52, corner_radius=0)
        self.bottom_bar.pack(fill="x", side="bottom")

        bottom_content = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        bottom_content.pack(fill="x", padx=10, pady=8)

        self.input_entry = ctk.CTkEntry(
            bottom_content,
            placeholder_text="Nova tarefa manual...",
            font=("Segoe UI", 12),
            height=34,
            fg_color="#121214",
            border_color=THEME["border"],
            text_color=THEME["text_primary"]
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.input_entry.bind("<Return>", lambda event: self._manual_add_task())

        self.priority_menu = ctk.CTkOptionMenu(
            bottom_content,
            values=["Média", "Alta", "Baixa"],
            width=76,
            height=34,
            font=("Segoe UI", 11),
            fg_color="#27272a",
            button_color=THEME["border"],
            button_hover_color=THEME["accent"]
        )
        self.priority_menu.set("Média")
        self.priority_menu.pack(side="left", padx=(0, 6))

        self.add_btn = ctk.CTkButton(
            bottom_content,
            text="＋",
            width=36,
            height=34,
            font=("Segoe UI", 14, "bold"),
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._manual_add_task
        )
        self.add_btn.pack(side="left")

    def _toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self.attributes("-topmost", self.always_on_top)
        self.pin_btn.configure(
            text="📌 Fixado" if self.always_on_top else "📍 Livre",
            text_color=THEME["accent"] if self.always_on_top else THEME["text_muted"]
        )

    def _update_status_ui(self, status: str, custom_text: Optional[str] = None):
        """Atualiza a barra de status visual de gravação/processamento."""
        self.current_status = status
        cfg = STATUS_CONFIG.get(status, STATUS_CONFIG["ready"])
        
        display_text = custom_text or cfg["text"]
        self.status_title.configure(text=display_text, text_color=cfg["color"])
        self.status_sub.configure(text=cfg["subtext"])
        self.mic_btn.set_recording_state(status == "recording")

        if status == "recording":
            self.audio_level_bar.configure(progress_color=THEME["danger"])
            self._start_rms_monitor()
        else:
            self._stop_rms_monitor()
            self.audio_level_bar.set(0.0)

    def _start_rms_monitor(self):
        if not self.recorder.is_recording:
            return
        level = min(1.0, self.recorder.get_rms_level() * 7.0)
        self.audio_level_bar.set(max(0.05, level))
        self._rms_timer = self.after(50, self._start_rms_monitor)

    def _stop_rms_monitor(self):
        if self._rms_timer:
            try:
                self.after_cancel(self._rms_timer)
            except Exception:
                pass
            self._rms_timer = None

    def show_feedback(self, message: str, is_error: bool = False):
        """Exibe uma notificação curta de feedback na tela."""
        color = THEME["danger"] if is_error else THEME["success"]
        self.feedback_banner.configure(
            text=message,
            text_color=color,
            height=24,
            fg_color="#201515" if is_error else "#12261b"
        )

        if self._feedback_timer:
            try:
                self.after_cancel(self._feedback_timer)
            except Exception:
                pass

        self._feedback_timer = self.after(3500, self._clear_feedback)

    def _clear_feedback(self):
        self.feedback_banner.configure(text="", height=0, fg_color="transparent")
        self._feedback_timer = None

    def _refresh_tasks_view(self):
        """Reconstrói a listagem de tarefas no container com scroll."""
        for widget in self.scroll_container.winfo_children():
            widget.destroy()

        pending_tasks = self.storage.get_pending_tasks()
        completed_tasks = self.storage.get_completed_tasks()

        # Cabeçalho da Seção "A Fazer"
        pend_header = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
        pend_header.pack(fill="x", pady=(2, 6))

        pend_title = ctk.CTkLabel(
            pend_header,
            text=f"A FAZER  ({len(pending_tasks)})",
            font=("Segoe UI", 11, "bold"),
            text_color=THEME["text_secondary"]
        )
        pend_title.pack(side="left")

        # Controles de Zoom de Fonte (A- / A+)
        font_ctrl_frame = ctk.CTkFrame(pend_header, fg_color="transparent")
        font_ctrl_frame.pack(side="right")

        btn_font_dec = ctk.CTkButton(
            font_ctrl_frame,
            text="A-",
            font=("Segoe UI", 10, "bold"),
            width=26,
            height=20,
            corner_radius=4,
            fg_color=THEME["card_bg"],
            hover_color=THEME["card_hover"],
            text_color=THEME["text_secondary"],
            command=self._decrease_font_size
        )
        btn_font_dec.pack(side="left", padx=(0, 2))

        lbl_font = ctk.CTkLabel(
            font_ctrl_frame,
            text=f"{self.font_size}px",
            font=("Segoe UI", 10, "bold"),
            text_color=THEME["accent"],
            width=36
        )
        lbl_font.pack(side="left")

        btn_font_inc = ctk.CTkButton(
            font_ctrl_frame,
            text="A+",
            font=("Segoe UI", 10, "bold"),
            width=26,
            height=20,
            corner_radius=4,
            fg_color=THEME["card_bg"],
            hover_color=THEME["card_hover"],
            text_color=THEME["text_secondary"],
            command=self._increase_font_size
        )
        btn_font_inc.pack(side="left", padx=(2, 0))

        if not pending_tasks:
            empty_lbl = ctk.CTkLabel(
                self.scroll_container,
                text="Nenhuma pendência! Use a voz ou digite abaixo.",
                font=("Segoe UI", 11, "italic"),
                text_color=THEME["text_muted"],
                pady=16
            )
            empty_lbl.pack(fill="x")
        else:
            for task in pending_tasks:
                card = TaskItemCard(
                    self.scroll_container,
                    task=task,
                    on_toggle=self._handle_toggle_task,
                    on_delete=self._handle_delete_task,
                    font_size=self.font_size
                )
                card.pack(fill="x", pady=3)

        # Seção "Concluídas"
        if completed_tasks:
            comp_header = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
            comp_header.pack(fill="x", pady=(14, 6))

            comp_title = ctk.CTkLabel(
                comp_header,
                text=f"CONCLUÍDAS  ({len(completed_tasks)})",
                font=("Segoe UI", 11, "bold"),
                text_color=THEME["text_muted"]
            )
            comp_title.pack(side="left")

            clear_btn = ctk.CTkButton(
                comp_header,
                text="Limpar todas",
                font=("Segoe UI", 10),
                width=65,
                height=20,
                fg_color="transparent",
                hover_color="#381919",
                text_color=THEME["danger"],
                command=self._handle_clear_completed
            )
            clear_btn.pack(side="right")

            for task in completed_tasks:
                card = TaskItemCard(
                    self.scroll_container,
                    task=task,
                    on_toggle=self._handle_toggle_task,
                    on_delete=self._handle_delete_task,
                    font_size=self.font_size
                )
                card.pack(fill="x", pady=2)

    def _manual_add_task(self):
        title = self.input_entry.get().strip()
        if not title:
            return
        
        priority_map = {"Média": "media", "Alta": "alta", "Baixa": "baixa"}
        selected_prio = priority_map.get(self.priority_menu.get(), "media")

        self.storage.add_task(title=title, priority=selected_prio)
        self.input_entry.delete(0, "end")
        self._refresh_tasks_view()
        self.show_feedback("Tarefa adicionada!")

    def _handle_toggle_task(self, task_id: str):
        updated = self.storage.toggle_task(task_id)
        self._refresh_tasks_view()
        if updated:
            msg = "Tarefa concluída!" if updated.get("completed") else "Tarefa reaberta!"
            self.show_feedback(msg)

    def _handle_delete_task(self, task_id: str):
        if self.storage.delete_task(task_id):
            self._refresh_tasks_view()
            self.show_feedback("Tarefa removida!")

    def _handle_clear_completed(self):
        count = self.storage.clear_completed()
        self._refresh_tasks_view()
        self.show_feedback(f"{count} tarefas limpas!")

    # Controle de Gravação & Threading
    def toggle_recording(self):
        """Alterna entre iniciar e parar a gravação de voz."""
        if not self.recorder.is_recording:
            started = self.recorder.start()
            if started:
                self._update_status_ui("recording")
            else:
                self.show_feedback("Erro ao acessar microfone", is_error=True)
        else:
            # Finaliza gravação e dispara thread de processamento
            self._update_status_ui("processing")
            wav_bytes = self.recorder.stop()
            if not wav_bytes:
                self._update_status_ui("ready")
                self.show_feedback("Áudio muito curto ou vazio.", is_error=True)
                return

            threading.Thread(
                target=self._process_voice_worker,
                args=(wav_bytes,),
                daemon=True
            ).start()

    def _process_voice_worker(self, wav_bytes: bytes):
        """Worker assíncrono para processar áudio via Groq Whisper e Llama 3.3."""
        try:
            current_tasks = self.storage.get_all_tasks()
            result, transcription = self.groq_client.process_voice_command(wav_bytes, current_tasks)

            action = result.get("action", "none")
            task_id = result.get("task_id")
            task_title = result.get("task_title", "")
            priority = result.get("priority", "media")
            due_time = result.get("due_time")
            feedback = result.get("feedback_message", "Comando executado!")

            # Executa a ação no Storage
            if action == "add":
                if task_title:
                    self.storage.add_task(title=task_title, priority=priority, due_time=due_time)
            elif action == "toggle_complete":
                # Tenta por id, ou busca por título correspondente
                resolved_id = task_id
                if not resolved_id and task_title:
                    match = self.storage.find_task_by_title_match(task_title)
                    if match:
                        resolved_id = match["id"]
                if resolved_id:
                    self.storage.toggle_task(resolved_id)
                else:
                    feedback = "Tarefa não encontrada"
            elif action == "delete":
                resolved_id = task_id
                if not resolved_id and task_title:
                    match = self.storage.find_task_by_title_match(task_title)
                    if match:
                        resolved_id = match["id"]
                if resolved_id:
                    self.storage.delete_task(resolved_id)
                else:
                    feedback = "Tarefa não encontrada"
            elif action == "clear_completed":
                self.storage.clear_completed()

            # Notifica a interface na thread principal
            self.after(0, self._on_voice_success, feedback, transcription)
        except Exception as e:
            error_msg = str(e)
            self.after(0, self._on_voice_error, error_msg)

    def _on_voice_success(self, feedback: str, transcription: str):
        self._update_status_ui("ready")
        self._refresh_tasks_view()
        display_msg = f"{feedback} ('{transcription}')" if len(transcription) <= 30 else feedback
        self.show_feedback(display_msg)

    def _on_voice_error(self, error_msg: str):
        self._update_status_ui("ready")
        self.show_feedback(f"Erro: {error_msg}", is_error=True)

    def _prompt_api_key_dialog(self):
        """Dialog rápido para configurar ou alterar a GROQ_API_KEY."""
        dialog = ctk.CTkInputDialog(
            text="Cole sua Groq API Key (gsk_...):",
            title="Configurar Groq API"
        )
        entered_key = dialog.get_input()
        if entered_key:
            clean_key = entered_key.strip()
            self.groq_client.set_api_key(clean_key)
            # Salva no .env
            try:
                from config import ENV_FILE
                with open(ENV_FILE, "w", encoding="utf-8") as f:
                    f.write(f"GROQ_API_KEY={clean_key}\n")
                self.show_feedback("Chave Groq salva com sucesso!")
            except Exception as e:
                self.show_feedback(f"Chave aplicada na sessão: {e}")

    def _show_firebase_info_dialog(self):
        """Exibe status e orientações de conexão com o Firebase Firestore."""
        is_fb = self.storage.is_firebase_connected()
        from tkinter import messagebox
        if is_fb:
            messagebox.showinfo(
                "Firebase Firestore Conectado",
                "🔥 O aplicativo está conectado ao Firebase Firestore!\n\n"
                "Suas tarefas são sincronizadas na nuvem em tempo real e cacheadas localmente para máxima velocidade."
            )
        else:
            messagebox.showinfo(
                "Configurar Firebase Firestore",
                "💾 Modo Local Ativo (Sem Nuvem).\n\n"
                "Para sincronizar suas tarefas no Firebase:\n"
                "1. Acesse o Firebase Console (console.firebase.google.com)\n"
                "2. Crie um projeto e ative o Firestore Database\n"
                "3. Em Configurações do Projeto > Contas de Serviço, gere uma Nova Chave Privada\n"
                "4. Salve o arquivo baixado como 'firebase_credentials.json' na pasta do app:\n"
                f"{self.storage.filepath.parent}\n\n"
                "O app detectará e ativará a nuvem automaticamente ao reiniciar!"
            )

    def _load_font_setting(self) -> int:
        try:
            if SETTINGS_FILE.is_file():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = int(data.get("font_size", DEFAULT_FONT_SIZE))
                    return max(12, min(24, val))
        except Exception:
            pass
        return DEFAULT_FONT_SIZE

    def _save_font_setting(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"font_size": self.font_size}, f)
        except Exception:
            pass

    def _increase_font_size(self):
        if self.font_size < 24:
            self.font_size += 2
            self._save_font_setting()
            self._refresh_tasks_view()
            self.show_feedback(f"Fonte aumentada: {self.font_size}px")

    def _decrease_font_size(self):
        if self.font_size > 12:
            self.font_size -= 2
            self._save_font_setting()
            self._refresh_tasks_view()
            self.show_feedback(f"Fonte diminuída: {self.font_size}px")
