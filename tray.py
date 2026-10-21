from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
import sys
import threading
from pathlib import Path

from config import load_settings, setup_logging
from ctl import SERVICE_NAME, is_service_active, select_only_item
from db import Database
from main import DealHunterApp
from notifier import send_desktop_notification

logger = logging.getLogger("deal_hunter.tray")


def _create_tag_icon(active: bool):
    """Gera dinamicamente o ícone da bandeja (verde quando ativo, cinza quando pausado)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bg_color = (166, 227, 161, 255) if active else (108, 112, 134, 255)
    fg_color = (24, 24, 37, 255)

    draw.rounded_rectangle((6, 6, 58, 58), radius=14, fill=bg_color)
    draw.polygon([(18, 18), (38, 18), (50, 30), (30, 50), (18, 38)], fill=fg_color)
    draw.ellipse((23, 23, 29, 29), fill=bg_color)
    return img


class TrayController:
    """
    Ícone universal na Bandeja do Sistema (System Tray) para:
    - Windows 10/11
    - Linux (KDE Plasma, GNOME AppIndicator, XFCE, Cinnamon, MATE, Waybar Tray)
    """

    def __init__(self) -> None:
        self.settings = load_settings(require_telegram=False)
        self.db = Database(self.settings.db_path)
        if not self.db.list_watchlist():
            self.db.seed_defaults()

        self._use_systemd = (
            platform.system().lower() == "linux"
            and (Path.home() / ".config/systemd/user" / SERVICE_NAME).exists()
        )
        self._internal_running = False
        self._worker_thread: threading.Thread | None = None
        self._stop_event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.icon = None

        if not self._use_systemd:
            self.start_internal_worker()

    def is_running(self) -> bool:
        if self._use_systemd:
            return is_service_active()
        return self._internal_running

    def toggle_running(self) -> bool:
        if self._use_systemd:
            target = "stop" if is_service_active() else "start"
            subprocess.run(["systemctl", "--user", target, SERVICE_NAME], check=False)
            state = is_service_active()
        else:
            if self._internal_running:
                self.stop_internal_worker()
            else:
                self.start_internal_worker()
            state = self._internal_running

        self.refresh_tray()
        return state

    def start_internal_worker(self) -> None:
        if self._internal_running:
            return
        self._internal_running = True

        def _thread_target() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            settings = load_settings(require_telegram=False)
            db = Database(settings.db_path)
            app = DealHunterApp(settings=settings, db=db)
            self._stop_event = app.stop_event
            try:
                loop.run_until_complete(app.run())
            except Exception as exc:
                logger.error("Erro no worker interno da bandeja: %s", exc)
            finally:
                loop.close()
                self._internal_running = False

        self._worker_thread = threading.Thread(target=_thread_target, daemon=True)
        self._worker_thread.start()

    def stop_internal_worker(self) -> None:
        if not self._internal_running:
            return
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self._internal_running = False

    def open_gui(self) -> None:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent / "main.py"), "--gui"]
        )

    def check_now(self) -> None:
        def _scan() -> None:
            settings = load_settings(require_telegram=False)
            db = Database(settings.db_path)
            app = DealHunterApp(settings=settings, db=db)
            total, found = asyncio.run(app.run_scrape_cycle(notify=True))
            send_desktop_notification(
                title="🔍 Deals Hunter — Varredura Concluída",
                body=f"{total} verificado(s), {found} nova(s) oferta(s)!",
            )

        threading.Thread(target=_scan, daemon=True).start()

    def _select_product(self, item_id: int) -> None:
        select_only_item(self.db, item_id)
        self.refresh_tray()

    def _build_menu(self):
        import pystray

        running = self.is_running()
        items = self.db.list_watchlist()
        active_queries = [it.query for it in items if it.active]
        summary = ", ".join(active_queries) if active_queries else "Nenhum ativo"

        product_menu_items = []
        for it in items:
            product_menu_items.append(
                pystray.MenuItem(
                    f"{'✓ ' if it.active else ''}{it.query} (<= R$ {it.max_price:.0f})",
                    lambda _icon, _item, i=it.id: self._select_product(i),
                )
            )

        return pystray.Menu(
            pystray.MenuItem(
                f"{'🟢 Ativo' if running else '🔴 Parado'} — {summary}",
                lambda _icon, _item: self.open_gui(),
                default=True,
            ),
            pystray.MenuItem(
                "🎛️ Abrir Painel de Controle",
                lambda _icon, _item: self.open_gui(),
            ),
            pystray.MenuItem(
                "⏹ Desligar Monitoramento" if running else "▶ Ligar Monitoramento",
                lambda _icon, _item: self.toggle_running(),
            ),
            pystray.MenuItem(
                "🎯 Escolher Produto Pesquisado",
                pystray.Menu(*product_menu_items) if product_menu_items else None,
            ),
            pystray.MenuItem(
                "🔍 Buscar Promoções Agora",
                lambda _icon, _item: self.check_now(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "❌ Sair da Bandeja",
                lambda icon, _item: self._quit(icon),
            ),
        )

    def refresh_tray(self) -> None:
        if self.icon is not None:
            running = self.is_running()
            self.icon.icon = _create_tag_icon(running)
            self.icon.menu = self._build_menu()

    def _quit(self, icon) -> None:
        self.stop_internal_worker()
        icon.stop()

    def run(self) -> None:
        import pystray

        running = self.is_running()
        self.icon = pystray.Icon(
            "deals_hunter",
            _create_tag_icon(running),
            "Deals Hunter — Monitor de Promoções",
            menu=self._build_menu(),
        )
        self.icon.run()


def run_system_tray() -> None:
    setup_logging(logging.INFO)
    controller = TrayController()
    controller.run()


if __name__ == "__main__":
    run_system_tray()
