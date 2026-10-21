from __future__ import annotations

import asyncio
import platform
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
from typing import Callable

from config import load_settings, update_env_values
from ctl import (
    HELP_DOC_URL,
    SERVICE_NAME,
    format_ago,
    format_brl,
    format_saving,
    is_service_active,
    select_only_item,
    set_primary_query,
    toggle_item_active,
)
from db import Database
from main import DealHunterApp
from notifier import open_url_in_browser, send_desktop_notification
from theme import Palette, load_palette


class Switch(tk.Canvas):
    """Switch estilo Material 3 desenhado no Canvas (o tkinter não tem um nativo)."""

    def __init__(
        self,
        master: tk.Misc,
        palette: Palette,
        on: bool,
        command: Callable[[], None] | None,
        bg: str,
        width: int = 44,
        height: int = 24,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            takefocus=1,
        )
        self.palette = palette
        self.on = on
        self.command = command
        self.w = width
        self.h = height
        self.bind("<Button-1>", self._activate)
        self.bind("<space>", self._activate)
        self.bind("<Return>", self._activate)
        self._draw()

    def _activate(self, _event: tk.Event | None = None) -> None:
        if self.command:
            self.command()

    def _pill(self, x0: float, y0: float, x1: float, y1: float, color: str) -> None:
        r = (y1 - y0) / 2
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=color, outline=color)
        self.create_oval(x1 - 2 * r, y0, x1, y1, fill=color, outline=color)
        self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, outline=color)

    def _draw(self) -> None:
        self.delete("all")
        p = self.palette
        w, h = self.w, self.h
        border = p.primary if self.on else p.outline
        track = p.primary if self.on else p.surface_container_highest
        self._pill(0, 0, w - 1, h - 1, border)
        self._pill(2, 2, w - 3, h - 3, track)
        knob = p.on_primary if self.on else p.outline
        d = h - 8 if self.on else h - 12
        cx = w - h / 2 if self.on else h / 2
        self.create_oval(cx - d / 2, h / 2 - d / 2, cx + d / 2, h / 2 + d / 2, fill=knob, outline=knob)


class ScrollArea(tk.Frame):
    """Área com rolagem pela roda do mouse para as listas de promoções/watchlist."""

    def __init__(self, master: tk.Misc, bg: str) -> None:
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._window, width=e.width),
        )
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _event: tk.Event) -> None:
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", lambda _e: self._scroll(-1))
        self.bind_all("<Button-5>", lambda _e: self._scroll(1))

    def _unbind_wheel(self, _event: tk.Event) -> None:
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _on_wheel(self, event: tk.Event) -> None:
        delta = event.delta if abs(event.delta) < 120 else event.delta // 120
        self._scroll(-delta)

    def _scroll(self, units: int) -> None:
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")


