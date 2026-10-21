from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
import threading
import webbrowser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db import Database, WatchlistItem
    from scrapers import Deal

logger = logging.getLogger("deal_hunter.notifier")

# Cache em memória de notification_id -> url para cliques no corpo ("default")
_NOTIF_URL_MAP: dict[int, str] = {}


def _format_brl(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def open_url_in_browser(url: str) -> None:
    """Abre a URL no navegador padrão do sistema."""
    if not url or not url.startswith("http"):
        return
    logger.info("Abrindo oferta no navegador: %s", url)
    system = platform.system().lower()
    if system == "linux":
        xdg_bin = shutil.which("xdg-open")
        if xdg_bin:
            subprocess.Popen(
                [xdg_bin, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
    try:
        webbrowser.open(url)
    except Exception as exc:
        logger.error("Erro ao abrir navegador para %s: %s", url, exc)


def send_desktop_notification(
    title: str,
    body: str,
    url: str | None = None,
    timeout_ms: int = 8000,
) -> tuple[bool, int]:
    """
    Envia uma notificação nativa clicável direto no PC (Linux, Windows ou macOS).
    Retorna (sucesso, notification_id).
    """
    system = platform.system().lower()

    if system == "linux":
        return _notify_linux(title, body, url, timeout_ms)
    if system == "windows":
        ok = _notify_windows(title, body, url)
        return ok, 0
    if system == "darwin":
        ok = _notify_macos(title, body)
        return ok, 0

    logger.warning("Sistema operacional '%s' sem backend de notificação nativo.", system)
    return False, 0


def _notify_linux(
    title: str, body: str, url: str | None = None, timeout_ms: int = 8000
) -> tuple[bool, int]:
    """
    Envia notificação via D-Bus (org.freedesktop.Notifications) com ação 'default'
    (clique no card) e botão '🛒 Abrir Oferta'.
    """
    actions: list[str] = []
    if url:
        actions = [
            "default",
            "Abrir Oferta",
            f"open:{url}",
            "🛒 Abrir Oferta",
        ]

    # 1. Tenta via jeepney (puro Python D-Bus)
    try:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection

        notifs = DBusAddress(
            "/org/freedesktop/Notifications",
            bus_name="org.freedesktop.Notifications",
            interface="org.freedesktop.Notifications",
        )
        with open_dbus_connection(bus="SESSION") as conn:
            msg = new_method_call(
                notifs,
                "Notify",
                "susssasa{sv}i",
                (
                    "Deals Hunter",
                    0,
                    "dialog-information",
                    title,
                    body,
                    actions,
                    {},
                    int(timeout_ms),
                ),
            )
            reply = conn.send_and_get_reply(msg)
            nid = int(reply.body[0])
            if url:
                _NOTIF_URL_MAP[nid] = url
            return True, nid
    except Exception as exc:
        logger.debug("Jeepney Notify falhou (%s), tentando gdbus.", exc)

    # 2. Fallback via gdbus CLI
    gdbus_bin = shutil.which("gdbus")
    if gdbus_bin:
        actions_arg = (
            f"['default', 'Abrir Oferta', 'open:{url}', '🛒 Abrir Oferta']"
            if url
            else "[]"
        )
        try:
            res = subprocess.run(
                [
                    gdbus_bin,
                    "call",
                    "--session",
                    "--dest",
                    "org.freedesktop.Notifications",
                    "--object-path",
                    "/org/freedesktop/Notifications",
                    "--method",
                    "org.freedesktop.Notifications.Notify",
                    "Deals Hunter",
                    "0",
                    "dialog-information",
                    title,
                    body,
                    actions_arg,
                    "{}",
                    str(timeout_ms),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                m = re.search(r"(\d+)", res.stdout)
                nid = int(m.group(1)) if m else 0
                if nid and url:
                    _NOTIF_URL_MAP[nid] = url
                return True, nid
        except Exception as exc:
            logger.debug("Falha ao notificar via gdbus: %s", exc)

    # 3. Fallback via notify-send
    notify_send_bin = shutil.which("notify-send")
    if notify_send_bin:
        try:
            res = subprocess.run(
                [
                    notify_send_bin,
                    "-a",
                    "Deals Hunter",
                    "-i",
                    "dialog-information",
                    "-t",
                    str(timeout_ms),
                    title,
                    body,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return True, 0
        except Exception as exc:
            logger.debug("Falha ao notificar via notify-send: %s", exc)

    return False, 0


def start_linux_notification_click_listener(db: Database) -> None:
    """
    Inicia uma thread em background que escuta o sinal D-Bus ActionInvoked
    (org.freedesktop.Notifications) e abre a oferta no navegador ao clicar!
    """
    if platform.system().lower() != "linux":
        return

    def _listener_loop() -> None:
        try:
            from jeepney import MatchRule, message_bus
            from jeepney.io.blocking import open_dbus_connection
        except ImportError:
            logger.warning("Biblioteca 'jeepney' não instalada; clique em notificações desativado.")
            return

        rule = MatchRule(
            type="signal",
            interface="org.freedesktop.Notifications",
            member="ActionInvoked",
            path="/org/freedesktop/Notifications",
        )
        while True:
            try:
                with open_dbus_connection(bus="SESSION") as conn:
                    conn.send_and_get_reply(message_bus.AddMatch(rule))
                    logger.info("Listener de cliques em notificações Desktop (D-Bus) ativo!")
                    while True:
                        msg = conn.receive()
                        if not msg or not msg.body or len(msg.body) < 2:
                            continue
                        nid = int(msg.body[0])
                        action_key = str(msg.body[1])
                        url: str | None = None
                        if action_key.startswith("open:"):
                            url = action_key.split("open:", 1)[1].strip()
                        elif action_key == "default":
                            url = _NOTIF_URL_MAP.get(nid) or db.get_url_by_notif_id(nid)
                        if url:
                            open_url_in_browser(url)
            except Exception as exc:
                logger.debug("Reconectando listener D-Bus de notificações: %s", exc)
                import time

                time.sleep(3)

    t = threading.Thread(target=_listener_loop, name="dbus_notif_clicks", daemon=True)
    t.start()


def _notify_windows(title: str, body: str, url: str | None = None) -> bool:
    """Dispara um BalloonTip clicável nativo do Windows via PowerShell."""
    safe_title = title.replace("'", "''").replace('"', "")
    safe_body = body.replace("'", "''").replace('"', "")
    click_handler = (
        f"$n.add_BalloonTipClicked({{ Start-Process '{url}' }}); " if url else ""
    )
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.BalloonTipIcon = 'Info'; "
        f"$n.BalloonTipTitle = '{safe_title}'; "
        f"$n.BalloonTipText = '{safe_body}'; "
        f"{click_handler}"
        "$n.Visible = $true; "
        "$n.ShowBalloonTip(8000); "
        "Start-Sleep -Seconds 8; "
        "$n.Dispose();"
    )
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        return True
    except Exception as exc:
        logger.debug("Falha ao enviar notificação no Windows: %s", exc)
        return False


def _notify_macos(title: str, body: str) -> bool:
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"')
    try:
        res = subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{safe_body}" with title "{safe_title}"',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.returncode == 0
    except Exception as exc:
        logger.debug("Falha ao enviar notificação no macOS: %s", exc)
        return False


def send_deal_desktop_alert(
    deal: Deal, item: WatchlistItem, auto_open_browser: bool = False
) -> tuple[bool, int]:
    """Formata e envia o alerta clicável de promoção diretamente para o desktop do usuário."""
    title = f"🚨 OFERTA: {item.query.upper()} — R$ {_format_brl(deal.price)}"
    store_info = f"{deal.store} ({deal.provider})" if deal.store else deal.provider
    coupon_info = f" | Cupom: {deal.coupon}" if deal.coupon else ""
    body = (
        f"{deal.title}\n"
        f"💰 R$ {_format_brl(deal.price)} (Meta: R$ {_format_brl(item.max_price)})\n"
        f"🏪 {store_info}{coupon_info}\n"
        f"👆 Clique na notificação para abrir a oferta!"
    )
    sent, nid = send_desktop_notification(title=title, body=body, url=deal.url)
    if auto_open_browser and deal.url:
        open_url_in_browser(deal.url)
    return sent, nid
