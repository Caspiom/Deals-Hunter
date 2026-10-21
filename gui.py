from __future__ import annotations

import asyncio
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from config import load_settings, update_env_values
from ctl import (
    SERVICE_NAME,
    is_service_active,
    select_only_item,
    set_primary_query,
    toggle_item_active,
)
from db import Database
from main import DealHunterApp
from notifier import send_desktop_notification


class ControlPanelWindow:
    """Painel Gráfico Multiplataforma (Linux KDE/GNOME/XFCE/WM & Windows) para o Deals Hunter."""

    BG_MAIN = "#1e1e2e"
    BG_CARD = "#28283d"
    FG_TEXT = "#cdd6f4"
    FG_MUTED = "#a6adc8"
    ACCENT = "#89b4fa"
    GREEN = "#a6e3a1"
    RED = "#f38ba8"

    def __init__(
        self,
        external_worker_state: Callable[[], bool] | None = None,
        external_worker_toggle: Callable[[], bool] | None = None,
    ) -> None:
        self.external_worker_state = external_worker_state
        self.external_worker_toggle = external_worker_toggle
        self.settings = load_settings(require_telegram=False)
        self.db = Database(self.settings.db_path)

        self.root = tk.Tk()
        self.root.title("Deals Hunter — Painel de Controle")
        self.root.geometry("520x650")
        self.root.configure(bg=self.BG_MAIN)
        self.root.minsize(480, 600)

        self._build_ui()
        self.refresh_ui()

    def _is_running(self) -> bool:
        if self.external_worker_state is not None:
            return self.external_worker_state()
        if platform.system().lower() == "linux":
            return is_service_active()
        return False

    def _toggle_running(self) -> None:
        if self.external_worker_toggle is not None:
            self.external_worker_toggle()
        elif platform.system().lower() == "linux":
            target = "stop" if is_service_active() else "start"
            subprocess.run(["systemctl", "--user", target, SERVICE_NAME], check=False)
        self.refresh_ui()

    def _build_ui(self) -> None:
        # Cabeçalho + Status do Bot
        header_frame = tk.Frame(self.root, bg=self.BG_CARD, padx=14, pady=12)
        header_frame.pack(fill=tk.X, padx=14, pady=(14, 8))

        left_header = tk.Frame(header_frame, bg=self.BG_CARD)
        left_header.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_status = tk.Label(
            left_header,
            text="🟢 Bot Monitorando",
            font=("Sans", 13, "bold"),
            bg=self.BG_CARD,
            fg=self.GREEN,
            anchor="w",
        )
        self.lbl_status.pack(fill=tk.X)

        self.lbl_summary = tk.Label(
            left_header,
            text="Alvo atual: ...",
            font=("Sans", 10),
            bg=self.BG_CARD,
            fg=self.FG_MUTED,
            anchor="w",
        )
        self.lbl_summary.pack(fill=tk.X, pady=(2, 0))

        self.btn_toggle_service = tk.Button(
            header_frame,
            text="Desligar Bot",
            font=("Sans", 10, "bold"),
            bg=self.RED,
            fg="#11111b",
            activebackground=self.ACCENT,
            relief=tk.FLAT,
            padx=12,
            pady=6,
            command=self._toggle_running,
        )
        self.btn_toggle_service.pack(side=tk.RIGHT)

        # Seção: Escolher / Alterar Produto Pesquisado
        search_frame = tk.Frame(self.root, bg=self.BG_CARD, padx=14, pady=12)
        search_frame.pack(fill=tk.X, padx=14, pady=6)

        tk.Label(
            search_frame,
            text="🎯 Escolher ou Adicionar Produto Pesquisado (Nome | Preço Máx):",
            font=("Sans", 10, "bold"),
            bg=self.BG_CARD,
            fg=self.FG_TEXT,
            anchor="w",
        ).pack(fill=tk.X)

        self.entry_query = tk.Entry(
            search_frame,
            font=("Sans", 11),
            bg="#181825",
            fg=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief=tk.FLAT,
        )
        self.entry_query.pack(fill=tk.X, pady=8, ipady=6)
        self.entry_query.insert(0, "fifine am8t | 285")
        self.entry_query.bind("<Return>", lambda _e: self._on_set_exclusive())

        btn_row = tk.Frame(search_frame, bg=self.BG_CARD)
        btn_row.pack(fill=tk.X)

        tk.Button(
            btn_row,
            text="🎯 Pesquisar Só Este",
            font=("Sans", 10, "bold"),
            bg=self.ACCENT,
            fg="#11111b",
            relief=tk.FLAT,
            padx=10,
            pady=5,
            command=self._on_set_exclusive,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        tk.Button(
            btn_row,
            text="➕ Adicionar à Lista",
            font=("Sans", 10),
            bg="#45475a",
            fg=self.FG_TEXT,
            relief=tk.FLAT,
            padx=10,
            pady=5,
            command=self._on_add_item,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

        # Seção: Lista de Produtos (Watchlist)
        list_frame = tk.Frame(self.root, bg=self.BG_CARD, padx=14, pady=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)

        top_list_row = tk.Frame(list_frame, bg=self.BG_CARD)
        top_list_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            top_list_row,
            text="📋 Produtos Cadastrados (Watchlist):",
            font=("Sans", 10, "bold"),
            bg=self.BG_CARD,
            fg=self.FG_TEXT,
        ).pack(side=tk.LEFT)

        tk.Button(
            top_list_row,
            text="🔍 Buscar Agora",
            font=("Sans", 9, "bold"),
            bg=self.GREEN,
            fg="#11111b",
            relief=tk.FLAT,
            padx=8,
            pady=2,
            command=self._on_check_now,
        ).pack(side=tk.RIGHT)

        self.items_container = tk.Frame(list_frame, bg=self.BG_CARD)
        self.items_container.pack(fill=tk.BOTH, expand=True)

        # Seção: Notificações no PC & Telegram Opcional (@BotFather)
        cfg_frame = tk.Frame(self.root, bg=self.BG_CARD, padx=14, pady=10)
        cfg_frame.pack(fill=tk.X, padx=14, pady=(6, 14))

        tk.Label(
            cfg_frame,
            text="🔔 Notificações no PC & Telegram Opcional (@BotFather):",
            font=("Sans", 10, "bold"),
            bg=self.BG_CARD,
            fg=self.FG_TEXT,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        chk_row = tk.Frame(cfg_frame, bg=self.BG_CARD)
        chk_row.pack(fill=tk.X)

        self.var_desktop_notif = tk.BooleanVar(value=self.settings.desktop_notifications)
        tk.Checkbutton(
            chk_row,
            text="Notificar direto no PC (Nativo)",
            variable=self.var_desktop_notif,
            bg=self.BG_CARD,
            fg=self.FG_TEXT,
            selectcolor="#181825",
            activebackground=self.BG_CARD,
            activeforeground=self.FG_TEXT,
        ).pack(side=tk.LEFT)

        tk.Button(
            chk_row,
            text="🔔 Testar Alerta PC",
            font=("Sans", 9),
            bg="#45475a",
            fg=self.FG_TEXT,
            relief=tk.FLAT,
            padx=8,
            pady=2,
            command=self._on_test_pc_notify,
        ).pack(side=tk.RIGHT)

        tg_grid = tk.Frame(cfg_frame, bg=self.BG_CARD)
        tg_grid.pack(fill=tk.X, pady=(8, 4))

        tk.Label(
            tg_grid,
            text="Bot Token (opcional):",
            font=("Sans", 9),
            bg=self.BG_CARD,
            fg=self.FG_MUTED,
        ).grid(row=0, column=0, sticky="w", pady=2)

        self.entry_token = tk.Entry(
            tg_grid,
            font=("Sans", 9),
            bg="#181825",
            fg=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief=tk.FLAT,
        )
        self.entry_token.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2, ipady=3)
        self.entry_token.insert(0, self.settings.telegram_bot_token)

        tk.Label(
            tg_grid,
            text="Chat ID (opcional):",
            font=("Sans", 9),
            bg=self.BG_CARD,
            fg=self.FG_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=2)

        self.entry_chat_id = tk.Entry(
            tg_grid,
            font=("Sans", 9),
            bg="#181825",
            fg=self.FG_TEXT,
            insertbackground=self.FG_TEXT,
            relief=tk.FLAT,
        )
        self.entry_chat_id.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2, ipady=3)
        if self.settings.allowed_chat_id:
            self.entry_chat_id.insert(0, str(self.settings.allowed_chat_id))

        tg_grid.columnconfigure(1, weight=1)

        tk.Button(
            cfg_frame,
            text="💾 Salvar Configurações",
            font=("Sans", 9, "bold"),
            bg=self.ACCENT,
            fg="#11111b",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            command=self._on_save_settings,
        ).pack(fill=tk.X, pady=(6, 0))

    def refresh_ui(self) -> None:
        running = self._is_running()
        items = self.db.list_watchlist()
        active_queries = [it.query for it in items if it.active]
        summary = ", ".join(active_queries) if active_queries else "Nenhum produto ativo"

        if running:
            self.lbl_status.config(text="🟢 Bot Monitorando em Background", fg=self.GREEN)
            self.btn_toggle_service.config(text="⏹ Desligar Bot", bg=self.RED)
        else:
            self.lbl_status.config(text="🔴 Bot Parado", fg=self.RED)
            self.btn_toggle_service.config(text="▶ Ligar Bot", bg=self.GREEN)

        self.lbl_summary.config(text=f"Pesquisando: {summary}")

        for child in self.items_container.winfo_children():
            child.destroy()

        if not items:
            tk.Label(
                self.items_container,
                text="Nenhum produto na lista. Adicione um acima!",
                bg=self.BG_CARD,
                fg=self.FG_MUTED,
            ).pack(pady=12)
            return

        for item in items:
            row = tk.Frame(self.items_container, bg="#181825", padx=8, pady=6)
            row.pack(fill=tk.X, pady=3)

            badge = "🟢" if item.active else "⚪"
            lbl = tk.Label(
                row,
                text=f"{badge} {item.query}  (<= R$ {item.max_price:.0f})",
                font=("Sans", 10, "bold" if item.active else "normal"),
                bg="#181825",
                fg=self.GREEN if item.active else self.FG_MUTED,
                anchor="w",
            )
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            tk.Button(
                row,
                text="Focar",
                font=("Sans", 8, "bold"),
                bg=self.ACCENT,
                fg="#11111b",
                relief=tk.FLAT,
                padx=6,
                command=lambda i=item.id: self._on_focus_item(i),
            ).pack(side=tk.LEFT, padx=2)

            tk.Button(
                row,
                text="Pausar" if item.active else "Ativar",
                font=("Sans", 8),
                bg="#45475a",
                fg=self.FG_TEXT,
                relief=tk.FLAT,
                padx=6,
                command=lambda i=item.id: self._on_toggle_item(i),
            ).pack(side=tk.LEFT, padx=2)

            tk.Button(
                row,
                text="🗑",
                font=("Sans", 8),
                bg=self.RED,
                fg="#11111b",
                relief=tk.FLAT,
                padx=6,
                command=lambda i=item.id: self._on_delete_item(i),
            ).pack(side=tk.LEFT, padx=(2, 0))

    def _on_set_exclusive(self) -> None:
        raw = self.entry_query.get().strip()
        if raw:
            set_primary_query(self.db, raw, exclusive=True)
            self.refresh_ui()

    def _on_add_item(self) -> None:
        raw = self.entry_query.get().strip()
        if raw:
            set_primary_query(self.db, raw, exclusive=False)
            self.refresh_ui()

    def _on_focus_item(self, item_id: int) -> None:
        select_only_item(self.db, item_id)
        self.refresh_ui()

    def _on_toggle_item(self, item_id: int) -> None:
        toggle_item_active(self.db, item_id)
        self.refresh_ui()

    def _on_delete_item(self, item_id: int) -> None:
        self.db.delete_watchlist_item(item_id)
        self.refresh_ui()

    def _on_test_pc_notify(self) -> None:
        send_desktop_notification(
            title="🚨 Deals Hunter — Teste no PC",
            body="Suas notificações nativas direto no computador estão funcionando!",
        )

    def _on_save_settings(self) -> None:
        updates = {
            "DESKTOP_NOTIFICATIONS": "true" if self.var_desktop_notif.get() else "false",
            "TELEGRAM_BOT_TOKEN": self.entry_token.get().strip(),
            "ALLOWED_CHAT_ID": self.entry_chat_id.get().strip() or "0",
        }
        update_env_values(updates)
        self.settings = load_settings(require_telegram=False)
        messagebox.showinfo(
            "Deals Hunter",
            "Configurações salvas no arquivo .env com sucesso!",
        )

    def _on_check_now(self) -> None:
        def _worker() -> None:
            settings = load_settings(require_telegram=False)
            db = Database(settings.db_path)
            app = DealHunterApp(settings=settings, db=db)
            total, found = asyncio.run(app.run_scrape_cycle(notify=True))
            send_desktop_notification(
                title="🔍 Deals Hunter — Busca Concluída",
                body=f"{total} produto(s) verificado(s), {found} nova(s) oferta(s) encontrada(s).",
            )

        threading.Thread(target=_worker, daemon=True).start()

    def run(self) -> None:
        self.root.mainloop()


def launch_control_panel(
    external_worker_state: Callable[[], bool] | None = None,
    external_worker_toggle: Callable[[], bool] | None = None,
) -> None:
    panel = ControlPanelWindow(
        external_worker_state=external_worker_state,
        external_worker_toggle=external_worker_toggle,
    )
    panel.run()


if __name__ == "__main__":
    launch_control_panel()
