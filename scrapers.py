from __future__ import annotations

import abc
import hashlib
import html
import json
import logging
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from db import Database, WatchlistItem

logger = logging.getLogger("deal_hunter.scrapers")


@dataclass(frozen=True)
class Deal:
    deal_id: str
    title: str
    price: float
    url: str
    coupon: str | None = None
    store: str | None = None
    provider: str = ""


def normalize_text(text: str) -> str:
    """Remove acentos, converte para minúsculas e normaliza espaços."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_str.lower().split())


def parse_brl_price(raw: Any) -> float | None:
    """Converte número ou string monetária ('R$ 1.299,90') para float."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if val > 0 else None

    text = str(raw).strip()
    if not text:
        return None

    match = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:\.\d{1,2})?)", text)
    if not match:
        return None

    num_str = match.group(1)
    if "," in num_str and "." in num_str:
        num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        num_str = num_str.replace(",", ".")

    try:
        val = float(num_str)
        return val if val > 0 else None
    except ValueError:
        return None


def make_deal_id(provider: str, raw_id: str, url: str) -> str:
    """Gera um identificador determinístico único para a oferta + URL."""
    base = f"{provider.lower().strip()}:{raw_id.strip()}:{url.strip()}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]
    return f"{provider.lower()}_{raw_id}_{digest}"