class ControlPanelWindow:
    """
    Painel Gráfico Multiplataforma (Linux KDE/GNOME/XFCE/WM, Windows e macOS) para o Deals Hunter.

    Mesmo layout do plugin do Noctalia: cabeçalho com switch → adicionar produto →
    abas (Promoções | Watchlist | Ajustes) → rodapé com "Buscar agora".
    As cores vêm de `theme.load_palette()` (matugen/Noctalia, tema do sistema ou Windows).
    """

    WIDTH = 420
    HEIGHT = 640

    def __init__(
        self,
        external_worker_state: Callable[[], bool] | None = None,
        external_worker_toggle: Callable[[], bool] | None = None,
    ) -> None:
        self.external_worker_state = external_worker_state
        self.external_worker_toggle = external_worker_toggle
        self.settings = load_settings(require_telegram=False)
        self.db = Database(self.settings.db_path)
        self.p = load_palette()

        self.active_tab = "deals"
        self.busy = False
        self.footer_message = ""

        self.root = tk.Tk()
        self.root.title("Deals Hunter")
        self.root.configure(bg=self.p.surface)
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.root.resizable(False, False)
        self.family = self._pick_font_family()

        self._build_ui()
        self.refresh_ui()

    # ------------------------------------------------------------------ helpers

    def _pick_font_family(self) -> str:
        available = set(tkfont.families(self.root))
        for family in self.p.fonts:
            if family in available:
                return family
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def font(self, size: int, weight: str = "normal") -> tuple[str, int, str]:
        return (self.family, size, weight)

    def _button(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        bg: str,
        fg: str,
        size: int = 10,
        weight: str = "bold",
        padx: int = 12,
        pady: int = 6,
    ) -> tk.Button:
        return tk.Button(
            master,
            text=text,
            command=command,
            font=self.font(size, weight),
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            padx=padx,
            pady=pady,
            cursor="hand2",
        )

    def _entry(self, master: tk.Misc, size: int = 11) -> tk.Entry:
        p = self.p
        return tk.Entry(
            master,
            font=self.font(size),
            bg=p.field,
            fg=p.on_surface,
            insertbackground=p.on_surface,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=p.outline_variant,
            highlightcolor=p.primary,
        )

    def _label(
        self,
        master: tk.Misc,
        text: str,
        bg: str,
        fg: str | None = None,
        size: int = 9,
        weight: str = "normal",
    ) -> tk.Label:
        return tk.Label(
            master,
            text=text,
            bg=bg,
            fg=fg or self.p.on_surface_variant,
            font=self.font(size, weight),
            anchor="w",
            justify=tk.LEFT,
        )

    def _checkbox(self, master: tk.Misc, text: str, variable: tk.BooleanVar, bg: str) -> tk.Checkbutton:
        p = self.p
        return tk.Checkbutton(
            master,
            text=text,
            variable=variable,
            font=self.font(9),
            bg=bg,
            fg=p.on_surface_variant,
            selectcolor=p.field,
            activebackground=bg,
            activeforeground=p.on_surface,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )

    # ------------------------------------------------------------------ layout

    def _build_ui(self) -> None:
        p = self.p
        body = tk.Frame(self.root, bg=p.surface, padx=16, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        # Cabeçalho: ícone + título/status + switch liga/desliga + fechar
        header = tk.Frame(body, bg=p.surface)
        header.pack(fill=tk.X)

        icon = tk.Canvas(header, width=40, height=40, bg=p.surface, highlightthickness=0, bd=0)
        icon.create_rectangle(0, 0, 40, 40, fill=p.primary_container, outline=p.primary_container)
        icon.create_polygon(
            11, 13, 22, 13, 30, 20, 22, 27, 11, 27,
            fill="", outline=p.on_primary_container, width=2, joinstyle=tk.ROUND,
        )
        icon.create_oval(14, 18, 18, 22, fill=p.on_primary_container, outline="")
        icon.pack(side=tk.LEFT)

        titles = tk.Frame(header, bg=p.surface)
        titles.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)
        self._label(titles, "Deal Hunter", p.surface, p.on_surface, 12, "bold").pack(fill=tk.X)
        status_row = tk.Frame(titles, bg=p.surface)
        status_row.pack(fill=tk.X)
        self.status_dot = tk.Canvas(status_row, width=8, height=8, bg=p.surface, highlightthickness=0, bd=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 6))
        self.lbl_status = self._label(status_row, "", p.surface)
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X)

        self._button(
            header, "✕", self.root.destroy, p.surface, p.on_surface_variant, size=11, weight="normal", padx=8, pady=2
        ).pack(side=tk.RIGHT)
        self.switch_slot = tk.Frame(header, bg=p.surface)
        self.switch_slot.pack(side=tk.RIGHT, padx=(0, 4))

        # Adicionar produto
        add_card = tk.Frame(body, bg=p.surface_container, padx=12, pady=12)
        add_card.pack(fill=tk.X, pady=(12, 0))

        fields = tk.Frame(add_card, bg=p.surface_container)
        fields.pack(fill=tk.X)
        fields.columnconfigure(0, weight=1)

        self._label(fields, "Produto", p.surface_container, size=9, weight="bold").grid(row=0, column=0, sticky="w")
        self._label(fields, "Preço máx. (R$)", p.surface_container, size=9, weight="bold").grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        self.entry_query = self._entry(fields)
        self.entry_query.grid(row=1, column=0, sticky="ew", pady=(4, 0), ipady=6)
        self.entry_query.bind("<Return>", lambda _e: self._on_add_product())
        self.entry_price = self._entry(fields)
        self.entry_price.configure(width=10)
        self.entry_price.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 0), ipady=6)
        self.entry_price.bind("<Return>", lambda _e: self._on_add_product())
        self._button(fields, "+", self._on_add_product, p.primary, p.on_primary, size=13, padx=12, pady=1).grid(
            row=1, column=2, sticky="ns", padx=(8, 0), pady=(4, 0)
        )

        self.var_exclusive = tk.BooleanVar(value=False)
        self._checkbox(add_card, "Monitorar só este (pausa os outros)", self.var_exclusive, p.surface_container).pack(
            anchor="w", pady=(10, 0)
        )

        # Aviso "pausado" (só aparece com o bot desligado)
        self.paused_notice = tk.Frame(
            body,
            bg=p.surface_container_high,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=p.outline_variant,
        )
        notice_text = tk.Frame(self.paused_notice, bg=p.surface_container_high)
        notice_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._label(notice_text, "Monitoramento pausado", p.surface_container_high, p.on_surface, 10, "bold").pack(
            fill=tk.X
        )
        self._label(notice_text, "Sua watchlist continua salva.", p.surface_container_high).pack(fill=tk.X)
        self._button(self.paused_notice, "Ligar", self._toggle_running, p.primary, p.on_primary).pack(side=tk.RIGHT)

        # Abas
        self.tabs_bar = tk.Frame(body, bg=p.surface_container, padx=4, pady=4)
        self.tabs_bar.pack(fill=tk.X, pady=(12, 0))
        self.tab_buttons: dict[str, tk.Button] = {}
        for tab_id in ("deals", "watchlist"):
            btn = self._button(
                self.tabs_bar,
                "",
                lambda t=tab_id: self._select_tab(t),
                p.surface_container,
                p.on_surface_variant,
                pady=6,
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.tab_buttons[tab_id] = btn

        # Rodapé
        footer = tk.Frame(body, bg=p.surface)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(footer, bg=p.outline_variant, height=1).pack(fill=tk.X, pady=(0, 12))
        footer_row = tk.Frame(footer, bg=p.surface)
        footer_row.pack(fill=tk.X)
        self.lbl_footer = self._label(footer_row, "", p.surface)
        self.lbl_footer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_help = self._button(
            footer_row,
            "?",
            lambda: open_url_in_browser(HELP_DOC_URL),
            p.surface_container,
            p.on_surface_variant,
            padx=9,
            pady=6,
        )
        self.btn_help.pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_settings = self._button(
            footer_row,
            "⚙",
            lambda: self._select_tab("deals" if self.active_tab == "settings" else "settings"),
            p.surface_container,
            p.on_surface_variant,
            padx=9,
            pady=6,
        )
        self.btn_settings.pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_check = self._button(
            footer_row, "⟳  Buscar agora", self._on_check_now, p.secondary_container, p.on_secondary_container
        )
        self.btn_check.pack(side=tk.RIGHT)

        # Conteúdo das abas
        self.content = ScrollArea(body, p.surface)
        self.content.pack(fill=tk.BOTH, expand=True, pady=12)

        self._build_settings_frame()

    def _build_settings_frame(self) -> None:
        """Ajustes: notificações no PC e Telegram opcional (@BotFather)."""
        p = self.p
        bg = p.surface_container
        self.settings_frame = tk.Frame(self.content.inner, bg=bg, padx=12, pady=12)

        self._label(self.settings_frame, "Notificações", bg, p.on_surface, 10, "bold").pack(fill=tk.X)
        notif_row = tk.Frame(self.settings_frame, bg=bg)
        notif_row.pack(fill=tk.X, pady=(6, 0))
        self.var_desktop_notif = tk.BooleanVar(value=self.settings.desktop_notifications)
        self._checkbox(notif_row, "Notificar direto no PC", self.var_desktop_notif, bg).pack(side=tk.LEFT)
        self._button(
            notif_row, "Testar", self._on_test_pc_notify, p.secondary_container, p.on_secondary_container, size=9, pady=3
        ).pack(side=tk.RIGHT)

        tg_header = tk.Frame(self.settings_frame, bg=bg)
        tg_header.pack(fill=tk.X, pady=(14, 0))
        self._label(tg_header, "Telegram (opcional)", bg, p.on_surface, 10, "bold").pack(side=tk.LEFT)
        self._button(
            tg_header,
            "? Guia (PT/EN)",
            lambda: open_url_in_browser(HELP_DOC_URL),
            p.secondary_container,
            p.on_secondary_container,
            size=9,
            padx=8,
            pady=2,
        ).pack(side=tk.RIGHT)
        self._label(self.settings_frame, "Bot token (@BotFather)", bg).pack(fill=tk.X, pady=(6, 2))
        self.entry_token = self._entry(self.settings_frame, size=10)
        self.entry_token.pack(fill=tk.X, ipady=4)
        self.entry_token.insert(0, self.settings.telegram_bot_token)

        self._label(self.settings_frame, "Chat ID (opcional — auto com /start)", bg).pack(fill=tk.X, pady=(8, 2))
        self.entry_chat_id = self._entry(self.settings_frame, size=10)
        self.entry_chat_id.pack(fill=tk.X, ipady=4)
        if self.settings.allowed_chat_id:
            self.entry_chat_id.insert(0, str(self.settings.allowed_chat_id))

        self._button(self.settings_frame, "Salvar ajustes", self._on_save_settings, p.primary, p.on_primary).pack(
            fill=tk.X, pady=(14, 0)
        )

    # ------------------------------------------------------------------ estado

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

    def _select_tab(self, tab_id: str) -> None:
        self.active_tab = tab_id
        self.refresh_ui()

    def refresh_ui(self) -> None:
        p = self.p
        running = self._is_running()
        items = self.db.list_watchlist()
        recent_deals = self.db.list_recent_deals(limit=6)
        found_counts = self.db.count_deals_by_watchlist()
        active_count = sum(1 for it in items if it.active)

        # Cabeçalho
        self.status_dot.delete("all")
        dot = p.primary if running else p.outline
        self.status_dot.create_oval(0, 0, 8, 8, fill=dot, outline=dot)
        if not running:
            status_text = "Pausado"
        elif not items:
            status_text = "Nenhum produto na watchlist"
        else:
            status_text = f"Monitorando {active_count} de {len(items)} produtos"
        self.lbl_status.config(text=status_text)

        for child in self.switch_slot.winfo_children():
            child.destroy()
        Switch(self.switch_slot, p, running, self._toggle_running, p.surface, width=52, height=30).pack()

        if running:
            self.paused_notice.pack_forget()
        else:
            self.paused_notice.pack(fill=tk.X, pady=(12, 0), before=self.tabs_bar)

        # Abas
        labels = {
            "deals": f"Promoções  {len(recent_deals)}",
            "watchlist": f"Watchlist  {len(items)}",
            "settings": "Ajustes",
        }
        for tab_id, btn in self.tab_buttons.items():
            selected = tab_id == self.active_tab
            bg = p.secondary_container if selected else p.surface_container
            fg = p.on_secondary_container if selected else p.on_surface_variant
            btn.config(text=labels[tab_id], bg=bg, fg=fg, activebackground=bg, activeforeground=fg)

        settings_selected = self.active_tab == "settings"
        s_bg = p.primary if settings_selected else p.surface_container
        s_fg = p.on_primary if settings_selected else p.on_surface_variant
        self.btn_settings.config(bg=s_bg, fg=s_fg, activebackground=s_bg, activeforeground=s_fg)

        # Conteúdo
        self.settings_frame.pack_forget()
        for child in self.content.inner.winfo_children():
            if child is not self.settings_frame:
                child.destroy()
        self.content.canvas.yview_moveto(0)

        if self.active_tab == "watchlist":
            self._render_watchlist(items, found_counts)
        elif self.active_tab == "settings":
            self.settings_frame.pack(fill=tk.X)
        else:
            self._render_deals(recent_deals, {it.id: it for it in items})

        # Rodapé
        if self.busy:
            footer = "Buscando…"
        elif self.footer_message:
            footer = self.footer_message
        elif not running:
            footer = "Busca automática pausada"
        elif recent_deals:
            footer = f"Monitorando · última promoção {format_ago(recent_deals[0].found_at)}"
        else:
            footer = "Monitorando · nenhuma promoção ainda"
        self.lbl_footer.config(text=footer)
        self.btn_check.config(state=tk.DISABLED if self.busy else tk.NORMAL)

    def _render_empty(self, title: str, body: str) -> None:
        p = self.p
        box = tk.Frame(self.content.inner, bg=p.surface, pady=40)
        box.pack(fill=tk.X)
        tk.Label(box, text=title, bg=p.surface, fg=p.on_surface, font=self.font(11, "bold")).pack()
        tk.Label(
            box, text=body, bg=p.surface, fg=p.on_surface_variant, font=self.font(9), wraplength=300, justify=tk.CENTER
        ).pack(pady=(6, 0))

    def _render_deals(self, deals: list, items_by_id: dict) -> None:
        p = self.p
        if not deals:
            self._render_empty(
                "Nenhuma promoção por enquanto",
                "Quando algo cair abaixo do seu preço-alvo, aparece aqui e você recebe uma notificação.",
            )
            return

        for deal in deals:
            bg = p.surface_container
            card = tk.Frame(self.content.inner, bg=bg, padx=12, pady=10, cursor="hand2")
            card.pack(fill=tk.X, pady=(0, 8))

            right = tk.Frame(card, bg=bg)
            right.pack(side=tk.RIGHT, padx=(12, 0))
            tk.Label(
                right, text=format_brl(deal.price), bg=bg, fg=p.primary, font=self.font(12, "bold"), anchor="e"
            ).pack(anchor="e")
            item = items_by_id.get(deal.watchlist_id)
            saving = format_saving(deal.price, item.max_price if item else None)
            if saving:
                tk.Label(
                    right,
                    text=saving,
                    bg=p.tertiary_container,
                    fg=p.on_tertiary_container,
                    font=self.font(8, "bold"),
                    padx=6,
                    pady=1,
                ).pack(anchor="e", pady=(4, 0))

            left = tk.Frame(card, bg=bg)
            left.pack(side=tk.LEFT, fill=tk.X, expand=True)
            title = deal.title if len(deal.title) <= 34 else deal.title[:34].rstrip() + "…"
            self._label(left, title, bg, p.on_surface, 10, "bold").pack(fill=tk.X)
            meta = " · ".join(part for part in (deal.store, format_ago(deal.found_at)) if part)
            self._label(left, meta, bg).pack(fill=tk.X, pady=(3, 0))

            def _open(_event: tk.Event, url: str = deal.url) -> None:
                open_url_in_browser(url)

            for widget in (card, left, right, *left.winfo_children(), *right.winfo_children()):
                widget.bind("<Button-1>", _open)

    def _render_watchlist(self, items: list, found_counts: dict[int, int]) -> None:
        p = self.p
        if not items:
            self._render_empty("Watchlist vazia", "Adicione um produto e um preço-alvo acima.")
            return

        for item in items:
            bg = p.surface_container
            row = tk.Frame(self.content.inner, bg=bg, padx=12, pady=8)
            row.pack(fill=tk.X, pady=(0, 8))

            Switch(row, p, item.active, lambda i=item.id: self._on_toggle_item(i), bg).pack(side=tk.LEFT)

            self._button(
                row, "✕", lambda i=item.id: self._on_delete_item(i), bg, p.error, size=10, weight="normal", padx=6, pady=2
            ).pack(side=tk.RIGHT)
            tk.Button(
                row,
                text="Focar",
                command=lambda i=item.id: self._on_focus_item(i),
                font=self.font(9, "bold"),
                bg=bg,
                fg=p.primary,
                activebackground=bg,
                activeforeground=p.primary,
                relief=tk.FLAT,
                bd=0,
                highlightthickness=1,
                highlightbackground=p.outline_variant,
                padx=10,
                pady=3,
                cursor="hand2",
            ).pack(side=tk.RIGHT, padx=(0, 4))

            text = tk.Frame(row, bg=bg)
            text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)
            name = item.query if len(item.query) <= 24 else item.query[:24].rstrip() + "…"
            self._label(text, name, bg, p.on_surface if item.active else p.on_surface_variant, 10, "bold").pack(
                fill=tk.X
            )
            price = f"até {format_brl(item.max_price)}"
            found = found_counts.get(item.id, 0)
            if not item.active:
                meta = f"{price} · pausado"
            elif found == 0:
                meta = f"{price} · nenhuma ainda"
            else:
                meta = f"{price} · {found} achada{'' if found == 1 else 's'}"
            self._label(text, meta, bg).pack(fill=tk.X)

    # ------------------------------------------------------------------ ações

    def _build_query_payload(self) -> str:
        q = self.entry_query.get().strip()
        p = self.entry_price.get().strip()
        if not q:
            return ""
        if p and "|" not in q:
            return f"{q} | {p}"
        return q

    def _on_add_product(self) -> None:
        raw = self._build_query_payload()
        if not raw:
            return
        self.footer_message = set_primary_query(self.db, raw, exclusive=self.var_exclusive.get())
        self.entry_query.delete(0, tk.END)
        self.entry_price.delete(0, tk.END)
        self.active_tab = "watchlist"
        self.refresh_ui()

    def _on_focus_item(self, item_id: int) -> None:
        self.footer_message = select_only_item(self.db, item_id)
        self.refresh_ui()

    def _on_toggle_item(self, item_id: int) -> None:
        self.footer_message = toggle_item_active(self.db, item_id)
        self.refresh_ui()

    def _on_delete_item(self, item_id: int) -> None:
        self.db.delete_watchlist_item(item_id)
        self.footer_message = ""
        self.refresh_ui()

    def _on_test_pc_notify(self) -> None:
        send_desktop_notification(
            title="🚨 Deals Hunter — Teste Clicável",
            body="👆 Clique nesta notificação para testar a abertura no navegador!",
            url="https://github.com/Caspiom/Deals-Hunter",
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
        if self.busy:
            return
        self.busy = True
        self.refresh_ui()

        def _worker() -> None:
            try:
                settings = load_settings(require_telegram=False)
                db = Database(settings.db_path)
                app = DealHunterApp(settings=settings, db=db)
                total, found = asyncio.run(app.run_scrape_cycle(notify=True))
                message = f"Busca concluída: {total} verificado(s), {found} nova(s) oferta(s)."
            except Exception as exc:
                message = f"Erro na busca: {exc}"
            self.root.after(0, lambda: self._finish_check(message))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_check(self, message: str) -> None:
        self.busy = False
        self.footer_message = message
        self.refresh_ui()

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
