"""Query-based web search for the orchestrator / sidekick (no browser)."""

from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import quote_plus, urljoin

from http_get import fetch_https

_DDG_JSON = "https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"
_DDG_HTML = "https://html.duckduckgo.com/html/?q={q}"
_WTTR_UA = "curl/8.0"

_CURRENCY_CODE = re.compile(r"\b([A-Z]{3})\b")
_KNOWN_CURRENCIES = frozenset(
    {
        "AED",
        "AUD",
        "BRL",
        "CAD",
        "CHF",
        "CNY",
        "EUR",
        "GBP",
        "HKD",
        "IDR",
        "ILS",
        "INR",
        "JPY",
        "KRW",
        "MXN",
        "MYR",
        "NZD",
        "PHP",
        "RUB",
        "SAR",
        "SEK",
        "SGD",
        "THB",
        "TRY",
        "TWD",
        "USD",
        "ZAR",
    }
)
_CURRENCY_WORDS = {
    "dollar": "USD",
    "dollars": "USD",
    "usd": "USD",
    "rupee": "INR",
    "rupees": "INR",
    "inr": "INR",
    "euro": "EUR",
    "euros": "EUR",
    "eur": "EUR",
    "pound": "GBP",
    "pounds": "GBP",
    "gbp": "GBP",
    "yen": "JPY",
    "jpy": "JPY",
}


def _json_hits(data: dict) -> list[str]:
    lines: list[str] = []
    answer = str(data.get("Answer") or "").strip()
    if answer:
        lines.append(f"Answer: {answer}")
    abstract = str(data.get("AbstractText") or data.get("Abstract") or "").strip()
    if abstract:
        src = str(data.get("AbstractSource") or "").strip()
        prefix = f"{src}: " if src else ""
        lines.append(prefix + abstract)
    defn = str(data.get("Definition") or "").strip()
    if defn:
        lines.append("Definition: " + defn)
    for topic in data.get("RelatedTopics") or []:
        if not isinstance(topic, dict):
            continue
        text = str(topic.get("Text") or "").strip()
        if text:
            lines.append(text)
        if len(lines) >= 8:
            break
    return lines


def _duckduckgo_blocked(html: str) -> bool:
    low = (html or "").lower()
    return "anomaly.js" in low or "result__a" not in low and "links_main" not in low


def _html_hits(html: str, *, max_results: int) -> list[str]:
    if _duckduckgo_blocked(html):
        return []
    rows: list[str] = []
    pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)',
        re.I | re.S,
    )
    for href, title, snippet in pattern.findall(html or ""):
        title_t = unescape(re.sub(r"<[^>]+>", " ", title))
        snippet_t = unescape(re.sub(r"<[^>]+>", " ", snippet))
        title_t = " ".join(title_t.split())
        snippet_t = " ".join(snippet_t.split())
        url = unescape(href)
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = urljoin("https://html.duckduckgo.com", url)
        bit = title_t
        if snippet_t:
            bit += " — " + snippet_t
        if url:
            bit += f" ({url})"
        if bit:
            rows.append(bit)
        if len(rows) >= max_results:
            break
    if rows:
        return rows
    for href, title in re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html or "",
        flags=re.I | re.S,
    ):
        title_t = " ".join(unescape(re.sub(r"<[^>]+>", " ", title)).split())
        if title_t:
            rows.append(title_t)
        if len(rows) >= max_results:
            break
    return rows


def _currency_tokens(query: str) -> list[str]:
    q = (query or "").strip()
    if not q:
        return []
    codes = [
        m.group(1).upper()
        for m in _CURRENCY_CODE.finditer(q.upper())
        if m.group(1).upper() in _KNOWN_CURRENCIES
    ]
    if len(codes) >= 2:
        return codes[:2]
    words = re.findall(r"[A-Za-z]+", q.lower())
    found: list[str] = []
    for word in words:
        code = _CURRENCY_WORDS.get(word)
        if code and code not in found:
            found.append(code)
        if len(found) >= 2:
            break
    return found


def _looks_like_exchange_query(query: str) -> bool:
    low = (query or "").lower()
    if len(_currency_tokens(query)) >= 2:
        return True
    return any(
        token in low
        for token in (
            "exchange rate",
            "conversion rate",
            "convert ",
            "currency",
            "forex",
            "fx rate",
        )
    )