def extract_coupon_from_text(text: str) -> str | None:
    """Tenta extrair código de cupom mencionado no título caso o campo explícito venha vazio."""
    patterns = [
        r"(?:cupom|c[oó]digo)\s*[:\-]?\s*([A-Z0-9]{4,20})",
        r"\[cupom\s+([A-Z0-9]{4,20})\]",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            candidate = m.group(1).upper()
            if candidate not in {"CUPOM", "NOAPP", "APLICATIVO", "RESGATE", "LOJA"}:
                return candidate
    return None


def validate_deal(deal: Deal, item: WatchlistItem, db: Database) -> tuple[bool, str]:
    """
    Filtro Anti-Falso Positivo:
    1. Todos os termos principais da query devem estar presentes no título.
    2. Todas as palavras de must_contain (se houver) devem estar no título.
    3. Nenhuma palavra de exclude_words pode estar no título.
    4. O preço deve estar entre min_price e max_price.
    5. A oferta não pode estar registrada na tabela seen_deals.
    """
    norm_title = normalize_text(deal.title)

    # 1. Todos os termos principais da query devem estar presentes no título
    query_terms = [t for t in normalize_text(item.query).split() if t]
    for term in query_terms:
        if term not in norm_title:
            return False, f"Termo '{term}' ausente no título"

    # 2. Palavras obrigatórias (must_contain)
    for must_word in item.must_contain_list:
        norm_must = normalize_text(must_word)
        if norm_must and norm_must not in norm_title:
            return False, f"Palavra obrigatória '{must_word}' ausente"

    # 3. Palavras negativas (exclude_words)
    for bad_word in item.exclude_words_list:
        norm_bad = normalize_text(bad_word)
        if norm_bad and norm_bad in norm_title:
            return False, f"Palavra negativa '{bad_word}' encontrada no título"

    # 4. Faixa de preço (min_price <= price <= max_price)
    if deal.price < item.min_price:
        return (
            False,
            f"Preço R$ {deal.price:.2f} abaixo do piso mínimo (R$ {item.min_price:.2f})",
        )
    if deal.price > item.max_price:
        return (
            False,
            f"Preço R$ {deal.price:.2f} acima da meta (R$ {item.max_price:.2f})",
        )

    # 5. Duplicidade (seen_deals)
    if db.is_deal_seen(deal.deal_id):
        return False, "Oferta já notificada anteriormente"

    return True, "OK"


class DealProvider(abc.ABC):
    """Interface base para provedores de promoções."""

    name: str = "BaseProvider"

    @abc.abstractmethod
    async def search(self, query: str, client: httpx.AsyncClient) -> list[Deal]:
        """Busca ofertas recentes para a query informada."""
        raise NotImplementedError


class PelandoProvider(DealProvider):
    """
    Scraper do Pelando (pelando.com.br).
    Extrai dados do JSON hidratado (Astro Island / __NEXT_DATA__) com fallback para HTML.
    """

    name = "Pelando"
    BASE_URL = "https://www.pelando.com.br"

    @staticmethod
    def _unwrap_astro_props(val: Any) -> Any:
        """Desempacota a serialização [0, valor] / [1, lista] do Astro Island."""
        if isinstance(val, list) and len(val) == 2 and isinstance(val[0], int):
            tag, inner = val[0], val[1]
            if tag == 0:
                return PelandoProvider._unwrap_astro_props(inner)
            if tag == 1 and isinstance(inner, list):
                return [PelandoProvider._unwrap_astro_props(x) for x in inner]
        if isinstance(val, dict):
            return {k: PelandoProvider._unwrap_astro_props(v) for k, v in val.items()}
        return val

    def _parse_astro_island(self, html_text: str) -> list[Deal]:
        deals: list[Deal] = []
        pattern = re.compile(
            r'<astro-island[^>]*component-export="SearchFeedContent"[^>]*props="([^"]+)"',
            re.IGNORECASE,
        )
        match = pattern.search(html_text)
        if not match:
            return deals

        raw_props = html.unescape(match.group(1))
        data = json.loads(raw_props)
        unwrapped = self._unwrap_astro_props(data)

        raw_deals = (
            unwrapped.get("initialData", {})
            .get("deals", {})
            .get("deals", [])
        )
        if not isinstance(raw_deals, list):
            return deals

        for item in raw_deals:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "active")).lower()
            if status in {"expired", "inactive", "deleted"}:
                continue

            title = str(item.get("title") or "").strip()
            price = parse_brl_price(item.get("price"))
            slug = str(item.get("slug") or "").strip()
            raw_id = str(item.get("id") or slug)

            if not title or price is None or not slug:
                continue

            url = f"{self.BASE_URL}/d/{slug}"
            store_obj = item.get("store")
            store_name = (
                str(store_obj.get("name")).strip()
                if isinstance(store_obj, dict) and store_obj.get("name")
                else None
            )
            coupon = (
                str(item.get("couponCode") or item.get("coupon") or "").strip()
                or extract_coupon_from_text(title)
            )

            deals.append(
                Deal(
                    deal_id=make_deal_id(self.name, raw_id, url),
                    title=title,
                    price=price,
                    url=url,
                    coupon=coupon or None,
                    store=store_name,
                    provider=self.name,
                )
            )
        return deals

    def _parse_next_data(self, soup: BeautifulSoup) -> list[Deal]:
        deals: list[Deal] = []
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag or not script_tag.string:
            return deals

        data = json.loads(script_tag.string)
        page_props = data.get("props", {}).get("pageProps", {})
        offers = (
            page_props.get("deals")
            or page_props.get("offers")
            or page_props.get("initialData", {}).get("deals", [])
        )
        if not isinstance(offers, list):
            return deals

        for item in offers:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "active")).lower() == "expired":
                continue

            title = str(item.get("title") or "").strip()
            price = parse_brl_price(item.get("price"))
            slug = str(item.get("slug") or item.get("id") or "").strip()
            if not title or price is None or not slug:
                continue

            url = (
                slug
                if slug.startswith("http")
                else f"{self.BASE_URL}/d/{slug.lstrip('/')}"
            )
            store_obj = item.get("store")
            store_name = (
                store_obj.get("name")
                if isinstance(store_obj, dict)
                else str(store_obj) if store_obj else None
            )
            coupon = (
                str(item.get("couponCode") or item.get("coupon") or "").strip()
                or extract_coupon_from_text(title)
            )

            deals.append(
                Deal(
                    deal_id=make_deal_id(self.name, str(item.get("id", slug)), url),
                    title=title,
                    price=price,
                    url=url,
                    coupon=coupon or None,
                    store=store_name,
                    provider=self.name,
                )
            )
        return deals

    def _parse_html_cards(self, soup: BeautifulSoup) -> list[Deal]:
        deals: list[Deal] = []
        seen_urls: set[str] = set()

        for link in soup.select('a[href*="/d/"]'):
            href = str(link.get("href") or "").strip()
            if not href:
                continue
            url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            if url in seen_urls:
                continue

            card = link.find_parent(
                lambda tag: tag.name in {"div", "article", "li"}
                and any("deal-card" in c for c in (tag.get("class") or []))
            ) or link.parent

            if card and card.find(attrs={"data-inactive": "true"}):
                continue

            title = str(link.get("aria-label") or link.get_text(" ", strip=True)).strip()
            if not title or len(title) < 5:
                continue

            card_text = card.get_text(" ", strip=True) if card else ""
            price_match = re.search(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)", card_text)
            price = parse_brl_price(price_match.group(1)) if price_match else None
            if price is None:
                continue

            seen_urls.add(url)
            slug = url.rstrip("/").split("/")[-1]
            coupon = extract_coupon_from_text(title) or extract_coupon_from_text(card_text)

            deals.append(
                Deal(
                    deal_id=make_deal_id(self.name, slug, url),
                    title=title,
                    price=price,
                    url=url,
                    coupon=coupon,
                    store=None,
                    provider=self.name,
                )
            )
        return deals

    async def search(self, query: str, client: httpx.AsyncClient) -> list[Deal]:
        encoded_query = urllib.parse.quote(query.strip())
        search_url = f"{self.BASE_URL}/busca/{encoded_query}"

        response = await client.get(search_url, follow_redirects=True)
        response.raise_for_status()
        html_text = response.text

        # 1. Tenta extrair via JSON estruturado do Astro Island
        try:
            deals = self._parse_astro_island(html_text)
            if deals:
                return deals
        except Exception as exc:
            logger.debug("Pelando Astro Island parse falhou (%s), tentando fallback.", exc)

        soup = BeautifulSoup(html_text, "html.parser")

        # 2. Tenta extrair via __NEXT_DATA__
        try:
            deals = self._parse_next_data(soup)
            if deals:
                return deals
        except Exception as exc:
            logger.debug("Pelando __NEXT_DATA__ parse falhou (%s), tentando HTML.", exc)

        # 3. Fallback via seletores HTML
        return self._parse_html_cards(soup)


