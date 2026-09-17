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
        **kwargs
    ):
        super().__init__(master, corner_radius=8, **kwargs)
        self.task = task
        self.task_id = task.get("id", "")
        self.completed = task.get("completed", False)
        self.on_toggle = on_toggle
        self.on_delete = on_delete

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
        self.check_var = ctk.BooleanVar(value=self.completed)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.check_var,
            width=20,
            height=20,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=5,
            border_color=THEME["accent"] if not self.completed else THEME["text_muted"],
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._handle_toggle
        )
        self.checkbox.grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=8, sticky="w")

        # 2. Informações de Título
        title_color = THEME["text_primary"] if not self.completed else THEME["text_muted"]
        font_style = ("Segoe UI", 12) if not self.completed else ("Segoe UI", 12, "overstrike")
        
        self.title_label = ctk.CTkLabel(
            self,
            text=task.get("title", ""),
            font=font_style,
            text_color=title_color,
            anchor="w",
            wraplength=220,
            justify="left"
        )
        self.title_label.grid(row=0, column=1, padx=(0, 6), pady=(6, 2), sticky="w")

        # 3. Sublinha: Badge de Prioridade e Due Time
        meta_frame = ctk.CTkFrame(self, fg_color="transparent")
        meta_frame.grid(row=1, column=1, padx=(0, 6), pady=(0, 6), sticky="w")

        if not self.completed:
            badge = PriorityBadge(meta_frame, priority=task.get("priority", "media"))
            badge.pack(side="left", padx=(0, 6))

        due_time = task.get("due_time")
        if due_time:
            time_label = ctk.CTkLabel(
                meta_frame,
                text=f"🕒 {due_time}",
                font=("Segoe UI", 10),
                text_color=THEME["text_muted"]
            )
            time_label.pack(side="left")

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

    def _handle_toggle(self):
        if self.on_toggle:
            self.on_toggle(self.task_id)

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
