#!/usr/bin/env python3
"""
Módulo nativo para Waybar / Polybar / i3status-rust.
Retorna JSON no formato esperado pelo Waybar custom module:
  {"text": "🏷️ fifine am8t", "tooltip": "...", "class": "active", "alt": "active"}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config import load_settings  # noqa: E402
from ctl import build_status_dict  # noqa: E402
from db import Database  # noqa: E402


def main() -> None:
    settings = load_settings(require_telegram=False)
    db = Database(settings.db_path)
    status = build_status_dict(db)

    running = bool(status["service_active"])
    summary = str(status["summary"])
    icon = "🏷️" if running else "⏸️"
    css_class = "active" if running else "inactive"

    items_lines = [
        f"{'🟢' if it['active'] else '⚪'} {it['query']} (<= R$ {it['max_price']:.0f})"
        for it in status["items"]
    ]
    tooltip = (
        f"Deals Hunter: {'ATIVO' if running else 'PARADO'}\n"
        + ("\n".join(items_lines) if items_lines else "Sem produtos")
        + "\n\nClique Esq: Abrir Painel | Clique Dir: Ligar/Desligar | Meio: Buscar Agora"
    )

    payload = {
        "text": f"{icon} {summary}",
        "tooltip": tooltip,
        "class": css_class,
        "alt": css_class,
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