class PromobitProvider(DealProvider):
    """
    Scraper do Promobit (promobit.com.br).
    Consulta a API JSON oficial do frontend Next.js (/search?q=...&sort=latest)
    e possui fallback para __NEXT_DATA__ e parsing HTML via BeautifulSoup.
    """

    name = "Promobit"
    BASE_URL = "https://www.promobit.com.br"
    API_URL = "https://api.promobit.com.br/search"

    def _parse_api_offers(self, payload: dict[str, Any]) -> list[Deal]:
        deals: list[Deal] = []
        raw_offers = payload.get("active_offers") or payload.get("offers") or []
        if not isinstance(raw_offers, list):
            return deals

        for item in raw_offers:
            if not isinstance(item, dict):
                continue

            # Ignora postagens que são apenas divulgação genérica de cupom sem produto
            if str(item.get("offer_price_type", "")).upper() == "COUPON":
                continue

            title = str(item.get("offer_title") or item.get("title") or "").strip()
            price = parse_brl_price(item.get("offer_price") or item.get("price"))
            slug = str(item.get("offer_slug") or item.get("slug") or "").strip()
            raw_id = str(item.get("offer_id") or item.get("id") or slug)

            if not title or price is None or not slug:
                continue

            url = (
                slug
                if slug.startswith("http")
                else f"{self.BASE_URL}/oferta/{slug.lstrip('/')}"
            )
            coupon_raw = item.get("offer_coupon") or item.get("coupon")
            coupon = (
                str(coupon_raw).strip()
                if coupon_raw
                else extract_coupon_from_text(title)
            )
            store = str(
                item.get("store_name") or item.get("store_domain") or ""
            ).strip() or None

            deals.append(
                Deal(
                    deal_id=make_deal_id(self.name, raw_id, url),
                    title=title,
                    price=price,
                    url=url,
                    coupon=coupon or None,
                    store=store,
                    provider=self.name,
                )
            )
        return deals

    def _parse_html_fallback(self, html_text: str) -> list[Deal]:
        soup = BeautifulSoup(html_text, "html.parser")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag and script_tag.string:
            try:
                data = json.loads(script_tag.string)
                page_props = data.get("props", {}).get("pageProps", {})
                deals = self._parse_api_offers(page_props)
                if deals:
                    return deals
            except Exception as exc:
                logger.debug("Promobit __NEXT_DATA__ parse falhou: %s", exc)

        deals: list[Deal] = []
        seen_urls: set[str] = set()
        for link in soup.select('a[href*="/oferta/"]'):
            href = str(link.get("href") or "").strip()
            if not href:
                continue
            url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
            if url in seen_urls:
                continue

            card_text = link.get_text(" ", strip=True)
            price_match = re.search(
                r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)", card_text
            )
            price = parse_brl_price(price_match.group(1)) if price_match else None
            if price is None:
                continue

            title = re.sub(r"R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?.*", "", card_text).strip()
            if not title:
                title = str(link.get("title") or "").strip()
            if not title:
                continue

            seen_urls.add(url)
            slug = url.rstrip("/").split("/")[-1]
            deals.append(
                Deal(
                    deal_id=make_deal_id(self.name, slug, url),
                    title=title,
                    price=price,
                    url=url,
                    coupon=extract_coupon_from_text(title),
                    store=None,
                    provider=self.name,
                )
            )
        return deals

    async def search(self, query: str, client: httpx.AsyncClient) -> list[Deal]:
        params = {"q": query.strip(), "sort": "latest"}
        try:
            resp = await client.get(
                self.API_URL,
                params=params,
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict):
                return self._parse_api_offers(payload)
        except Exception as exc:
            logger.warning(
                "Promobit API falhou para '%s' (%s), tentando fallback HTML.",
                query,
                exc,
            )

        encoded_query = urllib.parse.quote(query.strip())
        web_url = f"{self.BASE_URL}/buscar/?q={encoded_query}&sort=recent"
        resp = await client.get(web_url, follow_redirects=True)
        resp.raise_for_status()
        return self._parse_html_fallback(resp.text)