def _lookup_exchange_rate(query: str) -> str | None:
    tokens = _currency_tokens(query)
    if len(tokens) < 2:
        return None
    base, quote = tokens[0], tokens[1]
    url = f"https://api.frankfurter.app/latest?from={base}&to={quote}"
    raw = fetch_https(url, max_chars=2_000, strip_html=False)
    if raw.startswith("Error:"):
        url = f"https://open.er-api.com/v6/latest/{base}"
        raw = fetch_https(url, max_chars=4_000, strip_html=False)
        if raw.startswith("Error:"):
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        rates = data.get("rates") if isinstance(data, dict) else None
        if not isinstance(rates, dict):
            return None
        rate = rates.get(quote)
        if rate is None:
            return None
        when = str(data.get("time_last_update_utc") or data.get("date") or "").strip()
        line = f"1 {base} = {rate} {quote}"
        if when:
            line += f" (updated {when})"
        return f"Exchange rate ({base}/{quote}): {line} — source: exchangerate-api.com"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    rates = data.get("rates") if isinstance(data, dict) else None
    if not isinstance(rates, dict):
        return None
    rate = rates.get(quote)
    if rate is None:
        return None
    when = str(data.get("date") or "").strip()
    line = f"1 {base} = {rate} {quote}"
    if when:
        line += f" (as of {when})"
    return f"Exchange rate ({base}/{quote}): {line} — source: frankfurter.app (ECB)"


def _weather_location(query: str) -> str | None:
    q = " ".join((query or "").split())
    low = q.lower()
    if "weather" not in low and "forecast" not in low:
        return None
    m = re.search(
        r"(?:weather|forecast)\s+(?:in|for|at|of)\s+(.+?)(?:\?|$| today| tomorrow| this week)",
        q,
        flags=re.I,
    )
    if m:
        return m.group(1).strip(" .,!?:;\"'")
    m = re.search(
        r"(?:what(?:'s| is) the )?(?:weather|forecast)\s+(?:like\s+)?(?:in|for|at)\s+(.+?)(?:\?|$| today| tomorrow)",
        q,
        flags=re.I,
    )
    if m:
        return m.group(1).strip(" .,!?:;\"'")
    m = re.search(r"(.+?)\s+weather(?:\s+today|\s+now|\s+forecast)?(?:\?|$)", q, flags=re.I)
    if m:
        loc = m.group(1).strip(" .,!?:;\"'")
        loc = re.sub(
            r"^(?:what(?:'s| is)|how(?:'s| is)|tell me|check|get)\s+",
            "",
            loc,
            flags=re.I,
        ).strip()
        return loc or None
    return None


def _lookup_weather(query: str) -> str | None:
    location = _weather_location(query)
    if not location:
        return None
    url = f"https://wttr.in/{quote_plus(location)}?format=3"
    raw = fetch_https(url, max_chars=500, strip_html=False, user_agent=_WTTR_UA)
    if raw.startswith("Error:") or raw.startswith("<!DOCTYPE"):
        return None
    line = " ".join(raw.split())
    if not line or line.lower().startswith("(empty"):
        return None
    return f"Weather ({location}): {line} — source: wttr.in"


def _specialized_lookup(query: str) -> list[str]:
    hits: list[str] = []
    if _looks_like_exchange_query(query):
        fx = _lookup_exchange_rate(query)
        if fx:
            hits.append(fx)
    if "weather" in query.lower() or "forecast" in query.lower():
        wx = _lookup_weather(query)
        if wx:
            hits.append(wx)
    return hits


def search_web(query: str, *, max_results: int = 5) -> str:
    q = " ".join((query or "").split())
    if not q:
        return "Error: query is required."
    max_results = max(1, min(int(max_results or 5), 8))
    encoded = quote_plus(q)
    parts: list[str] = []
    parts.extend(_specialized_lookup(q))

    raw = fetch_https(_DDG_JSON.format(q=encoded), max_chars=20_000)
    if not raw.startswith("Error:"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for hit in _json_hits(data):
                    if hit not in parts:
                        parts.append(hit)
        except json.JSONDecodeError:
            pass

    html = fetch_https(_DDG_HTML.format(q=encoded), max_chars=40_000, strip_html=False)
    if not html.startswith("Error:"):
        for hit in _html_hits(html, max_results=max_results):
            if hit not in parts:
                parts.append(hit)

    if not parts:
        if raw.startswith("Error:") and html.startswith("Error:"):
            return f"Error: search failed ({raw}; {html})"
        return "No search results."
    numbered = [f"{i}. {line}" for i, line in enumerate(parts[: max_results + 3], start=1)]
    return "\n".join(numbered)


def run_web_search(args: dict) -> str:
    query = str(args.get("query") or "").strip()
    max_results = args.get("max_results")
    try:
        n = int(max_results) if max_results is not None else 5
    except (TypeError, ValueError):
        n = 5
    return search_web(query, max_results=n)
