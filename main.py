from __future__ import annotations

import argparse
import asyncio
import logging
import random
import signal
import sys

from bot import TelegramBot, format_deal_notification
from config import Settings, load_settings, setup_logging
from db import Database
from notifier import send_deal_desktop_alert
from scrapers import DealEngine

logger = logging.getLogger("deal_hunter.main")


class DealHunterApp:
    """Coordenador central que executa o Worker de Scraping e (opcionalmente) o Bot do Telegram."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.engine = DealEngine(
            db=db,
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.user_agent,
        )
        self.bot = TelegramBot(
            settings=settings,
            db=db,
            on_manual_check=self.run_scrape_cycle,
        )
        self.stop_event = asyncio.Event()
        self._scrape_lock = asyncio.Lock()

    async def run_scrape_cycle(self, notify: bool = True) -> tuple[int, int]:
        """
        Executa uma varredura completa de todos os itens ativos na watchlist.
        Envia alertas direto no PC (Desktop Notification) e/ou no Telegram (se configurado).
        Retorna (total_itens_ativos, total_novas_ofertas_enviadas).
        """
        async with self._scrape_lock:
            active_items = self.db.list_watchlist(only_active=True)
            if not active_items:
                logger.info("Watchlist vazia ou sem itens ativos para monitorar.")
                return 0, 0

            logger.info(
                "Iniciando ciclo de scraping para %d produto(s) ativo(s)...",
                len(active_items),
            )
            new_alerts_count = 0

            async with self.engine.create_http_client() as client:
                for item in active_items:
                    try:
                        matched_deals = await self.engine.check_watchlist_item(
                            item, client
                        )
                    except Exception as exc:
                        logger.error(
                            "Falha inesperada ao processar item '%s': %s",
                            item.query,
                            exc,
                        )
                        continue

                    for deal in matched_deals:
                        if not notify:
                            print("\n" + "=" * 60)
                            print(format_deal_notification(deal, item))
                            print("=" * 60)
                            new_alerts_count += 1
                            continue

                        delivered = False

                        # 1. Canal Primário: Notificação Nativa Direto no PC
                        if self.settings.desktop_notifications:
                            pc_ok = send_deal_desktop_alert(
                                deal,
                                item,
                                auto_open_browser=self.settings.auto_open_browser,
                            )
                            if pc_ok:
                                delivered = True

                        # 2. Canal Secundário Opcional: Bot do Telegram (@BotFather)
                        if self.settings.telegram_enabled:
                            tg_ok = await self.bot.send_deal_alert(deal, item)
                            if tg_ok:
                                delivered = True

                        if delivered:
                            self.db.mark_deal_seen(deal.deal_id, item.id, deal.price)
                            new_alerts_count += 1

                    # Pequena pausa entre produtos para evitar rate-limiting
                    await asyncio.sleep(random.uniform(1.0, 2.5))

            logger.info(
                "Ciclo finalizado: %d produto(s) verificado(s), %d nova(s) oferta(s).",
                len(active_items),
                new_alerts_count,
            )
            return len(active_items), new_alerts_count

    async def background_scraper_worker(self) -> None:
        """Worker periódico que executa o scraping com jitter aleatório entre 10 e 15 min."""
        logger.info(
            "Worker de Scraping iniciado (intervalo com jitter: %.1f ~ %.1f min).",
            self.settings.scrape_interval_min_minutes,
            self.settings.scrape_interval_max_minutes,
        )
        while not self.stop_event.is_set():
            try:
                await self.run_scrape_cycle(notify=True)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Erro no Worker de Scraping: %s", exc, exc_info=True)

            sleep_minutes = random.uniform(
                self.settings.scrape_interval_min_minutes,
                self.settings.scrape_interval_max_minutes,
            )
            sleep_seconds = sleep_minutes * 60.0
            logger.info(
                "Próxima varredura automática em %.1f minutos (%.0f segundos).",
                sleep_minutes,
                sleep_seconds,
            )

            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=sleep_seconds)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop_event.set)
            except NotImplementedError:
                pass

        tasks: list[asyncio.Task] = []
        worker_task = asyncio.create_task(
            self.background_scraper_worker(), name="scraper_worker"
        )
        tasks.append(worker_task)

        if self.settings.telegram_enabled:
            listener_task = asyncio.create_task(
                self.bot.poll_forever(self.stop_event), name="telegram_listener"
            )
            tasks.append(listener_task)
        else:
            logger.info(
                "Modo Desktop Ativo: notificações direto no PC ativadas "
                "(Telegram BotFather opcional não configurado)."
            )

        logger.info("Sistema Deals Hunter em execução! Pressione Ctrl+C para encerrar.")
        await self.stop_event.wait()
        logger.info("Sinal de encerramento recebido. Parando tarefas...")

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Deals Hunter finalizado com segurança.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deals Hunter — Monitor de Promoções (Desktop + Telegram Opcional)"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Popula o banco de dados com os itens iniciais ('fifine am8t' e 'fifine sfm1') e encerra.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa um ciclo único de scraping exibindo os resultados no terminal (sem enviar alertas).",
    )
    parser.add_argument(
        "--check-now",
        action="store_true",
        help="Executa um ciclo único de scraping e envia alertas encontrados (PC e/ou Telegram).",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Abre o Painel de Controle Gráfico (GUI).",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Inicia o ícone na Bandeja do Sistema (System Tray) para Windows/KDE/GNOME/XFCE.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ativa logs detalhados em nível DEBUG.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    if args.gui:
        from gui import launch_control_panel

        launch_control_panel()
        return

    if args.tray:
        from tray import run_system_tray

        run_system_tray()
        return

    settings = load_settings(require_telegram=False)
    db = Database(settings.db_path)

    if args.seed:
        inserted = db.seed_defaults()
        items = db.list_watchlist()
        print(
            f"Seed concluído ({len(inserted)} novos itens inseridos). Total na watchlist: {len(items)}"
        )
        for item in items:
            print(
                f"  [#{item.id}] query='{item.query}' | min=R$ {item.min_price:.2f} | "
                f"max=R$ {item.max_price:.2f} | exclude='{item.exclude_words}'"
            )
        return

    if not db.list_watchlist():
        logger.info("Watchlist vazia detectada. Inserindo itens de seed inicial...")
        db.seed_defaults()

    app = DealHunterApp(settings=settings, db=db)

    if args.dry_run:
        asyncio.run(app.run_scrape_cycle(notify=False))
        return

    if args.check_now:
        asyncio.run(app.run_scrape_cycle(notify=True))
        return

    asyncio.run(app.run())


if __name__ == "__main__":
    main()
