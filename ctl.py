#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from config import load_settings
from db import Database
from main import DealHunterApp
from notifier import open_url_in_browser, send_desktop_notification

BASE_DIR = Path(__file__).resolve().parent
SERVICE_NAME = "deal-hunter.service"


def is_service_active() -> bool:
    res = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    return res.stdout.strip() == "active"


def build_status_dict(db: Database, message: str = "") -> dict:
    running = is_service_active()
    items = db.list_watchlist()
    active_queries = [it.query for it in items if it.active]
    if not active_queries:
        summary = "Sem produto"
    elif len(active_queries) == 1:
        summary = active_queries[0]
    else:
        summary = f"{active_queries[0]} +{len(active_queries) - 1}"

    recent = db.list_recent_deals(limit=6)
    return {
        "service_active": running,
        "summary": summary,
        "message": message,
        "items": [
            {
                "id": it.id,
                "query": it.query,
                "max_price": it.max_price,
                "min_price": it.min_price,
                "exclude_words": it.exclude_words,
                "active": it.active,
            }
            for it in items
        ],
        "recent_deals": [
            {
                "title": d.title,
                "price": d.price,
                "url": d.url,
                "store": d.store,
            }
            for d in recent
        ],
    }


def set_item_active(db: Database, item_id: int, active: bool) -> None:
    with db._connect() as conn:
        conn.execute(
            "UPDATE watchlist SET active = ? WHERE id = ?",
            (1 if active else 0, item_id),
        )


def toggle_item_active(db: Database, item_id: int) -> str:
    item = db.get_watchlist_item(item_id)
    if not item:
        return "Item não encontrado."
    new_state = not item.active
    set_item_active(db, item_id, new_state)
    return f"'{item.query}' {'ativado' if new_state else 'pausado'}."


def select_only_item(db: Database, item_id: int) -> str:
    item = db.get_watchlist_item(item_id)
    if not item:
        return "Item não encontrado."
    with db._connect() as conn:
        conn.execute("UPDATE watchlist SET active = 0")
        conn.execute("UPDATE watchlist SET active = 1 WHERE id = ?", (item_id,))
    return f"Monitorando apenas: {item.query} (<= R$ {item.max_price:.0f})"


def set_primary_query(db: Database, raw_input: str, exclusive: bool = True) -> str:
    """
    Define ou adiciona rapidamente o produto pesquisado pelo gadget da barra.
    Formatos aceitos:
      - 'fifine am8t | 285 | espuma,cabo'
      - 'fifine am8t | 285'
      - 'fifine am8t' (mantém preço atual ou usa 285 como padrão)
    """
    parts = [p.strip() for p in raw_input.split("|")]
    query = " ".join(parts[0].split())
    if not query:
        return "Informe um nome de produto válido."

    max_price: float | None = None
    if len(parts) > 1 and parts[1]:
        try:
            max_price = float(parts[1].replace("R$", "").replace(",", ".").strip())
        except ValueError:
            max_price = None

    exclude_words = (
        parts[2] if len(parts) > 2 else "espuma,cabo,suporte avulso,pop filter"
    )

    items = db.list_watchlist()
    for it in items:
        if it.query.lower() == query.lower():
            if max_price is not None and max_price > 0:
                min_price = round(max_price * 0.30, 2)
                with db._connect() as conn:
                    conn.execute(
                        "UPDATE watchlist SET max_price = ?, min_price = ? WHERE id = ?",
                        (max_price, min_price, it.id),
                    )
            if exclusive:
                select_only_item(db, it.id)
            else:
                set_item_active(db, it.id, True)
            price_used = max_price if (max_price and max_price > 0) else it.max_price
            return f"Produto selecionado: {it.query} (<= R$ {price_used:.0f})"

    if max_price is None or max_price <= 0:
        active_items = [it for it in items if it.active]
        max_price = active_items[0].max_price if active_items else 285.0

    new_item = db.add_watchlist_item(
        query=query,
        max_price=max_price,
        exclude_words=exclude_words,
        active=True,
    )
    if exclusive:
        select_only_item(db, new_item.id)
    return f"Adicionado e ativo: {new_item.query} (<= R$ {new_item.max_price:.0f})"


def main() -> None:
    settings = load_settings(require_telegram=False)
    db = Database(settings.db_path)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    msg = ""

    if cmd == "status":
        pass
    elif cmd == "toggle-service":
        was_active = is_service_active()
        target = "stop" if was_active else "start"
        subprocess.run(["systemctl", "--user", target, SERVICE_NAME], check=False)
        now_active = is_service_active()
        msg = "Bot ligado em background!" if now_active else "Bot desligado."
    elif cmd == "start-service":
        subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], check=False)
        msg = "Bot ligado em background!"
    elif cmd == "stop-service":
        subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], check=False)
        msg = "Bot desligado."
    elif cmd == "toggle-item":
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            msg = toggle_item_active(db, int(sys.argv[2]))
    elif cmd == "select-only":
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            msg = select_only_item(db, int(sys.argv[2]))
    elif cmd == "set-query":
        raw = " ".join(sys.argv[2:]).strip()
        if raw:
            msg = set_primary_query(db, raw, exclusive=True)
    elif cmd == "add-item":
        raw = " ".join(sys.argv[2:]).strip()
        if raw:
            msg = set_primary_query(db, raw, exclusive=False)
    elif cmd == "del-item":
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            item_id = int(sys.argv[2])
            existing = db.get_watchlist_item(item_id)
            if existing and db.delete_watchlist_item(item_id):
                msg = f"Removido: {existing.query}"
    elif cmd == "check-now":
        try:
            full_settings = load_settings(require_telegram=False)
            app = DealHunterApp(settings=full_settings, db=db)
            total, new_deals = asyncio.run(app.run_scrape_cycle(notify=True))
            msg = f"Busca concluída: {total} verificado(s), {new_deals} nova(s) oferta(s)!"
        except Exception as exc:
            msg = f"Erro na busca: {exc}"
    elif cmd == "test-notify":
        ok, _nid = send_desktop_notification(
            title="🚨 Deals Hunter — Teste Clicável",
            body="👆 Clique nesta notificação para testar a abertura no navegador!",
            url="https://github.com/Caspiom/Deals-Hunter",
        )
        msg = "Notificação de teste enviada ao PC!" if ok else "Falha ao enviar notificação no PC."
    elif cmd == "open-url":
        if len(sys.argv) > 2:
            open_url_in_browser(sys.argv[2].strip())
            msg = "Oferta aberta no navegador!"

    print(json.dumps(build_status_dict(db, message=msg), ensure_ascii=False))


if __name__ == "__main__":
    main()
