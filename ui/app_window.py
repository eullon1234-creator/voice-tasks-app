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
from ai_memory_engine import AIMemoryEngine
from ui.components import TaskItemCard, PulsingMicButton

class AppWindow(ctk.CTk):
    def __init__(self, storage: TaskStorage, recorder: AudioRecorder, groq_client: GroqClient):
        super().__init__()
        
        self.storage = storage
        self.recorder = recorder
        self.groq_client = groq_client
        self.ai_memory = AIMemoryEngine(groq_client=self.groq_client)

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
        self._stopwatch_timer = None
        self._card_widgets = []
        self.selected_category = "Todas"

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

        # Inicia loops em tempo real (cronômetro e lembretes)
        self._start_stopwatch_loop()
        self.after(5000, self._check_reminders)

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

        # Botão Celular (QR Code)
        self.mobile_btn = ctk.CTkButton(
            self.header_frame,
            text="📱 App",
            width=48,
            height=26,
            font=("Segoe UI", 10, "bold"),
            fg_color="#1e1b4b",
            hover_color="#312e81",
            text_color="#a5b4fc",
            border_width=1,
            border_color="#4338ca",
            command=self._show_mobile_qr_dialog
        )
        self.mobile_btn.pack(side="right", padx=(6, 0))

        # 2. Barra de Navegação entre Abas (Tarefas / Relatórios / Copiloto)
        self.tab_nav = ctk.CTkSegmentedButton(
            self,
            values=["📋 Tarefas", "📊 Relatórios", "💬 Copiloto IA"],
            font=("Segoe UI", 11, "bold"),
            selected_color=THEME["accent"],
            selected_hover_color=THEME["accent_hover"],
            unselected_color=THEME["card_bg"],
            unselected_hover_color=THEME["card_hover"],
            command=self._on_tab_change
        )
        self.tab_nav.set("📋 Tarefas")
        self.tab_nav.pack(fill="x", padx=14, pady=(2, 4))

        # 2.1 Banner de Gamificação & Streaks
        self.streak_card = ctk.CTkFrame(
            self,
            fg_color="#181922",
            border_width=1,
            border_color="#2b2d3d",
            corner_radius=10
        )
        self.streak_card.pack(fill="x", padx=14, pady=(2, 4))

        streak_content = ctk.CTkFrame(self.streak_card, fg_color="transparent")
        streak_content.pack(fill="x", padx=10, pady=(6, 2))

        self.streak_label = ctk.CTkLabel(
            streak_content,
            text="🔥 0 dias seguidos",
            font=("Segoe UI", 11, "bold"),
            text_color="#f59e0b"
        )
        self.streak_label.pack(side="left")

        self.goal_label = ctk.CTkLabel(
            streak_content,
            text="🎯 Meta: 0m / 60m",
            font=("Segoe UI", 10),
            text_color=THEME["text_muted"]
        )
        self.goal_label.pack(side="right")

        self.goal_bar = ctk.CTkProgressBar(
            self.streak_card,
            height=4,
            corner_radius=2,
            fg_color="#101116",
            progress_color=THEME["accent"]
        )
        self.goal_bar.set(0.0)
        self.goal_bar.pack(fill="x", padx=10, pady=(0, 6))

        # 2.2 Barra de Filtro de Categorias Rápido
        self.category_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.category_bar.pack(fill="x", padx=14, pady=(2, 4))

        from config import CATEGORIES
        self.category_buttons = {}
        for cat_name, cfg in CATEGORIES.items():
            btn = ctk.CTkButton(
                self.category_bar,
                text=f"{cfg['icon']} {cat_name}",
                font=("Segoe UI", 10, "bold"),
                height=24,
                corner_radius=12,
                fg_color=THEME["accent"] if cat_name == "Todas" else THEME["card_bg"],
                text_color="#ffffff" if cat_name == "Todas" else THEME["text_secondary"],
                hover_color=THEME["accent_hover"],
                command=lambda c=cat_name: self._set_category_filter(c)
            )
            btn.pack(side="left", padx=(0, 4))
            self.category_buttons[cat_name] = btn

        # 3. Painel de Gravação de Voz (Voice Bar)
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

        # Container da Aba de Relatórios (inicia oculto)
        self.reports_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=THEME["border"],
            scrollbar_button_hover_color=THEME["accent"]
        )

        # Container da Aba do Copiloto IA (inicia oculto)
        self.copilot_container = ctk.CTkFrame(self, fg_color="transparent")
        self._build_copilot_ui()

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

        self.category_menu = ctk.CTkOptionMenu(
            bottom_content,
            values=["Geral", "Trabalho", "Pessoal", "Estudos"],
            width=82,
            height=34,
            font=("Segoe UI", 10),
            fg_color="#27272a",
            button_color=THEME["border"],
            button_hover_color=THEME["accent"]
        )
        self.category_menu.set("Geral")
        self.category_menu.pack(side="left", padx=(0, 4))

        self.priority_menu = ctk.CTkOptionMenu(
            bottom_content,
            values=["Média", "Alta", "Baixa"],
            width=72,
            height=34,
            font=("Segoe UI", 10),
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

    def _on_tab_change(self, selected_tab: str):
        """Alterna entre as abas de Tarefas, Relatórios e Copiloto IA."""
        if "Tarefas" in selected_tab:
            self.reports_container.pack_forget()
            self.copilot_container.pack_forget()
            self.streak_card.pack(fill="x", padx=14, pady=(2, 4), after=self.tab_nav)
            self.category_bar.pack(fill="x", padx=14, pady=(2, 4), after=self.streak_card)
            self.voice_card.pack(fill="x", padx=14, pady=8, after=self.category_bar)
            self.feedback_banner.pack(fill="x", padx=16, pady=0, after=self.voice_card)
            self.bottom_bar.pack(fill="x", side="bottom")
            self.scroll_container.pack(fill="both", expand=True, padx=10, pady=4, after=self.feedback_banner)
            self._refresh_tasks_view()
        elif "Relatórios" in selected_tab:
            self.streak_card.pack_forget()
            self.category_bar.pack_forget()
            self.voice_card.pack_forget()
            self.scroll_container.pack_forget()
            self.bottom_bar.pack_forget()
            self.copilot_container.pack_forget()
            self.reports_container.pack(fill="both", expand=True, padx=10, pady=4, after=self.tab_nav)
            self._refresh_reports_view()
        else:
            # Copiloto IA
            self.streak_card.pack_forget()
            self.category_bar.pack_forget()
            self.voice_card.pack_forget()
            self.scroll_container.pack_forget()
            self.bottom_bar.pack_forget()
            self.reports_container.pack_forget()
            self.copilot_container.pack(fill="both", expand=True, padx=10, pady=4, after=self.tab_nav)
            self._refresh_copilot_view()

    def _refresh_reports_view(self):
        """Renderiza os KPIs, Gráficos de Barra e Histórico de Produtividade."""
        for widget in self.reports_container.winfo_children():
            widget.destroy()

        stats = self.storage.get_productivity_stats()

        # 1. Grade de KPIs (2x2)
        kpi_grid = ctk.CTkFrame(self.reports_container, fg_color="transparent")
        kpi_grid.pack(fill="x", pady=(2, 8))
        kpi_grid.grid_columnconfigure((0, 1), weight=1)

        def make_kpi_card(master, row, col, icon, value, label, color):
            card = ctk.CTkFrame(master, fg_color=THEME["card_bg"], border_width=1, border_color=THEME["border"], corner_radius=10)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            
            top_f = ctk.CTkFrame(card, fg_color="transparent")
            top_f.pack(fill="x", padx=10, pady=(8, 2))
            
            lbl_ic = ctk.CTkLabel(top_f, text=icon, font=("Segoe UI", 16))
            lbl_ic.pack(side="left")
            
            lbl_val = ctk.CTkLabel(card, text=value, font=("Segoe UI", 16, "bold"), text_color=color)
            lbl_val.pack(padx=10, anchor="w")
            
            lbl_desc = ctk.CTkLabel(card, text=label, font=("Segoe UI", 10), text_color=THEME["text_muted"])
            lbl_desc.pack(padx=10, pady=(0, 8), anchor="w")

        make_kpi_card(kpi_grid, 0, 0, "⏱️", stats["total_focus_formatted"], "Tempo de Foco", "#34d399")
        make_kpi_card(kpi_grid, 0, 1, "✅", f"{stats['completed_count']} / {stats['total_tasks']}", f"{stats['completion_rate']}% Concluídas", "#818cf8")
        make_kpi_card(kpi_grid, 1, 0, "⚡", stats["avg_formatted"], "Média p/ Tarefa", "#fbbf24")
        make_kpi_card(kpi_grid, 1, 1, "📌", f"{stats['pending_count']} pendentes", "A Fazer", "#f87171")

        # 2. Gráfico Semanal de Produtividade (Barras)
        chart_card = ctk.CTkFrame(self.reports_container, fg_color=THEME["card_bg"], border_width=1, border_color=THEME["border"], corner_radius=10)
        chart_card.pack(fill="x", pady=6)

        ch_header = ctk.CTkFrame(chart_card, fg_color="transparent")
        ch_header.pack(fill="x", padx=12, pady=(10, 6))

        ch_title = ctk.CTkLabel(ch_header, text="📈 PRODUTIVIDADE NA SEMANA", font=("Segoe UI", 11, "bold"), text_color=THEME["text_secondary"])
        ch_title.pack(side="left")

        weekday_time = stats["weekday_time"]
        max_time = max(weekday_time.values()) if any(weekday_time.values()) else 1

        for day, sec in weekday_time.items():
            row_f = ctk.CTkFrame(chart_card, fg_color="transparent")
            row_f.pack(fill="x", padx=12, pady=2)

            day_lbl = ctk.CTkLabel(row_f, text=day, font=("Segoe UI", 11, "bold"), width=36, anchor="w", text_color=THEME["text_primary"])
            day_lbl.pack(side="left")

            ratio = min(1.0, max(0.02, sec / max_time)) if sec > 0 else 0.02
            bar = ctk.CTkProgressBar(row_f, height=8, corner_radius=4, fg_color="#101116", progress_color=THEME["accent"] if sec > 0 else "#262938")
            bar.set(ratio)
            bar.pack(side="left", fill="x", expand=True, padx=8)

            from storage import format_duration
            time_text = format_duration(sec) if sec > 0 else "-"
            val_lbl = ctk.CTkLabel(row_f, text=time_text, font=("Segoe UI", 10), width=54, anchor="e", text_color=THEME["text_muted"] if sec == 0 else "#34d399")
            val_lbl.pack(side="right")

        ctk.CTkFrame(chart_card, height=6, fg_color="transparent").pack()

        # 3. Distribuição por Prioridade
        prio_card = ctk.CTkFrame(self.reports_container, fg_color=THEME["card_bg"], border_width=1, border_color=THEME["border"], corner_radius=10)
        prio_card.pack(fill="x", pady=6)

        p_header = ctk.CTkFrame(prio_card, fg_color="transparent")
        p_header.pack(fill="x", padx=12, pady=(10, 6))
        p_title = ctk.CTkLabel(p_header, text="🎯 TAREFAS POR PRIORIDADE", font=("Segoe UI", 11, "bold"), text_color=THEME["text_secondary"])
        p_title.pack(side="left")

        prio_names = [("Alta", "alta", "#ef4444"), ("Média", "media", "#f59e0b"), ("Baixa", "baixa", "#10b981")]
        tot_all = max(1, stats["total_tasks"])
        for p_label, p_key, p_col in prio_names:
            cnt = stats["prio_counts"].get(p_key, 0)
            comp = stats["prio_completed"].get(p_key, 0)
            p_row = ctk.CTkFrame(prio_card, fg_color="transparent")
            p_row.pack(fill="x", padx=12, pady=2)

            pl_lbl = ctk.CTkLabel(p_row, text=p_label, font=("Segoe UI", 11), width=48, anchor="w", text_color=p_col)
            pl_lbl.pack(side="left")

            p_bar = ctk.CTkProgressBar(p_row, height=8, corner_radius=4, fg_color="#101116", progress_color=p_col)
            p_bar.set(cnt / tot_all if cnt > 0 else 0.02)
            p_bar.pack(side="left", fill="x", expand=True, padx=8)

            pct_lbl = ctk.CTkLabel(p_row, text=f"{comp}/{cnt} feitas", font=("Segoe UI", 10), width=74, anchor="e", text_color=THEME["text_muted"])
            pct_lbl.pack(side="right")

        ctk.CTkFrame(prio_card, height=6, fg_color="transparent").pack()

        # 4. Botão Copiar Relatório
        def copy_summary():
            summary_text = (
                f"📊 Relatório de Produtividade • Voice Tasks\n"
                f"⏱️ Tempo Focado: {stats['total_focus_formatted']}\n"
                f"✅ Concluídas: {stats['completed_count']} de {stats['total_tasks']} ({stats['completion_rate']}%)\n"
                f"⚡ Tempo Médio por Tarefa: {stats['avg_formatted']}\n"
                f"📌 Pendentes: {stats['pending_count']}"
            )
            self.clipboard_clear()
            self.clipboard_append(summary_text)
            self.show_feedback("Relatório copiado para a área de transferência!")

        copy_btn = ctk.CTkButton(
            self.reports_container,
            text="📋 Copiar Resumo de Produtividade",
            font=("Segoe UI", 12, "bold"),
            height=36,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=copy_summary
        )
        copy_btn.pack(fill="x", pady=(8, 16))

    def _build_copilot_ui(self):
        """Constrói a interface da aba Copiloto IA."""
        # 1. Topo: Título e Botão Cérebro da IA
        top_bar = ctk.CTkFrame(self.copilot_container, fg_color="transparent")
        top_bar.pack(fill="x", padx=6, pady=(4, 6))

        title_lbl = ctk.CTkLabel(
            top_bar,
            text="💬 Copiloto IA (Memória Viva)",
            font=("Segoe UI", 12, "bold"),
            text_color=THEME["text_primary"]
        )
        title_lbl.pack(side="left")

        brain_btn = ctk.CTkButton(
            top_bar,
            text="🧠 Memória da IA",
            font=("Segoe UI", 10, "bold"),
            width=105,
            height=26,
            corner_radius=8,
            fg_color="#1e1b4b",
            hover_color="#312e81",
            text_color="#a5b4fc",
            border_width=1,
            border_color="#4f46e5",
            command=self._show_ai_memory_modal
        )
        brain_btn.pack(side="right")

        # 2. Card de Insight / Dica do Dia da IA
        self.copilot_insight_card = ctk.CTkFrame(
            self.copilot_container,
            fg_color="#181924",
            border_width=1,
            border_color="#2f324d",
            corner_radius=10
        )
        self.copilot_insight_card.pack(fill="x", padx=4, pady=(0, 6))

        in_top = ctk.CTkFrame(self.copilot_insight_card, fg_color="transparent")
        in_top.pack(fill="x", padx=10, pady=(6, 2))

        in_title = ctk.CTkLabel(in_top, text="✨ INSIGHT DO COPILOTO", font=("Segoe UI", 10, "bold"), text_color="#fbbf24")
        in_title.pack(side="left")

        self.insight_text_lbl = ctk.CTkLabel(
            self.copilot_insight_card,
            text="Analisando suas anotações e hábitos para gerar sua sugestão...",
            font=("Segoe UI", 11),
            text_color=THEME["text_primary"],
            wraplength=340,
            justify="left"
        )
        self.insight_text_lbl.pack(fill="x", padx=10, pady=(2, 6))

        self.insight_action_frame = ctk.CTkFrame(self.copilot_insight_card, fg_color="transparent")
        self.insight_action_frame.pack(fill="x", padx=10, pady=(0, 6))

        # 3. Lista de Mensagens do Chat Rolável
        self.chat_scroll = ctk.CTkScrollableFrame(
            self.copilot_container,
            fg_color="transparent",
            scrollbar_button_color=THEME["border"],
            scrollbar_button_hover_color=THEME["accent"]
        )
        self.chat_scroll.pack(fill="both", expand=True, padx=2, pady=4)

        # 4. Barra Inferior de Envio do Chat
        chat_bar = ctk.CTkFrame(self.copilot_container, fg_color=THEME["card_bg"], height=48, corner_radius=10)
        chat_bar.pack(fill="x", side="bottom", padx=2, pady=(4, 2))

        cb_content = ctk.CTkFrame(chat_bar, fg_color="transparent")
        cb_content.pack(fill="x", padx=8, pady=6)

        self.chat_entry = ctk.CTkEntry(
            cb_content,
            placeholder_text="Fale com o Copiloto (o que está fazendo, planos)...",
            font=("Segoe UI", 11),
            height=34,
            fg_color="#121214",
            border_color=THEME["border"],
            text_color=THEME["text_primary"]
        )
        self.chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.chat_entry.bind("<Return>", lambda e: self._send_copilot_message())

        self.chat_mic_btn = ctk.CTkButton(
            cb_content,
            text="🎙",
            width=36,
            height=34,
            font=("Segoe UI", 13),
            fg_color="#27272a",
            hover_color=THEME["accent"],
            command=self._copilot_voice_input
        )
        self.chat_mic_btn.pack(side="left", padx=(0, 4))

        self.chat_send_btn = ctk.CTkButton(
            cb_content,
            text="➤",
            width=36,
            height=34,
            font=("Segoe UI", 13, "bold"),
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._send_copilot_message
        )
        self.chat_send_btn.pack(side="left")

    def _refresh_copilot_view(self):
        """Renderiza as mensagens do chat e atualiza o insight diário."""
        for w in self.chat_scroll.winfo_children():
            w.destroy()

        history = self.ai_memory.get_chat_history()
        if not history:
            welcome_msg = (
                "Olá, Eullon! Eu sou seu Copiloto Pessoal de Produtividade.\n\n"
                "Estou aqui para aprender com você todos os dias: suas rotinas na GEL, seus hábitos e suas metas. "
                "Pode me contar o que está fazendo, desabafar ou me pedir ajuda para planejar seu dia!"
            )
            self._render_chat_bubble("assistant", welcome_msg)
        else:
            for item in history[-15:]:
                self._render_chat_bubble(item["role"], item["content"])

        threading.Thread(target=self._async_load_insight, daemon=True).start()

    def _async_load_insight(self):
        tasks = self.storage.get_all_tasks()
        mission = self.ai_memory.generate_daily_mission(tasks)
        self.after(0, self._display_mission, mission)

    def _display_mission(self, mission: Dict[str, Any]):
        tip = mission.get("tip", "Tenha um excelente dia de foco!")
        self.insight_text_lbl.configure(text=tip)

        for w in self.insight_action_frame.winfo_children():
            w.destroy()

        task = mission.get("task")
        if task and task.get("title"):
            accept_btn = ctk.CTkButton(
                self.insight_action_frame,
                text=f"➕ Adicionar Sugestão: {task['title']}",
                font=("Segoe UI", 10, "bold"),
                height=26,
                fg_color="#065f46",
                hover_color="#047857",
                text_color="#34d399",
                border_width=1,
                border_color="#10b981",
                command=lambda: self._accept_suggested_task(task)
            )
            accept_btn.pack(fill="x")

    def _render_chat_bubble(self, role: str, content: str, suggested_task: Optional[Dict[str, Any]] = None):
        is_user = (role == "user")
        row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        row.pack(fill="x", pady=4)

        bubble = ctk.CTkFrame(
            row,
            fg_color="#2b2d42" if is_user else "#181924",
            border_width=1,
            border_color="#3d405b" if is_user else THEME["border"],
            corner_radius=12
        )
        bubble.pack(side="right" if is_user else "left", padx=8, pady=2)

        lbl = ctk.CTkLabel(
            bubble,
            text=content,
            font=("Segoe UI", 11),
            text_color="#ffffff" if is_user else THEME["text_primary"],
            wraplength=260,
            justify="left"
        )
        lbl.pack(padx=10, pady=8)

        if suggested_task and suggested_task.get("title"):
            st_btn = ctk.CTkButton(
                bubble,
                text=f"➕ Criar: {suggested_task['title']}",
                font=("Segoe UI", 10, "bold"),
                height=24,
                fg_color="#065f46",
                hover_color="#047857",
                text_color="#34d399",
                command=lambda: self._accept_suggested_task(suggested_task)
            )
            st_btn.pack(fill="x", padx=10, pady=(0, 8))

    def _send_copilot_message(self):
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, "end")
        self._render_chat_bubble("user", text)

        thinking_row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        thinking_row.pack(fill="x", pady=4)
        thinking_bubble = ctk.CTkLabel(
            thinking_row,
            text="💭 Pensando com sua memória...",
            font=("Segoe UI", 10, "italic"),
            text_color=THEME["text_muted"]
        )
        thinking_bubble.pack(side="left", padx=12)

        def worker():
            current_tasks = self.storage.get_all_tasks()
            res = self.ai_memory.chat_with_copilot(text, current_tasks)
            self.after(0, lambda: [thinking_row.destroy(), self._render_chat_bubble("assistant", res["reply"], res.get("suggested_task"))])

        threading.Thread(target=worker, daemon=True).start()

    def _copilot_voice_input(self):
        """Gravação de áudio rápida para o chat do Copiloto."""
        if not self.recorder.is_recording:
            started = self.recorder.start()
            if started:
                self.chat_mic_btn.configure(fg_color=THEME["danger"], text="⏹")
                self.show_feedback("Gravando para o Copiloto...")
            else:
                self.show_feedback("Erro ao acessar microfone", is_error=True)
        else:
            self.chat_mic_btn.configure(fg_color="#27272a", text="🎙")
            wav_bytes = self.recorder.stop()
            if not wav_bytes:
                return
            self.show_feedback("Transcrevendo fala...")
            def worker():
                try:
                    text = self.groq_client.transcribe_audio(wav_bytes)
                    self.after(0, lambda: [self.chat_entry.delete(0, "end"), self.chat_entry.insert(0, text), self._send_copilot_message()])
                except Exception as e:
                    self.after(0, self.show_feedback, f"Erro: {e}", True)
            threading.Thread(target=worker, daemon=True).start()

    def _accept_suggested_task(self, task_data: Dict[str, Any]):
        title = task_data.get("title", "")
        prio = task_data.get("priority", "media")
        cat = task_data.get("category", "Geral")
        due = task_data.get("due_time")
        try:
            self.storage.add_task(title=title, priority=prio, category=cat, due_time=due)
            self.show_feedback(f"Tarefa '{title}' adicionada à lista!")
        except Exception as e:
            self.show_feedback(str(e), is_error=True)

    def _show_ai_memory_modal(self):
        """Abre janela com tudo o que a IA já aprendeu sobre o Eullon."""
        win = ctk.CTkToplevel(self)
        win.title("🧠 Memória da IA • O que ela sabe sobre você")
        win.geometry("380x520")
        win.configure(fg_color=THEME["bg_dark"])
        win.attributes("-topmost", True)

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=12)

        mem = self.ai_memory.get_memory()

        def make_section(title, icon, items):
            sec_f = ctk.CTkFrame(scroll, fg_color=THEME["card_bg"], border_width=1, border_color=THEME["border"], corner_radius=10)
            sec_f.pack(fill="x", pady=6)
            h = ctk.CTkLabel(sec_f, text=f"{icon} {title}", font=("Segoe UI", 11, "bold"), text_color=THEME["accent"])
            h.pack(padx=10, pady=(8, 4), anchor="w")
            if not items:
                lbl = ctk.CTkLabel(sec_f, text="Ainda aprendendo...", font=("Segoe UI", 10, "italic"), text_color=THEME["text_muted"])
                lbl.pack(padx=12, pady=(0, 6), anchor="w")
            else:
                for it in items:
                    it_lbl = ctk.CTkLabel(sec_f, text=f"• {it}", font=("Segoe UI", 10), text_color=THEME["text_primary"], wraplength=310, justify="left")
                    it_lbl.pack(padx=12, pady=2, anchor="w")
            ctk.CTkFrame(sec_f, height=4, fg_color="transparent").pack()

        make_section("Contexto de Trabalho", "💼", mem.get("work_context", []))
        make_section("Gostos & Preferências", "⚙️", mem.get("preferences", []))
        make_section("Hábitos Pessoais", "👤", mem.get("personal_habits", []))
        make_section("Metas & Objetivos", "🎯", mem.get("goals", []))

        def add_fact():
            dialog = ctk.CTkInputDialog(text="O que você quer ensinar para a IA sobre você?", title="Ensinar Novo Fato")
            new_fact = dialog.get_input()
            if new_fact and new_fact.strip():
                self.ai_memory.add_fact_manually("preferences", new_fact.strip())
                win.destroy()
                self.show_feedback("Novo fato aprendido pela IA!")

        add_btn = ctk.CTkButton(
            scroll,
            text="＋ Ensinar Novo Fato para a IA",
            font=("Segoe UI", 11, "bold"),
            height=34,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=add_fact
        )
        add_btn.pack(fill="x", pady=(10, 8))

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

        # 1. Atualiza o Banner de Gamificação (Streaks & Meta de Foco)
        try:
            goal_info = self.storage.get_daily_goal_progress()
            streak = goal_info.get("streak_days", 0)
            if streak > 0:
                self.streak_label.configure(text=f"🔥 {streak} {'dia' if streak == 1 else 'dias'} seguidos!")
            else:
                self.streak_label.configure(text="🔥 Comece seu foco hoje!")

            pct = goal_info.get("percentage", 0)
            self.goal_label.configure(text=f"🎯 Hoje: {goal_info['today_formatted']} / {goal_info['goal_minutes']}m ({pct}%)")
            self.goal_bar.set(min(1.0, pct / 100.0))
        except Exception:
            pass

        pending_tasks = self.storage.get_pending_tasks()
        completed_tasks = self.storage.get_completed_tasks()

        # Filtra por categoria caso uma categoria específica esteja selecionada
        if self.selected_category and self.selected_category != "Todas":
            pending_tasks = [t for t in pending_tasks if str(t.get("category", "Geral")).lower() == self.selected_category.lower()]
            completed_tasks = [t for t in completed_tasks if str(t.get("category", "Geral")).lower() == self.selected_category.lower()]

        # Cabeçalho da Seção "A Fazer"
        pend_header = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
        pend_header.pack(fill="x", pady=(2, 6))

        cat_suffix = f" • {self.selected_category}" if self.selected_category != "Todas" else ""
        pend_title = ctk.CTkLabel(
            pend_header,
            text=f"A FAZER  ({len(pending_tasks)}){cat_suffix}",
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

        self._card_widgets.clear()

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
                elapsed = self.storage.get_task_current_elapsed(task)
                card = TaskItemCard(
                    self.scroll_container,
                    task=task,
                    on_toggle=self._handle_toggle_task,
                    on_delete=self._handle_delete_task,
                    on_timer_toggle=self._handle_timer_toggle,
                    font_size=self.font_size,
                    current_elapsed=elapsed
                )
                card.pack(fill="x", pady=3)
                self._card_widgets.append(card)

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

    def _start_stopwatch_loop(self):
        """Atualiza a contagem dos segundos ao vivo a cada 1 segundo para tarefas em foco."""
        try:
            for card in list(self._card_widgets):
                if card.winfo_exists() and card.task.get("timer_running"):
                    elapsed = self.storage.get_task_current_elapsed(card.task)
                    card.update_timer_display(elapsed)
        except Exception:
            pass
        self._stopwatch_timer = self.after(1000, self._start_stopwatch_loop)

    def _set_category_filter(self, category: str):
        """Filtra as tarefas exibidas por categoria selecionada."""
        self.selected_category = category
        for cat_name, btn in getattr(self, "category_buttons", {}).items():
            if cat_name == category:
                btn.configure(fg_color=THEME["accent"], text_color="#ffffff")
            else:
                btn.configure(fg_color=THEME["card_bg"], text_color=THEME["text_secondary"])
        self._refresh_tasks_view()

    def _check_reminders(self):
        """Verifica se há lembretes agendados para o horário atual."""
        try:
            due_tasks = self.storage.get_due_reminders()
            for t in due_tasks:
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass
                self.storage.mark_reminded(t["id"])
                self.show_feedback(f"⏰ LEMBRETE: {t['title']}!", is_error=False)
                self._refresh_tasks_view()
        except Exception:
            pass
        self.after(15000, self._check_reminders)

    def _manual_add_task(self):
        title = self.input_entry.get().strip()
        if not title:
            return
        
        priority_map = {"Média": "media", "Alta": "alta", "Baixa": "baixa"}
        selected_prio = priority_map.get(self.priority_menu.get(), "media")
        selected_cat = self.category_menu.get() if hasattr(self, "category_menu") else "Geral"

        self.storage.add_task(title=title, priority=selected_prio, category=selected_cat)
        self.input_entry.delete(0, "end")
        self._refresh_tasks_view()
        self.show_feedback(f"Tarefa adicionada em {selected_cat}!")

    def _handle_timer_toggle(self, task_id: str):
        updated = self.storage.toggle_timer(task_id)
        self._refresh_tasks_view()
        if updated:
            if updated.get("timer_running"):
                self.show_feedback("⏱️ Foco iniciado! Contando tempo...")
            else:
                self.show_feedback("⏸️ Tarefa pausada.")

    def _handle_toggle_task(self, task_id: str):
        updated = self.storage.toggle_task(task_id)
        self._refresh_tasks_view()
        if updated:
            if updated.get("completed"):
                dur = updated.get("completed_duration")
                msg = f"🎉 Feito em {dur}! Parabéns!" if dur else "Tarefa concluída!"
            else:
                msg = "Tarefa reaberta!"
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
            category = result.get("category", "Geral")
            due_time = result.get("due_time")
            feedback = result.get("feedback_message", "Comando executado!")

            # Executa a ação no Storage
            if action == "add":
                if task_title:
                    self.storage.add_task(title=task_title, priority=priority, due_time=due_time, category=category)
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

    def _show_mobile_qr_dialog(self):
        """Abre janela com o QR Code para abrir o app no smartphone."""
        top = ctk.CTkToplevel(self)
        top.title("📱 Voice Tasks no Celular")
        top.geometry("340x430")
        top.resizable(False, False)
        top.configure(fg_color=THEME["bg_dark"])
        top.attributes("-topmost", True)

        title = ctk.CTkLabel(
            top,
            text="📱 Voice Tasks no Celular",
            font=("Segoe UI", 15, "bold"),
            text_color=THEME["text_primary"]
        )
        title.pack(pady=(16, 4))

        sub = ctk.CTkLabel(
            top,
            text="Aponte a câmera do seu celular para o QR Code abaixo:",
            font=("Segoe UI", 11),
            text_color=THEME["text_muted"],
            wraplength=280
        )
        sub.pack(pady=(0, 10))

        # Carrega imagem do QR Code
        from config import BASE_DIR
        from PIL import Image
        qr_path = BASE_DIR / "mobile_qr.png"

        if qr_path.is_file():
            pil_img = Image.open(qr_path)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(190, 190))
            qr_label = ctk.CTkLabel(top, image=ctk_img, text="")
            qr_label.pack(pady=6)

        url_str = "https://eullon1234-creator.github.io/voice-tasks-app/"

        def copy_url():
            top.clipboard_clear()
            top.clipboard_append(url_str)
            btn_copy.configure(text="✅ Link Copiado!")
            top.after(2000, lambda: btn_copy.configure(text="📋 Copiar Link"))

        btn_copy = ctk.CTkButton(
            top,
            text="📋 Copiar Link",
            font=("Segoe UI", 11, "bold"),
            height=30,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=copy_url
        )
        btn_copy.pack(pady=(8, 4))

        hint = ctk.CTkLabel(
            top,
            text="💡 Dica: No celular, toque nos 3 pontinhos e escolha 'Adicionar à tela inicial' para instalar como app!",
            font=("Segoe UI", 9, "italic"),
            text_color="#818cf8",
            wraplength=280
        )
        hint.pack(pady=(4, 12))