class DealEngine:
    """Orquestrador modular que consulta todos os DealProviders registrados."""

    def __init__(
        self,
        db: Database,
        providers: list[DealProvider] | None = None,
        timeout_seconds: float = 15.0,
        user_agent: str = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    ) -> None:
        self.db = db
        self.providers: list[DealProvider] = providers or [
            PelandoProvider(),
            PromobitProvider(),
        ]
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def create_http_client(self) -> httpx.AsyncClient:
        # local_address="0.0.0.0" força IPv4, evitando travamentos em redes com IPv6 quebrado
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=2)
        return httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

    async def check_watchlist_item(
        self, item: WatchlistItem, client: httpx.AsyncClient
    ) -> list[Deal]:
        """Busca em todos os provedores e retorna apenas ofertas inéditas e aprovadas no filtro."""
        matched_deals: list[Deal] = []

        for provider in self.providers:
            try:
                deals = await provider.search(item.query, client)
                logger.info(
                    "[%s] Query '%s': %d ofertas brutas encontradas.",
                    provider.name,
                    item.query,
                    len(deals),
                )
            except Exception as exc:
                logger.error(
                    "[%s] Erro ao buscar '%s': %s",
                    provider.name,
                    item.query,
                    exc,
                )
                continue

            for deal in deals:
                is_valid, reason = validate_deal(deal, item, self.db)
                if is_valid:
                    logger.info(
                        "MATCH! [%s] '%s' por R$ %.2f (meta <= R$ %.2f)",
                        provider.name,
                        deal.title,
                        deal.price,
                        item.max_price,
                    )
                    matched_deals.append(deal)
                else:
                    logger.debug(
                        "Ignorado [%s] '%s' (R$ %.2f): %s",
                        provider.name,
                        deal.title,
                        deal.price,
                        reason,
                    )

        return matched_deals
