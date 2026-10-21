from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import httpx

from config import Settings, update_env_chat_id
from db import Database, WatchlistItem
from scrapers import Deal, parse_brl_price

logger = logging.getLogger("deal_hunter.bot")


def escape_tg_markdown(text: str) -> str:
    """Escapa caracteres especiais do Markdown v1 do Telegram em textos dinâmicos."""
    if not text:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def format_brl(value: float) -> str:
    """Formata float como moeda brasileira (ex: 285,00)."""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_deal_notification(deal: Deal, item: WatchlistItem) -> str:
    """Formata a mensagem de alerta de promoção seguindo o template exigido."""
    safe_query = escape_tg_markdown(item.query.upper())
    safe_title = escape_tg_markdown(deal.title)
    price_str = format_brl(deal.price)
    max_price_str = format_brl(item.max_price)

    if deal.coupon:
        clean_coupon = deal.coupon.replace("`", "")
        coupon_str = f"`{clean_coupon}`"
    else:
        coupon_str = "Não informado"

    store_label = deal.store or deal.provider or "Não informada"
    if deal.store and deal.provider and deal.provider.lower() not in deal.store.lower():
        store_label = f"{deal.store} (via {deal.provider})"
    safe_store = escape_tg_markdown(store_label)

    lines = [
        f"🚨 *OFERTA ENCONTRADA: {safe_query}*",
        f"📦 *Produto:* {safe_title}",
        f"💰 *Preço:* R$ {price_str} _(Sua meta: R$ {max_price_str})_",
        f"🎟️ *Cupom:* {coupon_str}",
        f"🏪 *Loja:* {safe_store}",
        f"🔗 [Link Direto]({deal.url})",
    ]
    return "\n".join(lines)


