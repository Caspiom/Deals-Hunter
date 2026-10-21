from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("deal_hunter.db")


@dataclass(frozen=True)
class WatchlistItem:
    id: int
    query: str
    max_price: float
    min_price: float
    must_contain: str
    exclude_words: str
    active: bool

    @property
    def must_contain_list(self) -> list[str]:
        if not self.must_contain:
            return []
        return [w.strip() for w in self.must_contain.split(",") if w.strip()]

    @property
    def exclude_words_list(self) -> list[str]:
        if not self.exclude_words:
            return []
        return [w.strip() for w in self.exclude_words.split(",") if w.strip()]


class Database:
    """Gerenciador de persistência SQLite para watchlist e ofertas já vistas."""

    def __init__(self, db_path: Path | str = "watcher.db") -> None:
        self.db_path = Path(db_path)
        self.init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    max_price REAL NOT NULL,
                    min_price REAL,
                    must_contain TEXT DEFAULT '',
                    exclude_words TEXT DEFAULT '',
                    active BOOLEAN DEFAULT 1
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_deals (
                    deal_id TEXT PRIMARY KEY,
                    watchlist_id INTEGER,
                    price REAL,
                    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (watchlist_id) REFERENCES watchlist (id) ON DELETE SET NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watchlist_active ON watchlist(active);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_deals_watchlist ON seen_deals(watchlist_id);"
            )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> WatchlistItem:
        max_price = float(row["max_price"])
        raw_min = row["min_price"]
        min_price = float(raw_min) if raw_min is not None else round(max_price * 0.30, 2)
        return WatchlistItem(
            id=int(row["id"]),
            query=str(row["query"]),
            max_price=max_price,
            min_price=min_price,
            must_contain=str(row["must_contain"] or ""),
            exclude_words=str(row["exclude_words"] or ""),
            active=bool(row["active"]),
        )

    def add_watchlist_item(
        self,
        query: str,
        max_price: float,
        min_price: float | None = None,
        must_contain: str = "",
        exclude_words: str = "",
        active: bool = True,
    ) -> WatchlistItem:
        clean_query = " ".join(query.strip().split())
        if not clean_query:
            raise ValueError("O termo de busca não pode ser vazio.")
        if max_price <= 0:
            raise ValueError("O preço máximo deve ser maior que zero.")

        computed_min = (
            round(float(min_price), 2)
            if min_price is not None
            else round(float(max_price) * 0.30, 2)
        )
        clean_must = ",".join(w.strip() for w in must_contain.split(",") if w.strip())
        clean_exclude = ",".join(w.strip() for w in exclude_words.split(",") if w.strip())

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO watchlist (query, max_price, min_price, must_contain, exclude_words, active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_query,
                    round(float(max_price), 2),
                    computed_min,
                    clean_must,
                    clean_exclude,
                    1 if active else 0,
                ),
            )
            item_id = int(cursor.lastrowid)
            row = conn.execute(
                "SELECT * FROM watchlist WHERE id = ?", (item_id,)
            ).fetchone()
            return self._row_to_item(row)

    def list_watchlist(self, only_active: bool = False) -> list[WatchlistItem]:
        sql = "SELECT * FROM watchlist"
        params: tuple[int, ...] = ()
        if only_active:
            sql += " WHERE active = ?"
            params = (1,)
        sql += " ORDER BY id ASC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_item(r) for r in rows]

    def get_watchlist_item(self, item_id: int) -> WatchlistItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM watchlist WHERE id = ?", (item_id,)
            ).fetchone()
            return self._row_to_item(row) if row else None

    def delete_watchlist_item(self, item_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM watchlist WHERE id = ?", (item_id,))
            return cursor.rowcount > 0

    def is_deal_seen(self, deal_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_deals WHERE deal_id = ?", (deal_id,)
            ).fetchone()
            return row is not None

    def mark_deal_seen(self, deal_id: str, watchlist_id: int, price: float) -> None:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_deals (deal_id, watchlist_id, price, found_at)
                VALUES (?, ?, ?, ?)
                """,
                (deal_id, watchlist_id, round(float(price), 2), now_iso),
            )

    def seed_defaults(self) -> list[WatchlistItem]:
        """Cadastra os produtos iniciais de exemplo caso ainda não existam na watchlist."""
        defaults = [
            {
                "query": "fifine am8t",
                "max_price": 285.0,
                "min_price": round(285.0 * 0.30, 2),
                "must_contain": "am8t",
                "exclude_words": "espuma,cabo,suporte avulso,pop filter",
            },
            {
                "query": "fifine sfm1",
                "max_price": 130.0,
                "min_price": round(130.0 * 0.30, 2),
                "must_contain": "sfm1",
                "exclude_words": "espuma,cabo,suporte avulso,pop filter",
            },
        ]
        existing_queries = {item.query.lower() for item in self.list_watchlist()}
        inserted: list[WatchlistItem] = []

        for d in defaults:
            if d["query"].lower() not in existing_queries:
                item = self.add_watchlist_item(
                    query=d["query"],
                    max_price=d["max_price"],
                    min_price=d["min_price"],
                    must_contain=d["must_contain"],
                    exclude_words=d["exclude_words"],
                )
                inserted.append(item)
                logger.info(
                    "Seed cadastrado: [%d] '%s' (R$ %.2f ~ R$ %.2f)",
                    item.id,
                    item.query,
                    item.min_price,
                    item.max_price,
                )
        return inserted
