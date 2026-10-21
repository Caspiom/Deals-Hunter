from __future__ import annotations

import logging

from config import load_settings, setup_logging
from db import Database


def run_seed() -> None:
    setup_logging(logging.INFO)
    settings = load_settings(require_telegram=False)
    db = Database(settings.db_path)
    inserted = db.seed_defaults()
    all_items = db.list_watchlist()

    print(f"\n✅ Seed executado com sucesso no banco: {settings.db_path}")
    print(f"   Novos itens adicionados: {len(inserted)}")
    print(f"   Total de itens na Watchlist: {len(all_items)}\n")
    for item in all_items:
        status = "ATIVO" if item.active else "INATIVO"
        print(
            f"   • [ID #{item.id}] {item.query} ({status})\n"
            f"     Faixa de preço: R$ {item.min_price:.2f} ~ R$ {item.max_price:.2f}\n"
            f"     Obrigatórias:   {item.must_contain or '(nenhuma)'}\n"
            f"     Negativas:      {item.exclude_words or '(nenhuma)'}\n"
        )


if __name__ == "__main__":
    run_seed()