class TelegramBot:
    """Cliente assíncrono do Telegram via Long Polling (getUpdates) usando httpx."""

    def __init__(
        self,
        settings: Settings,
        db: Database,
        on_manual_check: Callable[[], Awaitable[tuple[int, int]]],
    ) -> None:
        self.settings = settings
        self.db = db
        self.on_manual_check = on_manual_check
        self.api_base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self._offset: int = 0
        self._check_lock = asyncio.Lock()

    def _create_client(self) -> httpx.AsyncClient:
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
        return httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(45.0, connect=15.0),
        )

    async def send_message(
        self,
        text: str,
        chat_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool = False,
    ) -> bool:
        target_chat = chat_id or self.settings.allowed_chat_id
        payload: dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with self._create_client() as client:
            try:
                resp = await client.post(f"{self.api_base}/sendMessage", json=payload)
                if resp.status_code == 400:
                    # Fallback sem parse_mode caso algum caractere especial quebre o Markdown
                    logger.warning(
                        "Falha de formatação Markdown no Telegram (%s), enviando texto puro.",
                        resp.text,
                    )
                    payload.pop("parse_mode", None)
                    resp = await client.post(f"{self.api_base}/sendMessage", json=payload)
                if not resp.is_success:
                    logger.error(
                        "Erro do Telegram (%d): %s",
                        resp.status_code,
                        resp.text,
                    )
                resp.raise_for_status()
                return True
            except Exception as exc:
                logger.error("Erro ao enviar mensagem no Telegram: %s", exc)
                return False

    async def send_deal_alert(self, deal: Deal, item: WatchlistItem) -> bool:
        if self.settings.is_chat_id_misconfigured_as_bot:
            logger.warning(
                "Envio pendente: abra o bot @NixOfertaBot no Telegram e envie /start "
                "para registrar seu ALLOWED_CHAT_ID automaticamente."
            )
            return False
        text = format_deal_notification(deal, item)
        reply_markup = {
            "inline_keyboard": [
                [{"text": "🛒 Abrir Oferta", "url": deal.url}]
            ]
        }
        return await self.send_message(text=text, reply_markup=reply_markup)

    async def poll_forever(self, stop_event: asyncio.Event) -> None:
        """Loop contínuo de Long Polling para receber comandos do Telegram."""
        logger.info(
            "Iniciando Listener do Telegram (ALLOWED_CHAT_ID=%s)...",
            self.settings.allowed_chat_id,
        )
        async with self._create_client() as client:
            while not stop_event.is_set():
                try:
                    resp = await client.get(
                        f"{self.api_base}/getUpdates",
                        params={
                            "offset": self._offset,
                            "timeout": 25,
                            "allowed_updates": '["message"]',
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if not data.get("ok"):
                        logger.warning("Resposta inesperada do getUpdates: %s", data)
                        await asyncio.sleep(5)
                        continue

                    updates = data.get("result", [])
                    for upd in updates:
                        upd_id = int(upd["update_id"])
                        self._offset = max(self._offset, upd_id + 1)
                        await self._handle_update(upd)

                except asyncio.CancelledError:
                    break
                except httpx.TimeoutException:
                    continue
                except Exception as exc:
                    logger.error("Erro no loop de Long Polling do Telegram: %s", exc)
                    await asyncio.sleep(5)

    async def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = str(message.get("text") or "").strip()

        if not text:
            return

        # Auto-configuração caso ALLOWED_CHAT_ID tenha sido preenchido com o ID do próprio bot
        if chat_id and self.settings.is_chat_id_misconfigured_as_bot and int(chat_id) != self.settings.bot_id:
            real_chat_id = int(chat_id)
            self.settings.allowed_chat_id = real_chat_id
            update_env_chat_id(real_chat_id)
            logger.info(
                "ALLOWED_CHAT_ID atualizado automaticamente para o seu ID pessoal: %d (salvo no .env)!",
                real_chat_id,
            )
            await self.send_message(
                f"✅ *Configuração automática concluída!*\n"
                f"Seu `ALLOWED_CHAT_ID` (`{real_chat_id}`) foi salvo no `.env`.\n"
                f"Iniciando varredura das promoções agora..."
            )
            await self._cmd_check()
            return

        # Restrição de segurança: responde APENAS ao ALLOWED_CHAT_ID
        if int(chat_id or 0) != self.settings.allowed_chat_id:
            user_info = message.get("from") or {}
            username = user_info.get("username") or user_info.get("first_name") or "desconhecido"
            logger.warning(
                "Mensagem recebida de '%s' com chat_id=%s (mas ALLOWED_CHAT_ID=%s). "
                "Se este for você, atualize ALLOWED_CHAT_ID=%s no seu arquivo .env!",
                username,
                chat_id,
                self.settings.allowed_chat_id,
                chat_id,
            )
            return

        cmd_parts = text.split(maxsplit=1)
        command = cmd_parts[0].split("@")[0].lower()
        args_str = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

        if command in {"/start", "/help"}:
            await self._cmd_help()
        elif command == "/add":
            await self._cmd_add(args_str)
        elif command == "/list":
            await self._cmd_list()
        elif command == "/del":
            await self._cmd_del(args_str)
        elif command == "/check":
            await self._cmd_check()
        else:
            await self.send_message(
                "❓ Comando não reconhecido. Digite `/help` para ver os comandos disponíveis."
            )

    async def _cmd_help(self) -> None:
        msg = (
            "🤖 *Deal Hunter Bot — Comandos Disponíveis*\n\n"
            "➕ *Adicionar produto:*\n"
            "`/add <termo> | <preco_max> | [palavras_negativas]`\n"
            "• _Ex. simples:_ `/add galaxy s24 | 2500`\n"
            "• _Ex. avançado:_ `/add galaxy s24 | 2500 | capa,pelicula`\n\n"
            "📋 *Listar monitorados:*\n"
            "`/list` — Mostra todos os itens, IDs, faixa de preço e filtros.\n\n"
            "🗑️ *Remover item:*\n"
            "`/del <id>` — Remove o produto pelo ID (ex: `/del 1`).\n\n"
            "🔍 *Varredura imediata:*\n"
            "`/check` — Força uma busca agora mesmo em todas as lojas.\n\n"
            "ℹ️ *Ajuda:*\n"
            "`/help` — Exibe esta mensagem."
        )
        await self.send_message(msg)

    async def _cmd_add(self, args_str: str) -> None:
        if not args_str or "|" not in args_str:
            await self.send_message(
                "⚠️ *Formato inválido!*\n\n"
                "Use:\n"
                "`/add <termo> | <preco_max> | [palavras_negativas]`\n\n"
                "*Exemplos:*\n"
                "• `/add galaxy s24 | 2500`\n"
                "• `/add galaxy s24 | 2500 | capa,pelicula`"
            )
            return

        parts = [p.strip() for p in args_str.split("|")]
        query = parts[0]
        raw_max_price = parts[1] if len(parts) > 1 else ""
        exclude_words = parts[2] if len(parts) > 2 else ""
        must_contain = parts[3] if len(parts) > 3 else ""

        max_price = parse_brl_price(raw_max_price)
        if not query or max_price is None or max_price <= 0:
            await self.send_message(
                "❌ *Erro:* Informe um termo válido e um preço máximo numérico maior que zero.\n"
                "Exemplo: `/add galaxy s24 | 2500`"
            )
            return

        try:
            item = self.db.add_watchlist_item(
                query=query,
                max_price=max_price,
                exclude_words=exclude_words,
                must_contain=must_contain,
            )
        except Exception as exc:
            logger.error("Erro ao adicionar item na watchlist: %s", exc)
            await self.send_message(f"❌ Erro ao salvar no banco: {exc}")
            return

        neg_display = escape_tg_markdown(item.exclude_words) if item.exclude_words else "Nenhuma"
        await self.send_message(
            f"✅ *Produto adicionado à Watchlist!*\n\n"
            f"🆔 *ID:* `{item.id}`\n"
            f"🔎 *Termo:* {escape_tg_markdown(item.query)}\n"
            f"💰 *Faixa aceita:* R$ {format_brl(item.min_price)} ~ R$ {format_brl(item.max_price)}\n"
            f"🚫 *Palavras negativas:* {neg_display}"
        )

    async def _cmd_list(self) -> None:
        items = self.db.list_watchlist()
        if not items:
            await self.send_message(
                "📭 *Sua Watchlist está vazia.*\n"
                "Adicione um produto com `/add <termo> | <preco_max>`."
            )
            return

        lines = ["📋 *Produtos Monitorados (Watchlist):*\n"]
        for item in items:
            status_icon = "🟢 Ativo" if item.active else "🔴 Inativo"
            line = (
                f"🆔 *#{item.id}* — *{escape_tg_markdown(item.query)}* ({status_icon})\n"
                f"   💰 Faixa: R$ {format_brl(item.min_price)} ~ R$ {format_brl(item.max_price)}"
            )
            if item.exclude_words:
                line += f"\n   🚫 Excluir: `{item.exclude_words.replace('`', '')}`"
            if item.must_contain:
                line += f"\n   📌 Obrigatório: `{item.must_contain.replace('`', '')}`"
            lines.append(line)

        await self.send_message("\n\n".join(lines))

    async def _cmd_del(self, args_str: str) -> None:
        raw_id = args_str.strip().lstrip("#")
        if not raw_id.isdigit():
            await self.send_message(
                "⚠️ Informe o ID numérico do item para remover.\nExemplo: `/del 1`"
            )
            return

        item_id = int(raw_id)
        existing = self.db.get_watchlist_item(item_id)
        if not existing:
            await self.send_message(f"❌ Item com ID `{item_id}` não encontrado na Watchlist.")
            return

        self.db.delete_watchlist_item(item_id)
        await self.send_message(
            f"🗑️ Item *#{item_id}* (*{escape_tg_markdown(existing.query)}*) removido com sucesso!"
        )

    async def _cmd_check(self) -> None:
        if self._check_lock.locked():
            await self.send_message(
                "⏳ Já existe uma varredura em andamento. Aguarde a conclusão!"
            )
            return

        async with self._check_lock:
            await self.send_message(
                "🔍 *Iniciando varredura imediata* no Pelando e Promobit..."
            )
            try:
                total_items, new_deals = await self.on_manual_check()
                await self.send_message(
                    f"✅ *Varredura concluída!*\n"
                    f"• Produtos verificados: `{total_items}`\n"
                    f"• Novas ofertas enviadas: `{new_deals}`"
                )
            except Exception as exc:
                logger.error("Erro durante /check manual: %s", exc)
                await self.send_message(
                    f"❌ Ocorreu um erro durante a varredura: `{escape_tg_markdown(str(exc))}`"
                )
