from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _reload_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_file, override=True)
    except ImportError:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")


_reload_dotenv()

PLACEHOLDER_TOKENS = {
    "",
    "1234567890:AAH_seu_token_aqui",
    "your_bot_token_here",
}
PLACEHOLDER_CHAT_IDS = {"", "0", "123456789"}


@dataclass
class Settings:
    desktop_notifications: bool
    auto_open_browser: bool
    telegram_bot_token: str
    allowed_chat_id: int
    db_path: Path
    scrape_interval_min_minutes: float
    scrape_interval_max_minutes: float
    http_timeout_seconds: float
    user_agent: str

    @property
    def bot_id(self) -> int | None:
        if ":" in self.telegram_bot_token:
            prefix = self.telegram_bot_token.split(":", 1)[0].strip()
            if prefix.isdigit():
                return int(prefix)
        return None

    @property
    def is_chat_id_misconfigured_as_bot(self) -> bool:
        return self.bot_id is not None and self.allowed_chat_id == self.bot_id

    @property
    def telegram_enabled(self) -> bool:
        """Retorna True se um token válido do BotFather foi configurado."""
        return (
            bool(self.telegram_bot_token)
            and self.telegram_bot_token not in PLACEHOLDER_TOKENS
            and ":" in self.telegram_bot_token
        )


def update_env_values(updates: dict[str, str]) -> None:
    """Atualiza ou insere chaves no arquivo .env preservando comentários."""
    env_path = BASE_DIR / ".env"
    example_path = BASE_DIR / ".env.example"

    if not env_path.exists() and example_path.exists():
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")

    lines = (
        env_path.read_text(encoding="utf-8").splitlines()
        if env_path.exists()
        else []
    )
    remaining = dict(updates)
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                new_lines.append(f"{key}={remaining.pop(key)}")
                continue
        new_lines.append(line)

    for key, val in remaining.items():
        new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    _reload_dotenv()


def update_env_chat_id(new_chat_id: int) -> None:
    """Atualiza ALLOWED_CHAT_ID no arquivo .env."""
    update_env_values({"ALLOWED_CHAT_ID": str(new_chat_id)})


def load_settings(require_telegram: bool = False) -> Settings:
    _reload_dotenv()
    raw_desktop = os.getenv("DESKTOP_NOTIFICATIONS", "true").strip().lower()
    desktop_notifications = raw_desktop not in {"0", "false", "no", "off"}

    raw_open = os.getenv("AUTO_OPEN_BROWSER", "false").strip().lower()
    auto_open_browser = raw_open in {"1", "true", "yes", "on"}

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if token in PLACEHOLDER_TOKENS:
        token = ""

    raw_chat_id = os.getenv("ALLOWED_CHAT_ID", "0").strip()
    if raw_chat_id in PLACEHOLDER_CHAT_IDS:
        raw_chat_id = "0"

    if require_telegram and not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN não configurado! Configure pelo painel gráfico ou no .env."
        )

    try:
        allowed_chat_id = int(raw_chat_id) if raw_chat_id else 0
    except ValueError:
        allowed_chat_id = 0

    if token and ":" in token:
        bot_id_prefix = token.split(":", 1)[0].strip()
        if bot_id_prefix == str(allowed_chat_id):
            logging.getLogger("deal_hunter.config").warning(
                "ATENÇÃO: ALLOWED_CHAT_ID (%s) é igual ao ID do próprio Bot. "
                "Envie /start para o bot no Telegram para detectar seu chat_id automaticamente.",
                allowed_chat_id,
            )

    raw_db_path = os.getenv("DB_PATH", "watcher.db").strip()
    db_path = Path(raw_db_path)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    min_minutes = float(os.getenv("SCRAPE_INTERVAL_MIN_MINUTES", "10"))
    max_minutes = float(os.getenv("SCRAPE_INTERVAL_MAX_MINUTES", "15"))
    if max_minutes < min_minutes:
        max_minutes = min_minutes

    timeout = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))

    user_agent = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )

    return Settings(
        desktop_notifications=desktop_notifications,
        auto_open_browser=auto_open_browser,
        telegram_bot_token=token,
        allowed_chat_id=allowed_chat_id,
        db_path=db_path,
        scrape_interval_min_minutes=min_minutes,
        scrape_interval_max_minutes=max_minutes,
        http_timeout_seconds=timeout,
        user_agent=user_agent,
    )


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
