import customtkinter as ctk
from typing import Callable, Optional, Dict, Any
from config import THEME, PRIORITY_COLORS

class PriorityBadge(ctk.CTkFrame):
    """Badge colorido indicador de prioridade (Alta / Média / Baixa)."""
    def __init__(self, master, priority: str = "media", **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        norm_priority = (priority or "media").lower()
        cfg = PRIORITY_COLORS.get(norm_priority, PRIORITY_COLORS["media"])
        
        self.configure(
            fg_color=cfg["bg"],
            border_color=cfg["border"],
            border_width=1
        )
        
        label_text = norm_priority.upper()
        self.label = ctk.CTkLabel(
            self,
            text=label_text,
            font=("Segoe UI", 10, "bold"),
            text_color=cfg["fg"],
            padx=7,
            pady=1
        )
        self.label.pack()

class TaskItemCard(ctk.CTkFrame):
    """Card individual de tarefa com checkbox, badge, horário e botão de remoção."""
    def __init__(
        self,
        master,
        task: Dict[str, Any],
        on_toggle: Callable[[str], None],
        on_delete: Callable[[str], None],
        on_timer_toggle: Optional[Callable[[str], None]] = None,
        font_size: int = 15,
        current_elapsed: int = 0,
        **kwargs
    ):
        super().__init__(master, corner_radius=8, **kwargs)
        self.task = task
        self.task_id = task.get("id", "")
        self.completed = task.get("completed", False)
        self.on_toggle = on_toggle
        self.on_delete = on_delete
        self.on_timer_toggle = on_timer_toggle
        self.font_size = font_size
        self.current_elapsed = current_elapsed

        # Cores conforme estado
        bg_color = THEME["card_bg"] if not self.completed else "#18181b"
        border_color = THEME["border"] if not self.completed else "#27272a"
        self.configure(
            fg_color=bg_color,
            border_width=1,
            border_color=border_color
        )

        # Layout interno em grid
        self.grid_columnconfigure(1, weight=1)

        # 1. Checkbox
        box_size = max(18, min(24, font_size + 4))
        self.check_var = ctk.BooleanVar(value=self.completed)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.check_var,
            width=box_size,
            height=box_size,
            checkbox_width=box_size,
            checkbox_height=box_size,
            corner_radius=5,
            border_color=THEME["accent"] if not self.completed else THEME["text_muted"],
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._handle_toggle
        )
        self.checkbox.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=8, sticky="w")

        # 2. Informações de Título
        title_color = THEME["text_primary"] if not self.completed else THEME["text_muted"]
        font_style = ("Segoe UI", self.font_size) if not self.completed else ("Segoe UI", self.font_size, "overstrike")
        
        self.title_label = ctk.CTkLabel(
            self,
            text=task.get("title", ""),
            font=font_style,
            text_color=title_color,
            anchor="w",
            wraplength=240,
            justify="left"
        )
        self.title_label.grid(row=0, column=1, padx=(0, 6), pady=(6, 2), sticky="w")

        # 3. Sublinha: Metadados (Prioridade, Horário e Cronômetro / Tempo Gasto)
        meta_frame = ctk.CTkFrame(self, fg_color="transparent")
        meta_frame.grid(row=1, column=1, padx=(0, 6), pady=(0, 6), sticky="w")

        meta_font_size = max(10, self.font_size - 4)

        if not self.completed:
            # Badge de Prioridade
            badge = PriorityBadge(meta_frame, priority=task.get("priority", "media"))
            badge.pack(side="left", padx=(0, 6))

            # Horário / Due Time
            due_time = task.get("due_time")
            if due_time:
                time_label = ctk.CTkLabel(
                    meta_frame,
                    text=f"🕒 {due_time}",
                    font=("Segoe UI", meta_font_size),
                    text_color=THEME["text_muted"]
                )
                time_label.pack(side="left", padx=(0, 6))

            # Botão de Cronômetro de Foco
            from storage import format_stopwatch
            is_running = task.get("timer_running", False)
            btn_text = f"⏸ {format_stopwatch(self.current_elapsed)}" if is_running else (
                f"▶ Continuar ({format_stopwatch(self.current_elapsed)})" if self.current_elapsed > 0 else "▶ Iniciar Tarefa"
            )
            btn_bg = "#065f46" if is_running else "#232733"
            btn_fg = "#34d399" if is_running else "#a5b4fc"
            btn_border = "#10b981" if is_running else "#373e51"

            self.timer_btn = ctk.CTkButton(
                meta_frame,
                text=btn_text,
                font=("Segoe UI", meta_font_size, "bold"),
                height=22,
                corner_radius=6,
                fg_color=btn_bg,
                hover_color="#047857" if is_running else "#2d3345",
                text_color=btn_fg,
                border_width=1,
                border_color=btn_border,
                command=self._handle_timer_toggle
            )
            self.timer_btn.pack(side="left")
        else:
            # Se concluída: Exibe o tempo total gasto na tarefa
            duration = task.get("completed_duration")
            if duration:
                dur_badge = ctk.CTkFrame(
                    meta_frame,
                    corner_radius=6,
                    fg_color="#132e22",
                    border_color="#059669",
                    border_width=1
                )
                dur_badge.pack(side="left")
                dur_label = ctk.CTkLabel(
                    dur_badge,
                    text=f"⏱️ Feito em {duration}",
                    font=("Segoe UI", meta_font_size, "bold"),
                    text_color="#34d399",
                    padx=6,
                    pady=1
                )
                dur_label.pack()

        # 4. Botão Excluir (Discreto)
        self.del_btn = ctk.CTkButton(
            self,
            text="✕",
            font=("Segoe UI", 11, "bold"),
            width=24,
            height=24,
            corner_radius=12,
            fg_color="transparent",
            text_color=THEME["text_muted"],
            hover_color="#381919",
            command=self._handle_delete
        )
        self.del_btn.grid(row=0, column=2, rowspan=2, padx=(2, 8), pady=8, sticky="e")

    def update_timer_display(self, elapsed: int):
        """Atualiza o mostrador do cronômetro ao vivo."""
        if hasattr(self, "timer_btn") and self.task.get("timer_running"):
            from storage import format_stopwatch
            self.current_elapsed = elapsed
            self.timer_btn.configure(text=f"⏸ {format_stopwatch(elapsed)}")

    def _handle_toggle(self):
        if self.on_toggle:
            self.on_toggle(self.task_id)

    def _handle_timer_toggle(self):
        if self.on_timer_toggle:
            self.on_timer_toggle(self.task_id)

    def _handle_delete(self):
        if self.on_delete:
            self.on_delete(self.task_id)


class PulsingMicButton(ctk.CTkButton):
    """
    Botão de microfone com pulso animado quando em gravação.
    """
    def __init__(self, master, on_click: Callable[[], None], **kwargs):
        super().__init__(
            master,
            text="🎙",
            font=("Segoe UI Emoji", 18, "bold"),
            width=48,
            height=48,
            corner_radius=24,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=on_click,
            **kwargs
        )
        self.on_click = on_click
        self.is_animating = False
        self._pulse_step = 0
        self._pulse_colors = [
            "#ef4444", "#dc2626", "#b91c1c", "#991b1b", "#b91c1c", "#dc2626"
        ]

    def set_recording_state(self, recording: bool):
        if recording:
            self.is_animating = True
            self.configure(fg_color="#ef4444", hover_color="#dc2626", text="⏹")
            self._animate_pulse()
        else:
            self.is_animating = False
            self.configure(fg_color=THEME["accent"], hover_color=THEME["accent_hover"], text="🎙")

    def _animate_pulse(self):
        if not self.is_animating:
            return
        color = self._pulse_colors[self._pulse_step % len(self._pulse_colors)]
        self.configure(fg_color=color)
        self._pulse_step += 1
        self.after(140, self._animate_pulse)
