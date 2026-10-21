from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import webbrowser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db import WatchlistItem
    from scrapers import Deal

logger = logging.getLogger("deal_hunter.notifier")


def _format_brl(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def send_desktop_notification(
    title: str,
    body: str,
    url: str | None = None,
    timeout_ms: int = 8000,
) -> bool:
    """
    Envia uma notificação nativa direto no PC (Linux, Windows ou macOS).
    Não exige dependências pesadas compiladas.
    """
    system = platform.system().lower()

    if system == "linux":
        return _notify_linux(title, body, timeout_ms)
    if system == "windows":
        return _notify_windows(title, body, url)
    if system == "darwin":
        return _notify_macos(title, body)

    logger.warning("Sistema operacional '%s' sem backend de notificação nativo.", system)
    return False


def _notify_linux(title: str, body: str, timeout_ms: int = 8000) -> bool:
    """
    Usa org.freedesktop.Notifications via gdbus (funciona em Noctalia, KDE, GNOME,
    XFCE, Dunst, Mako, SwayNC mesmo sem libnotify instalado) ou notify-send.
    """
    gdbus_bin = shutil.which("gdbus")
    if gdbus_bin:
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
                    "[]",
                    "{}",
                    str(timeout_ms),
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return True
        except Exception as exc:
            logger.debug("Falha ao notificar via gdbus: %s", exc)

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
                return True
        except Exception as exc:
            logger.debug("Falha ao notificar via notify-send: %s", exc)

    logger.warning("Nenhum utilitário de notificação (gdbus / notify-send) disponível no Linux.")
    return False


def _notify_windows(title: str, body: str, url: str | None = None) -> bool:
    """Dispara um BalloonTip / Toast nativo do Windows via PowerShell (.NET System.Windows.Forms)."""
    safe_title = title.replace("'", "''").replace('"', "")
    safe_body = body.replace("'", "''").replace('"', "")
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.BalloonTipIcon = 'Info'; "
        f"$n.BalloonTipTitle = '{safe_title}'; "
        f"$n.BalloonTipText = '{safe_body}'; "
        "$n.Visible = $true; "
        "$n.ShowBalloonTip(7000); "
        "Start-Sleep -Seconds 2; "
        "$n.Dispose();"
    )
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creation_flags,
        )
        return res.returncode == 0
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
) -> bool:
    """Formata e envia o alerta de promoção diretamente para o desktop do usuário."""
    title = f"🚨 OFERTA: {item.query.upper()} — R$ {_format_brl(deal.price)}"
    store_info = f"{deal.store} ({deal.provider})" if deal.store else deal.provider
    coupon_info = f" | Cupom: {deal.coupon}" if deal.coupon else ""
    body = (
        f"{deal.title}\n"
        f"💰 R$ {_format_brl(deal.price)} (Meta: R$ {_format_brl(item.max_price)})\n"
        f"🏪 {store_info}{coupon_info}\n"
        f"🔗 {deal.url}"
    )
    sent = send_desktop_notification(title=title, body=body, url=deal.url)
    if auto_open_browser and deal.url:
        try:
            webbrowser.open(deal.url)
        except Exception:
            pass
    return sent
