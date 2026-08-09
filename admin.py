import asyncio
import io
import json
import random
import time
import logging
from typing import Optional, List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_IDS, TEST_CARD, GATEWAY_TIMEOUTS, FREE_USERS_BLOCKED
from helpers import get_html, btn, make_keyboard, is_admin, escape, mention_html
from shopify import check_card, test_proxy, is_valid_proxy, parse_cards
from data import (
    get_user_proxies,
    add_global_proxy,
    get_all_global_proxies,
    delete_global_proxy,
    get_all_users,
    save_broadcast,
    register_user,
    get_user_info,
    add_gateway,
    get_gateways,
    get_gateway,
    update_gateway_status,
    count_gateways,
    delete_gateway,
    add_api,
    get_apis,
    get_api,
    update_api_status,
    count_apis,
    delete_api,
    count_global_proxies,
    delete_dead_gateways,
    reorder_gateways,
    add_pp_gateway, get_pp_gateways, get_pp_gateway, count_pp_gateways,
    delete_pp_gateway, delete_dead_pp_gateways, update_pp_gateway_status,
    reorder_pp_gateways,
)

router = Router()
log = logging.getLogger(__name__)

# Stop events for add/check operations per admin
_stop_events: dict[int, asyncio.Event] = {}
#  States
class AddGatewayStates(StatesGroup):
    waiting_for_sites = State()

class AddAPIStates(StatesGroup):
    waiting_for_url = State()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

class DeleteGatewayStates(StatesGroup):
    waiting_for_id = State()

class DeleteAPIStates(StatesGroup):
    waiting_for_id = State()

class ProxyStates(StatesGroup):
    waiting_for_proxy   = State()
    waiting_delete_host = State()
@router.callback_query(F.data == "admin_gw_stop")
async def admin_gw_stop(callback: CallbackQuery):
    uid = callback.from_user.id
    if not is_admin(uid): await callback.answer("⛔", show_alert=True); return
    ev = _stop_events.get(uid)
    if ev:
        ev.set()
    await callback.answer("⏹ Stopping...", show_alert=False)

def _guard(fn):
    async def wrapper(obj, *args, **kwargs):
        uid = (obj.from_user or obj.message.from_user).id if isinstance(obj, CallbackQuery) else obj.from_user.id
        if not is_admin(uid):
            if isinstance(obj, CallbackQuery):
                await obj.answer("⛔ Not admin.", show_alert=True)
            else:
                await obj.answer("⛔ Not admin.")
            return
        if isinstance(obj, CallbackQuery):
            await obj.answer()
        return await fn(obj, *args, **kwargs)
    return wrapper

async def _safe_edit(msg: Message, text: str, markup=None):
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            log.warning(f"safe_edit: {e}")
    except Exception as e:
        log.warning(f"safe_edit: {e}")
#  Main Panel
ADMIN_MAIN_BUTTONS = [
    [btn("Gateways",   "admin_gateways",     style="primary"),
     btn("PayPal",     "admin_pp_gw",        style="primary")],
    [btn("APIs",       "admin_apis",         style="primary"),
     btn("Proxy Pool", "admin_proxy_pool:1", style="primary")],
    [btn("Stats",      "admin_stats",        style="default"),
     btn("Broadcast",  "admin_broadcast",    style="success")],
]

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Not admin.")
        return
    gw_count  = await count_gateways()
    api_count = await count_apis()
    px_count  = await count_global_proxies()
    user_count = len(await get_all_users())
    text = (
        f"👑 <b>Admin Panel</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🛍️ Gateways : <b>{gw_count}</b>\n"
        f"🔗 APIs     : <b>{api_count}</b>\n"
        f"🛡️ Proxies  : <b>{px_count}</b>\n"
        f"👥 Users    : <b>{user_count}</b>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=make_keyboard(ADMIN_MAIN_BUTTONS))

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    gw_count  = await count_gateways()
    api_count = await count_apis()
    px_count  = await count_global_proxies()
    user_count = len(await get_all_users())
    text = (
        f"👑 <b>Admin Panel</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🛍️ Gateways : <b>{gw_count}</b>\n"
        f"🔗 APIs     : <b>{api_count}</b>\n"
        f"🛡️ Proxies  : <b>{px_count}</b>\n"
        f"👥 Users    : <b>{user_count}</b>"
    )
    await _safe_edit(callback.message, text, make_keyboard(ADMIN_MAIN_BUTTONS))
#  Stats
@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    gw  = await count_gateways()
    api = await count_apis()
    px  = await count_global_proxies()
    us  = len(await get_all_users())
    text = (
        f"📊 <b>Bot Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🛍️ Gateways  : <b>{gw}</b>\n"
        f"🔗 APIs      : <b>{api}</b>\n"
        f"🛡️ Proxies   : <b>{px}</b>\n"
        f"👥 Users     : <b>{us}</b>\n"
        f"🕐 Uptime    : <b>running</b>"
    )
    await _safe_edit(callback.message, text, make_keyboard([
        [btn("🔄 Refresh", "admin_stats", style="primary")],
        [btn("⬅️ Back",    "admin_back",  style="danger")],
    ]))
#  Gateways
@router.callback_query(F.data == "admin_gateways")
async def admin_gateways(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    total = await count_gateways()
    text = (
        f"🛍️ <b>Gateways</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Total: <b>{total}</b> gateways"
    )
    await _safe_edit(callback.message, text, make_keyboard([
        [btn("Add Gateway",   "admin_add_gateway",           style="success"),
         btn("View",          "admin_view_gateways:1",       style="primary")],
        [btn("Check All",     "admin_check_all_gateways",    style="primary"),
         btn("Delete Dead",   "admin_delete_dead_gateways",  style="danger")],
        [btn("Delete by ID",  "admin_delete_gateway_prompt", style="danger"),
         btn("🔢 Renumber",   "admin_renumber_gateways",     style="primary")],
        [btn("Back",          "admin_back",                  style="danger")],
    ]))

@router.callback_query(F.data == "admin_add_gateway")
async def admin_add_gateway(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(AddGatewayStates.waiting_for_sites)
    await _safe_edit(callback.message,
        f"➕ <b>Add Gateways</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Send sites one per line or a <b>.txt file</b>:\n\n"
        f"<code>example1.myshopify.com\nexample2.myshopify.com</code>\n\n"
        f"Each site will be tested before adding.\n"
        f"Only <b>CARD_DECLINED</b> or <b>429</b> = alive.\n"
        f"Auto-named: <b>Shopify_V[ID]</b>",
        make_keyboard([[btn("❌ Cancel", "admin_cancel", style="danger")]])
    )

async def _check_site_alive(site: str, proxy: str, api_url: str) -> bool:
    try:
        _, resp_msg, *_ = await check_card(
            card=TEST_CARD, site=site, api_url=api_url,
            proxy=proxy, timeout=GATEWAY_TIMEOUTS.get("Shopify", 35),
        )
        r = (resp_msg or "").lower()
        return "card_declined" in r or "429" in r or "card declined" in r
    except Exception:
        return False

async def _check_site_score(site: str, proxy: str = "", api_url: str = "") -> tuple:
    """
    Returns (score, speed_ms, resp, price).
    score: 2=charge/approved  1=card_declined+price<=11  0=dead/other
    Auto-picks proxy and api from pool if not provided.
    """
    import time as _t
    try:
        # Auto-pick from pool if empty
        _px = proxy
        if not _px:
            _all_px = await get_all_global_proxies()
            _px = random.choice(_all_px) if _all_px else ""
        _url = api_url
        if not _url:
            _apis = await get_apis(limit=50)
            if _apis:
                _url = random.choice(_apis)["api_url"]

        t0 = _t.time()
        result = await check_card(
            card=TEST_CARD, site=site, api_url=_url,
            proxy=_px, timeout=GATEWAY_TIMEOUTS.get("Shopify", 35),
        )
        speed = int((_t.time() - t0) * 1000)
        # Unpack flexibly (5 or 6 return values)
        _, resp_msg, is_live, price, elapsed = result[0], result[1], result[2], result[3], result[4]
        price_val  = float(price) if price else 0.0
        r          = (resp_msg or "").lower()
        resp_short = (resp_msg or "")[:40]

        # ── Determine score ──
        if is_live or "charged" in r or "approved" in r or "payment successful" in r:
            score = 2
        elif ("card_declined" in r or "card declined" in r) and price_val <= 11:
            score = 1
        else:
            score = 0

        _tag  = {2: "CHARGED/APPROVED", 1: "CARD_DECLINED", 0: "DEAD/SKIP"}.get(score, "?")
        _icon = {2: "✅", 1: "🟡", 0: "❌"}.get(score, "?")

        log.info(
            "\n"
            "┌─────────────────────────────────────────\n"
            f"│  {_icon}  SITE CHECK  [{_tag}]\n"
            "├─────────────────────────────────────────\n"
            f"│  Site     : {site}\n"
            f"│  Response : {resp_msg}\n"
            f"│  Price    : ${price_val:.2f}\n"
            f"│  Speed    : {speed}ms\n"
            f"│  Proxy    : {_px or 'None'}\n"
            f"│  API      : {_url[:60]}{'…' if len(_url)>60 else ''}\n"
            "└─────────────────────────────────────────"
        )

        return score, speed, resp_short, price_val
    except Exception as e:
        log.warning(
            "\n"
            "┌─────────────────────────────────────────\n"
            f"│  ⚠️  SITE CHECK ERROR\n"
            "├─────────────────────────────────────────\n"
            f"│  Site  : {site}\n"
            f"│  Error : {e}\n"
            "└─────────────────────────────────────────"
        )
        return 0, 0, str(e)[:40], 0.0

@router.message(AddGatewayStates.waiting_for_sites)
async def handle_add_gateway_sites(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if message.document:
        try:
            f = await message.bot.get_file(message.document.file_id)
            c = await message.bot.download_file(f.file_path)
            raw_text = c.read().decode("utf-8", errors="ignore")
        except Exception:
            await message.answer("❌ Failed to read file."); return
    elif message.text:
        raw_text = message.text
    else:
        await message.answer("Send text or .txt file."); return

    sites = [l.strip().lower() for l in raw_text.splitlines()
             if l.strip() and not l.strip().startswith("#")]
    if not sites:
        await message.answer("⚠️ No valid sites found."); return

    await state.clear()
    apis = await get_apis(limit=50)
    if not apis:
        await message.answer("❌ No APIs configured. Add one first."); return
    api_url = random.choice(apis)["api_url"]
    proxies = await get_all_global_proxies() or await get_user_proxies(message.from_user.id)
    proxy   = random.choice(proxies) if proxies else ""

    uid       = message.from_user.id
    stop_ev   = asyncio.Event()
    _stop_events[uid] = stop_ev
    start_ts  = time.time()

    prog = await message.answer(
        f"⚡ <b>Starting...</b>  0/{len(sites)}",
        parse_mode="HTML",
        reply_markup=make_keyboard([[btn("⏹ Stop", "admin_gw_stop", style="danger")]])
    )

    results    = []
    _lock      = asyncio.Lock()
    done_count = [0]
    added_c    = [0]
    dead_c     = [0]
    high_price = [0]
    sem        = asyncio.Semaphore(5)

    async def _test(site):
        if stop_ev.is_set(): return
        async with sem:
            if stop_ev.is_set(): return
            score, speed, resp, price = await _check_site_score(site, proxy, api_url)
            gid   = None
            label = ""
            if score == 2:
                gid = await add_gateway("Shopify", site, message.from_user.id)
                label = "CHARGED"
            elif score == 1:
                gid = await add_gateway("Shopify", site, message.from_user.id)
                label = "DECLINED"
            elif price > 11 and ("card_declined" in resp.lower() or "card declined" in resp.lower()):
                label = "HIGH_PRICE"
            else:
                label = "DEAD"

            async with _lock:
                results.append((site, score, speed, resp, gid, price, label))
                done_count[0] += 1
                if gid:              added_c[0]    += 1
                if label == "DEAD":  dead_c[0]     += 1
                if label == "HIGH_PRICE": high_price[0] += 1
                snap    = done_count[0]
                elapsed = time.time() - start_ts
                cs      = f"{snap/elapsed:.1f}" if elapsed > 0 else "0"

            if snap % 5 == 0 or snap == len(sites):
                try:
                    bar_filled = int((snap / len(sites)) * 10)
                    bar = "█" * bar_filled + "░" * (10 - bar_filled)
                    await prog.edit_text(
                        f"⚡ <b>Adding Gateways</b>\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"[{bar}]  {snap}/{len(sites)}\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"✅ <b>Added</b>     : <b>{added_c[0]}</b>\n"
                        f"💀 <b>Dead</b>      : <b>{dead_c[0]}</b>\n"
                        f"💸 <b>High Price</b>: <b>{high_price[0]}</b>  (>$11)\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"⚡ Speed: <b>{cs} s/s</b>",
                        parse_mode="HTML",
                        reply_markup=make_keyboard([[btn("⏹ Stop", "admin_gw_stop", style="danger")]])
                    )
                except Exception: pass

    await asyncio.gather(*[_test(s) for s in sites])
    _stop_events.pop(uid, None)

    await reorder_gateways()

    elapsed_total = time.time() - start_ts
    stopped       = stop_ev.is_set()

    results.sort(key=lambda r: (-r[1], r[2]))
    alive    = [r for r in results if r[4] is not None]
    dead     = [r for r in results if r[6] == "DEAD"]
    hi_price = [r for r in results if r[6] == "HIGH_PRICE"]
    charged  = [r for r in results if r[1] == 2]
    declined = [r for r in results if r[1] == 1]

    lines = [
        f"{'⏹' if stopped else '✅'} <b>{'Stopped' if stopped else 'Done'}</b>\n"
        f"★━━━━━━━━━━━━━━━━★\n"
        f"📊 <b>Total Tested</b>  : <b>{done_count[0]}</b> / {len(sites)}\n"
        f"✅ <b>Added</b>         : <b>{len(alive)}</b>\n"
        f"💀 <b>Dead</b>          : <b>{len(dead)}</b>  (no response)\n"
        f"💸 <b>High Price</b>    : <b>{len(hi_price)}</b>  (>$11, skipped)\n"
        f"⏱ <b>Time</b>          : <b>{elapsed_total:.1f}s</b>\n"
        f"★━━━━━━━━━━━━━━━━★"
    ]

    if charged:
        lines.append(f"⚡ <b>CHARGED / APPROVED</b>  [{len(charged)}]")
        for site, score, speed, resp, gid, price, label in charged[:15]:
            lines.append(f"  ✅ <b>V{gid}</b>  ${price:.2f}  {speed}ms  <code>{resp[:30]}</code>")
        if len(charged) > 15:
            lines.append(f"  … +{len(charged)-15} more")

    if declined:
        lines.append(f"🟡 <b>CARD_DECLINED  ≤$11</b>  [{len(declined)}]")
        for site, score, speed, resp, gid, price, label in declined[:15]:
            lines.append(f"  🟡 <b>V{gid}</b>  ${price:.2f}  {speed}ms  <code>{resp[:30]}</code>")
        if len(declined) > 15:
            lines.append(f"  … +{len(declined)-15} more")

    if hi_price:
        lines.append(f"💸 <b>HIGH PRICE  >$11</b>  [{len(hi_price)}]  (not added)")
        for site, score, speed, resp, gid, price, label in hi_price[:8]:
            lines.append(f"  💸 ${price:.2f}  <code>{site[:30]}</code>  <code>{resp[:25]}</code>")
        if len(hi_price) > 8:
            lines.append(f"  … +{len(hi_price)-8} more")

    if dead:
        lines.append(f"💀 <b>DEAD / NO RESPONSE</b>  [{len(dead)}]")
        for site, score, speed, resp, gid, price, label in dead[:8]:
            lines.append(f"  💀 <code>{site[:30]}</code>  <code>{resp[:25]}</code>")
        if len(dead) > 8:
            lines.append(f"  … +{len(dead)-8} more")

    await prog.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=make_keyboard([[btn("Back", "admin_gateways", style="danger")]])
    )
@router.callback_query(F.data.startswith("admin_view_gateways:"))
async def admin_view_gateways(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    page     = int(callback.data.split(":")[1])
    per_page = 10
    total    = await count_gateways()
    pages    = max(1, (total + per_page - 1) // per_page)
    page     = max(1, min(page, pages))
    gateways = await get_gateways(per_page, (page - 1) * per_page)
    if not gateways:
        await _safe_edit(callback.message, "⚠️ <b>No gateways found.</b>",
            make_keyboard([[btn("⬅️ Back", "admin_gateways", style="danger")]])); return

    text = (
        f"🛍️ <b>Gateways</b>  ·  Page {page}/{pages}  ·  Total: {total}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    for g in gateways:
        ic = "✅" if g["status"] == "working" else "❌" if g["status"] == "dead" else "⏳"
        text += f"{ic} <b>Shopify_V{g['id']}</b>  <code>{g['site']}</code>  {g['speed']}ms\n"

    # Navigation row — -100 / -10 / ◀ / page / ▶ / +10 / +100
    nav = []
    if page > 100: nav.append(btn("«100", f"admin_view_gateways:{page-100}", style="primary"))
    if page > 10:  nav.append(btn("«10",  f"admin_view_gateways:{page-10}",  style="primary"))
    if page > 1:   nav.append(btn("◀",    f"admin_view_gateways:{page-1}",   style="primary"))
    nav.append(btn(f"{page}/{pages}", "ignore", style="default"))
    if page < pages:       nav.append(btn("▶",    f"admin_view_gateways:{page+1}",   style="primary"))
    if page + 9 < pages:   nav.append(btn("10»",  f"admin_view_gateways:{page+10}",  style="primary"))
    if page + 99 < pages:  nav.append(btn("100»", f"admin_view_gateways:{page+100}", style="primary"))

    # Per-gateway row: 🔍 flip/detail + 🗑️ delete — 5 per row
    offset_base = (page - 1) * per_page
    gw_btns = [
        btn(f"🔍 V{g['id']}", f"admin_gw_detail:{offset_base + i}:{page}", style="primary")
        for i, g in enumerate(gateways)
    ]
    del_btns = [
        btn(f"🗑️ V{g['id']}", f"admin_delete_gateway:{g['id']}", style="danger")
        for g in gateways
    ]

    rows = [nav]
    rows.append(gw_btns[:5])
    if gw_btns[5:]: rows.append(gw_btns[5:])
    rows.append(del_btns[:5])
    if del_btns[5:]: rows.append(del_btns[5:])
    rows.append([btn("⬅️ Back", "admin_gateways", style="danger")])
    await _safe_edit(callback.message, text, make_keyboard(rows))

@router.callback_query(F.data.startswith("admin_gw_detail:"))
async def admin_gw_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    parts      = callback.data.split(":")
    gw_index   = int(parts[1])
    list_page  = int(parts[2])
    total      = await count_gateways()
    gw_index   = max(0, min(gw_index, total - 1))

    gws = await get_gateways(limit=1, offset=gw_index)
    if not gws:
        await callback.message.answer("⚠️ Gateway not found."); return
    g  = gws[0]
    ic = "✅" if g["status"] == "working" else "❌" if g["status"] == "dead" else "⏳"

    text = (
        f"🔍 <b>Gateway Detail</b>  ·  {gw_index + 1}/{total}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID</b>      :  <b>Shopify_V{g['id']}</b>\n"
        f"🌐 <b>Site</b>    :  <code>{g['site']}</code>\n"
        f"{ic} <b>Status</b>  :  <b>{g['status']}</b>\n"
        f"⚡ <b>Speed</b>   :  <b>{g['speed']}ms</b>\n"
        f"👤 <b>Added By</b>:  <b>{g['added_by']}</b>"
    )

    nav = []
    if gw_index > 0:
        nav.append(btn("◀ Prev", f"admin_gw_detail:{gw_index-1}:{list_page}", style="primary"))
    nav.append(btn(f"{gw_index+1}/{total}", "ignore", style="default"))
    if gw_index < total - 1:
        nav.append(btn("Next ▶", f"admin_gw_detail:{gw_index+1}:{list_page}", style="primary"))

    rows = [
        nav,
        [
            btn("🔍 Test",   f"admin_check_single_gw:{g['id']}:{gw_index}:{list_page}", style="success"),
            btn("🗑️ Delete", f"admin_delete_gateway:{g['id']}",                          style="danger"),
        ],
        [btn("⬅️ Back to List", f"admin_view_gateways:{list_page}", style="danger")],
    ]
    await _safe_edit(callback.message, text, make_keyboard(rows))

@router.callback_query(F.data.startswith("admin_check_single_gw:"))
async def admin_check_single_gw(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer("🔍 Testing...")
    parts     = callback.data.split(":")
    gw_id     = int(parts[1])
    gw_index  = int(parts[2])
    list_page = int(parts[3])
    gw = await get_gateway(gw_id)
    if not gw:
        await callback.message.answer("❌ Gateway not found."); return
    apis = await get_apis(limit=50)
    if not apis:
        await callback.message.answer("❌ No APIs configured."); return
    api_url = random.choice(apis)["api_url"]
    proxies = await get_all_global_proxies() or [""]
    proxy   = random.choice(proxies)
    score, speed, _resp, _price = await _check_site_score(gw["site"], proxy, api_url)
    status  = "working" if score > 0 else "dead"
    tag     = "🟢 Charge/Approved" if score == 2 else "🟡 Declined (Alive)" if score == 1 else "🔴 Dead"
    await update_gateway_status(gw_id, status, speed)
    ic      = "✅" if score > 0 else "❌"
    total   = await count_gateways()
    text = (
        f"🔍 <b>Gateway Test Result</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID</b>     :  <b>Shopify_V{gw_id}</b>\n"
        f"🌐 <b>Site</b>   :  <code>{gw['site']}</code>\n"
        f"{ic} <b>Result</b> :  <b>{tag}</b>\n"
        f"⚡ <b>Speed</b>  :  <b>{speed}ms</b>\n"
        f"🛡️ <b>Proxy</b>  :  <code>{proxy or 'None'}</code>"
    )
    nav = []
    if gw_index > 0:
        nav.append(btn("◀ Prev", f"admin_gw_detail:{gw_index-1}:{list_page}", style="primary"))
    nav.append(btn(f"{gw_index+1}/{total}", "ignore", style="default"))
    if gw_index < total - 1:
        nav.append(btn("Next ▶", f"admin_gw_detail:{gw_index+1}:{list_page}", style="primary"))
    rows = [
        nav,
        [btn("⬅️ Back to List", f"admin_view_gateways:{list_page}", style="danger")],
    ]
    await _safe_edit(callback.message, text, make_keyboard(rows))
@router.callback_query(F.data.startswith("admin_delete_gateway:"))
async def admin_delete_gateway(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    gid = int(callback.data.split(":")[1])
    gw = await get_gateway(gid)
    if not gw: await callback.message.answer("Not found."); return
    await _safe_edit(callback.message,
        f"⚠️ <b>Delete Gateway?</b>\n━━━━━━━━━━━━━━━━\n"
        f"🛍️ <b>Shopify_V{gid}</b>\n🌐 <code>{gw['site']}</code>",
        make_keyboard([[
            btn("✅ Confirm", f"admin_confirm_delete_gateway:{gid}", style="danger"),
            btn("❌ Cancel",  "admin_view_gateways:1",              style="primary"),
        ]])
    )

@router.callback_query(F.data.startswith("admin_confirm_delete_gateway:"))
async def admin_confirm_delete_gateway(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    gid = int(callback.data.split(":")[1])
    await delete_gateway(gid)
    await reorder_gateways()
    await callback.answer(f"✅ Gateway deleted & renumbered.", show_alert=False)
    await admin_gateways(callback)

@router.callback_query(F.data == "admin_delete_gateway_prompt")
async def admin_delete_gateway_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(DeleteGatewayStates.waiting_for_id)
    await _safe_edit(callback.message,
        "🗑️ <b>Delete Gateway by ID</b>\n━━━━━━━━━━━━━━━━\nSend the Gateway ID:",
        make_keyboard([[btn("❌ Cancel","admin_cancel",style="danger")]])
    )

@router.message(DeleteGatewayStates.waiting_for_id)
async def delete_gateway_by_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not message.text:
        await message.answer("Send the ID as text."); return
    try:
        gid = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid ID."); return
    gw = await get_gateway(gid)
    if not gw:
        await message.answer("Gateway not found."); await state.clear(); return
    await delete_gateway(gid)
    await reorder_gateways()
    await state.clear()
    await message.answer(
        f"🗑️ <b>Deleted:</b> Shopify_V{gid}\n🌐 <code>{gw['site']}</code>\n✅ IDs renumbered.",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_delete_dead_gateways")
async def admin_delete_dead_gateways(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await _safe_edit(callback.message, "⏳ <b>Deleting dead gateways...</b>", None)
    deleted = await delete_dead_gateways()
    if deleted:
        await reorder_gateways()
    await callback.message.edit_text(
        f"🗑️ <b>Deleted {deleted} dead gateways.</b>\n✅ IDs renumbered.",
        parse_mode="HTML",
        reply_markup=make_keyboard([[btn("⬅️ Back", "admin_gateways", style="danger")]])
    )

@router.callback_query(F.data == "admin_renumber_gateways")
async def admin_renumber_gateways(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await _safe_edit(callback.message, "⏳ <b>Renumbering gateways...</b>", None)
    await reorder_gateways()
    total = await count_gateways()
    await _safe_edit(callback.message,
        f"✅ <b>Gateways renumbered!</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Now: <b>1 → {total}</b> sequential IDs.",
        make_keyboard([[btn("⬅️ Back", "admin_gateways", style="danger")]])
    )

@router.callback_query(F.data == "admin_check_all_gateways")
async def admin_check_all_gateways(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    total   = await count_gateways()
    apis    = await get_apis(limit=50)
    if not total or not apis:
        await _safe_edit(callback.message, "❌ No gateways or APIs.",
            make_keyboard([[btn("Back","admin_gateways",style="danger")]])); return

    api_url = random.choice(apis)["api_url"]
    proxies = await get_all_global_proxies() or [""]
    all_gws = await get_gateways(total)
    await _safe_edit(callback.message,
        f"⏳ <b>Checking {total} gateways...</b>", None)

    uid      = callback.from_user.id
    stop_ev  = asyncio.Event()
    _stop_events[uid] = stop_ev
    start_ts = time.time()

    results: dict = {}
    _lock    = asyncio.Lock()
    sem      = asyncio.Semaphore(5)
    done_c   = [0]

    async def _chk(gw):
        if stop_ev.is_set(): return
        async with sem:
            if stop_ev.is_set(): return
            proxy = random.choice(proxies)
            score, speed, resp, price = await _check_site_score(gw["site"], proxy, api_url)
            async with _lock:
                results[gw["id"]] = (score, speed, resp, price)
                done_c[0] += 1
                snap     = done_c[0]
                elapsed  = time.time() - start_ts
                cs       = f"{snap/elapsed:.1f}" if elapsed > 0 else "0"

            if snap % 5 == 0 or snap == total:
                alive_s = sum(1 for v in results.values() if v[0] > 0)
                dead_s  = sum(1 for v in results.values() if v[0] == 0)
                try:
                    bar_filled = int((snap / total) * 10)
                    bar = "█" * bar_filled + "░" * (10 - bar_filled)
                    await callback.message.edit_text(
                        f"⚡ <b>Checking Gateways</b>\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"[{bar}]  {snap}/{total}\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"✅ <b>Alive</b> : <b>{alive_s}</b>\n"
                        f"💀 <b>Dead</b>  : <b>{dead_s}</b>\n"
                        f"⚡ Speed: <b>{cs} s/s</b>",
                        parse_mode="HTML",
                        reply_markup=make_keyboard([[btn("⏹ Stop", "admin_gw_stop", style="danger")]])
                    )
                except Exception: pass

    await asyncio.gather(*[_chk(g) for g in all_gws])
    _stop_events.pop(uid, None)

    stopped      = stop_ev.is_set()
    elapsed_total= time.time() - start_ts
    dead_gws = []; alive_gws = []
    for gw in all_gws:
        score, speed, resp, price = results.get(gw["id"], (0, 0, "", 0))
        if score == 0:
            await delete_gateway(gw["id"])
            dead_gws.append({**gw, "_resp": resp})
        else:
            await update_gateway_status(gw["id"], "working", speed)
            alive_gws.append({**gw, "_score": score, "_speed": speed, "_resp": resp, "_price": price})

    if dead_gws:
        await reorder_gateways()

    alive_gws.sort(key=lambda g: (-g["_score"], g["_speed"]))
    charged_gws  = [g for g in alive_gws if g["_score"] == 2]
    declined_gws = [g for g in alive_gws if g["_score"] == 1]

    _st   = "⏹" if stopped else "✅"
    _stxt = "Stopped" if stopped else "Check Complete"
    lines = [
        f"{_st} <b>{_stxt}</b>\n"
        f"★━━━━━━━━━━━━━━━━★\n"
        f"📊 <b>Checked</b>       : <b>{done_c[0]}</b> / {total}\n"
        f"⚡ <b>Charged/Approved</b>: <b>{len(charged_gws)}</b>\n"
        f"🟡 <b>CARD_DECLINED</b>  : <b>{len(declined_gws)}</b>\n"
        f"💀 <b>Dead (deleted)</b> : <b>{len(dead_gws)}</b>\n"
        f"⏱ <b>Time</b>           : <b>{elapsed_total:.1f}s</b>\n"
        f"★━━━━━━━━━━━━━━━━★"
    ]

    if charged_gws:
        lines.append(f"⚡ <b>CHARGED / APPROVED</b>  [{len(charged_gws)}]")
        for g in charged_gws[:10]:
            lines.append(f"  ✅ <b>V{g['id']}</b>  ${g['_price']:.2f}  {g['_speed']}ms  <code>{g['_resp'][:28]}</code>")
        if len(charged_gws) > 10:
            lines.append(f"  … +{len(charged_gws)-10} more")

    if declined_gws:
        lines.append(f"🟡 <b>CARD_DECLINED  ≤$11</b>  [{len(declined_gws)}]")
        for g in declined_gws[:10]:
            lines.append(f"  🟡 <b>V{g['id']}</b>  ${g['_price']:.2f}  {g['_speed']}ms  <code>{g['_resp'][:28]}</code>")
        if len(declined_gws) > 10:
            lines.append(f"  … +{len(declined_gws)-10} more")

    if dead_gws:
        lines.append(f"💀 <b>DEAD (removed)</b>  [{len(dead_gws)}]")
        for g in dead_gws[:8]:
            lines.append(f"  💀 <code>{g['site'][:30]}</code>  <code>{g['_resp'][:25]}</code>")
        if len(dead_gws) > 8:
            lines.append(f"  … +{len(dead_gws)-8} more")

    await _safe_edit(
        callback.message,
        "\n".join(lines),
        make_keyboard([[btn("Back", "admin_gateways", style="danger")]])
    )
#  APIs
@router.callback_query(F.data == "admin_apis")
async def admin_apis(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    total = await count_apis()
    await _safe_edit(callback.message,
        f"🔗 <b>APIs</b>\n━━━━━━━━━━━━━━━━\nTotal: <b>{total}</b> APIs",
        make_keyboard([
            [btn("➕ Add API",     "admin_add_api",         style="success")],
            [btn("📋 View",        "admin_view_apis:1",     style="primary"),
             btn("🔍 Check All",   "admin_check_all_apis",  style="primary")],
            [btn("🗑️ Delete by ID","admin_delete_api_prompt",style="danger")],
            [btn("⬅️ Back",        "admin_back",            style="danger")],
        ])
    )

@router.callback_query(F.data == "admin_add_api")
async def admin_add_api(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(AddAPIStates.waiting_for_url)
    await _safe_edit(callback.message,
        f"➕ <b>Add API</b>\n━━━━━━━━━━━━━━━━\n"
        f"Send the API URL template:\n"
        f"<code>https://api.example.com/check?site={{site}}&card={{card}}&proxy={{proxy}}</code>",
        make_keyboard([[btn("❌ Cancel","admin_cancel",style="danger")]])
    )

@router.message(AddAPIStates.waiting_for_url)
async def add_api_url(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not message.text:
        await message.answer("Send the URL as text."); return
    url = message.text.strip()
    if not url:
        await message.answer("URL cannot be empty."); return
    api_id = await add_api(url, message.from_user.id)
    await state.clear()
    await message.answer(
        f"✅ <b>API Added</b>\n━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>API_V{api_id}</b>\n"
        f"🆔 ID: <code>{api_id}</code>\n"
        f"📎 <code>{url[:80]}</code>",
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("admin_view_apis:"))
async def admin_view_apis(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    page     = int(callback.data.split(":")[1])
    per_page = 10
    total    = await count_apis()
    pages    = max(1, (total + per_page - 1) // per_page)
    page     = max(1, min(page, pages))
    apis     = await get_apis(per_page, (page - 1) * per_page)
    if not apis:
        await _safe_edit(callback.message, "⚠️ <b>No APIs found.</b>",
            make_keyboard([[btn("⬅️ Back", "admin_apis", style="danger")]])); return

    text = (
        f"🔗 <b>APIs</b>  ·  Page {page}/{pages}  ·  Total: {total}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    for api in apis:
        ic      = "✅" if api["status"] == "working" else "❌" if api["status"] == "dead" else "⏳"
        preview = api["api_url"][:45] + "…" if len(api["api_url"]) > 45 else api["api_url"]
        text += f"{ic} <b>API_V{api['id']}</b>  {api['speed']}ms\n    <code>{preview}</code>\n"

    nav = []
    if page > 100: nav.append(btn("«100", f"admin_view_apis:{page-100}", style="primary"))
    if page > 10:  nav.append(btn("«10",  f"admin_view_apis:{page-10}",  style="primary"))
    if page > 1:   nav.append(btn("◀",    f"admin_view_apis:{page-1}",   style="primary"))
    nav.append(btn(f"{page}/{pages}", "ignore", style="default"))
    if page < pages:       nav.append(btn("▶",    f"admin_view_apis:{page+1}",   style="primary"))
    if page + 9 < pages:   nav.append(btn("10»",  f"admin_view_apis:{page+10}",  style="primary"))
    if page + 99 < pages:  nav.append(btn("100»", f"admin_view_apis:{page+100}", style="primary"))

    offset_base = (page - 1) * per_page
    chk_btns = [
        btn(f"🔍 V{api['id']}", f"admin_check_api:{api['id']}", style="primary")
        for api in apis
    ]
    del_btns = [
        btn(f"🗑️ V{api['id']}", f"admin_delete_api:{api['id']}", style="danger")
        for api in apis
    ]

    rows = [nav]
    rows.append(chk_btns[:5])
    if chk_btns[5:]: rows.append(chk_btns[5:])
    rows.append(del_btns[:5])
    if del_btns[5:]: rows.append(del_btns[5:])
    rows.append([btn("⬅️ Back", "admin_apis", style="danger")])
    await _safe_edit(callback.message, text, make_keyboard(rows))

@router.callback_query(F.data.startswith("admin_delete_api:"))
async def admin_delete_api(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    api_id = int(callback.data.split(":")[1])
    api = await get_api(api_id)
    if not api: await callback.message.answer("API not found."); return
    await _safe_edit(callback.message,
        f"⚠️ <b>Delete API_V{api_id}?</b>\n━━━━━━━━━━━━━━━━\n"
        f"<code>{api['api_url'][:100]}</code>",
        make_keyboard([[
            btn("✅ Confirm", f"admin_confirm_delete_api:{api_id}", style="danger"),
            btn("❌ Cancel",  "admin_view_apis:1",                  style="primary"),
        ]])
    )

@router.callback_query(F.data.startswith("admin_confirm_delete_api:"))
async def admin_confirm_delete_api(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    api_id = int(callback.data.split(":")[1])
    await delete_api(api_id)
    await callback.answer(f"✅ API {api_id} deleted.")
    await admin_apis(callback)

@router.callback_query(F.data == "admin_delete_api_prompt")
async def admin_delete_api_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(DeleteAPIStates.waiting_for_id)
    await _safe_edit(callback.message,
        "🗑️ <b>Delete API by ID</b>\n━━━━━━━━━━━━━━━━\nSend the API ID:",
        make_keyboard([[btn("❌ Cancel","admin_cancel",style="danger")]])
    )

@router.message(DeleteAPIStates.waiting_for_id)
async def delete_api_by_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not message.text: await message.answer("Send the ID."); return
    try:
        api_id = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid ID."); return
    api = await get_api(api_id)
    if not api:
        await message.answer("API not found."); await state.clear(); return
    await delete_api(api_id)
    await state.clear()
    await message.answer(f"🗑️ <b>API_V{api_id} deleted.</b>", parse_mode="HTML")

def _build_api_url(template, site, card, proxy):
    return template.replace("{site}", site).replace("{card}", card).replace("{proxy}", proxy)

@router.callback_query(F.data.startswith("admin_check_api:"))
async def admin_check_api(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    api_id = int(callback.data.split(":")[1])
    api    = await get_api(api_id)
    if not api:
        await _safe_edit(callback.message,"❌ API not found.",
            make_keyboard([[btn("⬅️ Back","admin_apis",style="danger")]])); return
    gws = await get_gateways(limit=1)
    if not gws:
        await _safe_edit(callback.message,"❌ No gateways found.",
            make_keyboard([[btn("⬅️ Back","admin_apis",style="danger")]])); return
    gw  = gws[0]
    proxies = await get_all_global_proxies() or [""]
    proxy   = random.choice(proxies)
    url     = _build_api_url(api["api_url"], gw["site"], TEST_CARD, proxy)
    await _safe_edit(callback.message, f"⏳ Checking API_V{api_id}...", None)
    status, resp, is_live, price, elapsed, *_ = await check_card(
        card=TEST_CARD, site=gw["site"], api_url=url,
        proxy=proxy, timeout=GATEWAY_TIMEOUTS.get("Shopify", 35)
    )
    ok      = "CARD_DECLINED" in resp or "429" in resp
    s_str   = "working" if ok else "dead"
    speed   = int(elapsed * 1000)
    await update_api_status(api_id, s_str, speed)
    icon = "✅" if ok else "❌"
    await _safe_edit(callback.message,
        f"🔗 <b>API Check — API_V{api_id}</b>\n━━━━━━━━━━━━━━━━\n"
        f"{icon} Status  : <b>{s_str}</b>\n"
        f"⚡ Speed   : <b>{speed}ms</b>\n"
        f"💬 Response: <code>{resp[:200]}</code>\n"
        f"🛡️ Proxy   : <code>{proxy or 'None'}</code>",
        make_keyboard([[btn("⬅️ Back","admin_view_apis:1",style="danger")]])
    )

@router.callback_query(F.data == "admin_check_all_apis")
async def admin_check_all_apis(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    gws = await get_gateways(limit=1)
    if not gws:
        await _safe_edit(callback.message,"❌ No gateways.",
            make_keyboard([[btn("⬅️ Back","admin_apis",style="danger")]])); return
    gw      = gws[0]
    total   = await count_apis()
    proxies = await get_all_global_proxies() or [""]
    all_apis= await get_apis(limit=total)
    await _safe_edit(callback.message, f"⏳ <b>Checking {total} APIs...</b>", None)

    working = 0; dead = 0
    sem = asyncio.Semaphore(50)

    async def _chk(api):
        nonlocal working, dead
        async with sem:
            proxy = random.choice(proxies)
            url   = _build_api_url(api["api_url"], gw["site"], TEST_CARD, proxy)
            _, resp, _, _, elapsed, *_ = await check_card(
                card=TEST_CARD, site=gw["site"], api_url=url,
                proxy=proxy, timeout=GATEWAY_TIMEOUTS.get("Shopify", 35)
            )
            ok    = "CARD_DECLINED" in resp or "429" in resp
            speed = int(elapsed * 1000)
            await update_api_status(api["id"], "working" if ok else "dead", speed)
            if ok: working += 1
            else:  dead    += 1

    await asyncio.gather(*[_chk(a) for a in all_apis])
    await _safe_edit(callback.message,
        f"✅ <b>All APIs Checked</b>\n━━━━━━━━━━━━━━━━\n"
        f"✅ Working : <b>{working}</b>\n❌ Dead : <b>{dead}</b>",
        make_keyboard([[btn("⬅️ Back","admin_apis",style="danger")]])
    )
#  Proxy Pool Manager
@router.callback_query(F.data.startswith("admin_proxy_pool:"))
async def admin_proxy_pool(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    page     = int(callback.data.split(":")[1])
    per_page = 10
    all_px   = await get_all_global_proxies()
    total    = len(all_px)
    pages    = max(1, (total + per_page - 1) // per_page)
    page     = max(1, min(page, pages))
    chunk    = all_px[(page - 1) * per_page : page * per_page]

    text = (
        f"🛡️ <b>Proxy Pool</b>  ·  Page {page}/{pages}  ·  Total: {total}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    for i, px in enumerate(chunk, 1):
        host = px.split("@")[-1] if "@" in px else px.split("//")[-1]
        text += f"<code>{(page-1)*per_page+i:3}.  {host}</code>\n"

    nav = []
    if page > 100: nav.append(btn("«100", f"admin_proxy_pool:{page-100}", style="primary"))
    if page > 10:  nav.append(btn("«10",  f"admin_proxy_pool:{page-10}",  style="primary"))
    if page > 1:   nav.append(btn("◀",    f"admin_proxy_pool:{page-1}",   style="primary"))
    nav.append(btn(f"{page}/{pages}", "ignore", style="default"))
    if page < pages:       nav.append(btn("▶",    f"admin_proxy_pool:{page+1}",   style="primary"))
    if page + 9 < pages:   nav.append(btn("10»",  f"admin_proxy_pool:{page+10}",  style="primary"))
    if page + 99 < pages:  nav.append(btn("100»", f"admin_proxy_pool:{page+100}", style="primary"))

    rows = [
        nav,
        [btn("➕ Add",          "admin_proxy_add",        style="success"),
         btn("🔍 Test & Clean", "admin_proxy_test",       style="primary")],
        [btn("📤 Export",       "admin_proxy_export",     style="default"),
         btn("🗑️ Delete One",   "admin_proxy_delete_one", style="danger")],
        [btn("💥 Delete All",   "admin_proxy_delete_all", style="danger"),
         btn("⬅️ Back",         "admin_back",             style="danger")],
    ]
    await _safe_edit(callback.message, text, make_keyboard(rows))
@router.callback_query(F.data == "admin_proxy_add")
async def admin_proxy_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(ProxyStates.waiting_for_proxy)
    await _safe_edit(callback.message,
        "➕ <b>Add Proxies to Pool</b>\n━━━━━━━━━━━━━━━━\n"
        "Send proxies one per line or a <b>.txt file</b>:\n"
        "<code>host:port\nuser:pass@host:port</code>",
        make_keyboard([[btn("❌ Cancel","admin_proxy_pool:1",style="danger")]])
    )

@router.message(ProxyStates.waiting_for_proxy)
async def handle_proxy_add(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if message.document:
        try:
            f = await message.bot.get_file(message.document.file_id)
            c = await message.bot.download_file(f.file_path)
            raw = c.read().decode("utf-8", errors="ignore")
        except Exception:
            await message.answer("❌ Failed to read file."); return
    elif message.text:
        raw = message.text
    else:
        await message.answer("Send text or .txt file."); return

    proxies = [l.strip() for l in raw.splitlines() if l.strip()]
    if not proxies:
        await message.answer("⚠️ No proxies found."); return

    await state.clear()
    added = dup = 0
    existing = set(await get_all_global_proxies())
    for px in proxies:
        if px in existing:
            dup += 1
        else:
            await add_global_proxy(px)
            existing.add(px)
            added += 1
    await message.answer(
        f"✅ <b>Proxies Added</b>\n━━━━━━━━━━━━━━━━\n"
        f"✅ Added     : <b>{added}</b>\n"
        f"♻️ Duplicate : <b>{dup}</b>\n"
        f"📊 Total Pool: <b>{len(existing)}</b>",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_proxy_delete_one")
async def admin_proxy_delete_one_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(ProxyStates.waiting_delete_host)
    await _safe_edit(callback.message,
        "🗑️ <b>Delete Proxy</b>\n━━━━━━━━━━━━━━━━\nSend the proxy to delete (host:port or full):",
        make_keyboard([[btn("❌ Cancel","admin_proxy_pool:1",style="danger")]])
    )

@router.message(ProxyStates.waiting_delete_host)
async def handle_proxy_delete_one(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not message.text: await message.answer("Send the proxy string."); return
    target = message.text.strip()
    await state.clear()
    try:
        await delete_global_proxy(target)
        await message.answer(f"✅ Deleted: <code>{escape(target)}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")

@router.callback_query(F.data == "admin_proxy_delete_all")
async def admin_proxy_delete_all(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return

    await callback.answer()
    await _safe_edit(callback.message,
        "⚠️ <b>Delete ALL proxies from pool?</b>\nThis cannot be undone!",
        make_keyboard([[
            btn("✅ Yes, Delete All", "admin_proxy_delete_all_confirm", style="danger"),
            btn("❌ Cancel",          "admin_proxy_pool:1",             style="primary"),
        ]])
    )

@router.callback_query(F.data == "admin_proxy_delete_all_confirm")
async def admin_proxy_delete_all_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    proxies = await get_all_global_proxies()
    for px in proxies:
        try: await delete_global_proxy(px)
        except: pass
    await _safe_edit(callback.message,
        f"✅ Deleted <b>{len(proxies)}</b> proxies.",
        make_keyboard([[btn("⬅️ Back","admin_proxy_pool:1",style="danger")]])
    )

@router.callback_query(F.data == "admin_proxy_export")
async def admin_proxy_export(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer("📥 Preparing export...")
    proxies = await get_all_global_proxies()
    if not proxies:
        await callback.message.answer("⚠️ Proxy pool is empty."); return
    content = "\n".join(proxies).encode("utf-8")
    fname   = f"proxies_{int(time.time())}.txt"
    await callback.message.answer_document(
        BufferedInputFile(content, filename=fname),
        caption=f"🛡️ Proxy Pool Export — {len(proxies)} proxies"
    )

@router.callback_query(F.data == "admin_proxy_test")
async def admin_proxy_test(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    proxies = await get_all_global_proxies()
    if not proxies:
        await callback.message.answer("Proxy pool is empty."); return

    total_before = len(proxies)

    seen: set = set(); deduped = []
    for px in proxies:
        if px not in seen:
            seen.add(px); deduped.append(px)
    dup_removed = total_before - len(deduped)

    msg = await callback.message.answer(
        f"⏳ <b>Testing {len(deduped)} proxies...</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Please wait — deleting dead proxies after full test.",
        parse_mode="HTML"
    )

    alive_data: list = []   # list of (speed_ms, proxy_str)
    dead_list:  list = []
    _lock = asyncio.Lock()
    sem   = asyncio.Semaphore(50)

    async def _chk(px):
        async with sem:
            ok, speed, _country = await test_proxy(px)
            async with _lock:
                if ok:
                    alive_data.append((speed, px))
                else:
                    dead_list.append(px)

    await asyncio.gather(*[_chk(px) for px in deduped])

    # --- حذف الميت بعد اكتمال الفحص كاملاً ---
    for px in dead_list:
        try: await delete_global_proxy(px)
        except: pass

    # --- ترتيب الأحياء من الأسرع للأبطأ ---
    alive_data.sort(key=lambda x: x[0])

    # --- حذف الأحياء وإعادة إضافتهم بالترتيب ---
    for _, px in alive_data:
        try: await delete_global_proxy(px)
        except: pass
    for _, px in alive_data:
        try: await add_global_proxy(px)
        except: pass

    fastest = alive_data[0][0]  if alive_data else 0
    slowest = alive_data[-1][0] if alive_data else 0
    avg     = int(sum(s for s, _ in alive_data) / len(alive_data)) if alive_data else 0

    await msg.edit_text(
        f"<b>Pool Cleaned</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Before     : <b>{total_before}</b>\n"
        f"Duplicates : <b>{dup_removed}</b>\n"
        f"Dead       : <b>{len(dead_list)}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Remaining  : <b>{len(alive_data)}</b>  (sorted fastest → slowest)\n"
        f"Fastest    : <b>{fastest}ms</b>  |  Avg: <b>{avg}ms</b>  |  Slowest: <b>{slowest}ms</b>",
        parse_mode="HTML"
    )
#  Broadcast — forward مع إخفاء المرسل
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(BroadcastStates.waiting_for_message)
    users = await get_all_users()
    await _safe_edit(callback.message,
        f"📡 <b>Broadcast</b>\n━━━━━━━━━━━━━━━━\n"
        f"👥 Recipients: <b>{len(users)}</b>\n\n"
        f"Send any message — text, photo, video, sticker, or GIF.\n"
        f"Emojis and formatting are fully supported.\n"
        f"Message will be <b>forwarded anonymously</b> (sender hidden).",
        make_keyboard([[btn("❌ Cancel","admin_cancel_broadcast",style="danger")]])
    )

@router.message(BroadcastStates.waiting_for_message)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    users = await get_all_users()
    if not users:
        await message.answer("No users found."); return

    prog = await message.answer(
        f"📡 <b>Broadcasting to {len(users)} users...</b>",
        parse_mode="HTML"
    )
    sent = failed = 0

    async def _send(uid):
        nonlocal sent, failed
        try:
            # copy_to يحفظ كل أنواع الوسائط ويخفي المرسل
            await message.copy_to(uid)
            sent += 1
        except Exception:
            failed += 1

    sem   = asyncio.Semaphore(25)
    tasks = []
    for uid in users:
        async def _task(u=uid):
            async with sem:
                await _send(u)
                await asyncio.sleep(0.05)
        tasks.append(_task())

    done_count = 0
    for coro in asyncio.as_completed(tasks):
        await coro
        done_count += 1
        if done_count % 50 == 0 or done_count == len(users):
            try:
                await prog.edit_text(
                    f"📡 <b>Broadcasting...</b>\n"
                    f"✅ {sent}  ❌ {failed}  |  {done_count}/{len(users)}",
                    parse_mode="HTML"
                )
            except Exception: pass

    await prog.edit_text(
        f"📡 <b>Broadcast Done</b>\n━━━━━━━━━━━━━━━━\n"
        f"✅ Sent   : <b>{sent}</b>\n"
        f"❌ Failed : <b>{failed}</b>\n"
        f"👥 Total  : <b>{len(users)}</b>",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_cancel_broadcast")
async def admin_cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Cancelled.")
    await _safe_edit(callback.message, "❌ Broadcast cancelled.",
        make_keyboard([[btn("⬅️ Back","admin_back",style="danger")]])
    )

@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Cancelled.")
    await admin_gateways(callback)

# ══════════════════════════════════════════════
#  PayPal Gateways Admin
# ══════════════════════════════════════════════

class AddPPGWStates(StatesGroup):
    waiting_for_sites = State()

@router.callback_query(F.data == "admin_pp_gw")
async def admin_pp_gw(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    total = await count_pp_gateways()
    await _safe_edit(callback.message,
        f"[{get_html('lightning1')}] <b>PayPal Gateways</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Total: <b>{total}</b> gateways",
        make_keyboard([
            [btn("Add",       "admin_pp_add",       style="success"),
             btn("View",      "admin_pp_view:1",    style="primary")],
            [btn("Check All", "admin_pp_check_all", style="primary"),
             btn("Delete Dead","admin_pp_del_dead",  style="danger")],
            [btn("Back",      "admin_back",          style="danger")],
        ])
    )

@router.callback_query(F.data == "admin_pp_add")
async def admin_pp_add(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(AddPPGWStates.waiting_for_sites)
    await _safe_edit(callback.message,
        f"[{get_html('lightning1')}] <b>Add PayPal Gateways</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Send URLs (one per line) or a .txt file.\n"
        f"Format: <code>https://example.com/donate/</code>",
        make_keyboard([[btn("Cancel", "admin_cancel", style="danger")]])
    )

@router.message(AddPPGWStates.waiting_for_sites)
async def handle_add_pp_sites(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if message.document:
        try:
            f   = await message.bot.get_file(message.document.file_id)
            c   = await message.bot.download_file(f.file_path)
            raw = c.read().decode("utf-8", errors="ignore")
        except Exception:
            await message.answer("Failed to read file."); return
    elif message.text:
        raw = message.text
    else:
        await message.answer("Send text or .txt file."); return

    sites = [l.strip() for l in raw.splitlines()
             if l.strip() and not l.strip().startswith("#") and l.strip().startswith("http")]
    if not sites:
        await message.answer(f"{get_html('warning')} No valid URLs found (must start with http)."); return

    await state.clear()
    uid      = message.from_user.id
    stop_ev  = asyncio.Event()
    _stop_events[uid] = stop_ev
    start_ts = time.time()

    prog = await message.answer(
        f"[{get_html('lightning1')}] <b>Testing PayPal sites...</b>  0/{len(sites)}",
        parse_mode="HTML",
        reply_markup=make_keyboard([[btn("⏹ Stop", "admin_gw_stop", style="danger")]])
    )

    results  = []
    _lock    = asyncio.Lock()
    done_c   = [0]
    added_c  = [0]
    dead_c   = [0]
    sem      = asyncio.Semaphore(5)

    async def _test_pp(site):
        if stop_ev.is_set(): return
        async with sem:
            if stop_ev.is_set(): return
            import time as _t
            from paypal import PayPal  # ← صح (كان pp خطأ)
            t0 = _t.time()
            resp_text = "—"
            is_alive  = False
            try:
                loop = asyncio.get_event_loop()
                pp   = PayPal(site, "1.00")
                au_result = await loop.run_in_executor(None, pp.Key)
                speed     = int((_t.time() - t0) * 1000)
                is_alive  = True
                resp_text = f"token={str(au_result[0])[:20]}..." if au_result else "OK"
            except AttributeError as e:
                speed     = int((_t.time() - t0) * 1000)
                resp_text = f"Form not found: {str(e)[:50]}"
            except Exception as e:
                speed     = int((_t.time() - t0) * 1000)
                resp_text = str(e)[:60]

            # Terminal output - detailed and clean
            icon = "✅" if is_alive else "❌"
            print(
                f"\n{'━'*55}\n"
                f"  {icon} {'ALIVE' if is_alive else 'DEAD':<8}  {speed:>5}ms\n"
                f"  🌐 {site}\n"
                f"  📋 {resp_text}\n"
                f"{'━'*55}"
            )

            gid = None
            if is_alive:
                gid = await add_pp_gateway(site, uid)

            async with _lock:
                results.append((site, is_alive, speed, gid, resp_text))
                done_c[0] += 1
                if gid:          added_c[0] += 1
                if not is_alive: dead_c[0]  += 1
                snap       = done_c[0]
                snap_added = added_c[0]
                snap_dead  = dead_c[0]

            if snap % 3 == 0 or snap == len(sites):
                bar_f = int((snap / len(sites)) * 10)
                bar   = "█" * bar_f + "░" * (10 - bar_f)
                try:
                    await prog.edit_text(
                        f"[{get_html('lightning1')}] <b>Testing PayPal</b>\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"[{bar}]  {snap}/{len(sites)}\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"✅ <b>Added</b>  : <b>{snap_added}</b>\n"
                        f"💀 <b>Dead</b>   : <b>{snap_dead}</b>",
                        parse_mode="HTML",
                        reply_markup=make_keyboard([[btn("⏹ Stop", "admin_gw_stop", style="danger")]])
                    )
                except Exception: pass

    await asyncio.gather(*[_test_pp(s) for s in sites])
    _stop_events.pop(uid, None)

    await reorder_pp_gateways()
    elapsed_total = time.time() - start_ts
    stopped       = stop_ev.is_set()
    alive  = [r for r in results if r[1]]
    dead   = [r for r in results if not r[1]]

    lines = [
        f"{'⏹' if stopped else '✅'} <b>{'Stopped' if stopped else 'Done'}</b>\n"
        f"★━━━━━━━━━━━━━━━━★\n"
        f"📊 Tested  : <b>{done_c[0]}</b> / {len(sites)}\n"
        f"✅ Added   : <b>{len(alive)}</b>\n"
        f"💀 Dead    : <b>{len(dead)}</b>\n"
        f"⏱ Time    : <b>{elapsed_total:.1f}s</b>\n"
        f"★━━━━━━━━━━━━━━━━★"
    ]
    if alive:
        lines.append(f"✅ <b>Alive PayPal Sites</b>  [{len(alive)}]")
        for site, _, speed, gid, *__ in alive[:15]:
            lines.append(f"  ✅ <b>PP_V{gid}</b>  {speed}ms  <code>{site[:35]}</code>")
        if len(alive) > 15:
            lines.append(f"  … +{len(alive)-15} more")
    if dead:
        lines.append(f"💀 <b>Dead</b>  [{len(dead)}]")
        for site, _, speed, *__ in dead[:8]:
            lines.append(f"  💀 <code>{site[:35]}</code>")
        if len(dead) > 8:
            lines.append(f"  … +{len(dead)-8} more")

    await prog.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=make_keyboard([[btn("Back", "admin_pp_gw", style="danger")]])
    )

@router.callback_query(F.data.startswith("admin_pp_view:"))
async def admin_pp_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    page     = int(callback.data.split(":")[1])
    per_page = 10
    total    = await count_pp_gateways()
    pages    = max(1, (total + per_page - 1) // per_page)
    page     = max(1, min(page, pages))
    gws      = await get_pp_gateways(per_page)
    # simple slice
    offset   = (page - 1) * per_page
    gws      = (await get_pp_gateways(total))[offset:offset+per_page]

    text = (
        f"[{get_html('lightning1')}] <b>PayPal Gateways</b>  ·  {page}/{pages}  ·  Total: {total}\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    for g in gws:
        ic    = "✅" if g["status"] == "working" else "💀" if g["status"] == "dead" else "⏳"
        text += f"{ic} <b>PP_V{g['id']}</b>  <code>{g['site'][:40]}</code>\n"

    nav = []
    if page > 1:  nav.append(btn("◀", f"admin_pp_view:{page-1}", style="primary"))
    nav.append(btn(f"{page}/{pages}", "ignore", style="default"))
    if page < pages: nav.append(btn("▶", f"admin_pp_view:{page+1}", style="primary"))

    rows = [nav, [
        btn("Delete by ID", "admin_pp_del_id", style="danger"),
        btn("Back",         "admin_pp_gw",     style="danger"),
    ]]
    await _safe_edit(callback.message, text, make_keyboard(rows))

@router.callback_query(F.data == "admin_pp_check_all")
async def admin_pp_check_all(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    total = await count_pp_gateways()
    if not total:
        await _safe_edit(callback.message, "No PayPal gateways.",
            make_keyboard([[btn("Back","admin_pp_gw",style="danger")]])); return

    all_gws  = await get_pp_gateways(total)
    uid      = callback.from_user.id
    stop_ev  = asyncio.Event()
    _stop_events[uid] = stop_ev
    start_ts = time.time()
    done_c   = [0]
    alive_c  = [0]
    dead_c   = [0]
    sem      = asyncio.Semaphore(5)
    _lock    = asyncio.Lock()
    results  = {}

    await _safe_edit(callback.message,
        f"⚡ <b>Checking {total} PayPal gateways...</b>", None)

    async def _chk_pp(gw):
        if stop_ev.is_set(): return
        async with sem:
            if stop_ev.is_set(): return
            import time as _t
            from paypal import PayPal  # ← صح (كان pp خطأ)
            t0        = _t.time()
            resp_text = "—"
            alive     = False
            try:
                pp   = PayPal(gw["site"], "1.00")
                loop = asyncio.get_event_loop()
                au   = await loop.run_in_executor(None, pp.Key)
                speed     = int((_t.time() - t0) * 1000)
                alive     = True
                resp_text = f"token={str(au[0])[:20]}..." if au else "OK"
            except AttributeError as e:
                speed     = int((_t.time() - t0) * 1000)
                resp_text = f"Form not found: {str(e)[:40]}"
            except Exception as e:
                speed     = int((_t.time() - t0) * 1000)
                resp_text = str(e)[:60]

            icon = "✅" if alive else "❌"
            print(
                f"\n{'━'*55}\n"
                f"  {icon} {'ALIVE' if alive else 'DEAD':<8}  {speed:>5}ms  PP_V{gw['id']}\n"
                f"  🌐 {gw['site']}\n"
                f"  📋 {resp_text}\n"
                f"{'━'*55}"
            )

            async with _lock:
                results[gw["id"]] = (alive, speed)
                done_c[0] += 1
                if alive: alive_c[0] += 1
                else:     dead_c[0]  += 1
                snap       = done_c[0]
                snap_alive = alive_c[0]
                snap_dead  = dead_c[0]

            if snap % 3 == 0 or snap == total:
                try:
                    bar_f = int((snap / total) * 10)
                    bar   = "█" * bar_f + "░" * (10 - bar_f)
                    await callback.message.edit_text(
                        f"⚡ <b>Checking PayPal</b>\n━━━━━━━━━━━━━━━━\n"
                        f"[{bar}]  {snap}/{total}\n"
                        f"✅ Alive: <b>{snap_alive}</b>  💀 Dead: <b>{snap_dead}</b>",
                        parse_mode="HTML",
                        reply_markup=make_keyboard([[btn("⏹ Stop", "admin_gw_stop", style="danger")]])
                    )
                except Exception: pass

    await asyncio.gather(*[_chk_pp(g) for g in all_gws])
    _stop_events.pop(uid, None)

    dead_deleted = 0
    for gw in all_gws:
        alive, speed = results.get(gw["id"], (False, 0))
        if alive:
            await update_pp_gateway_status(gw["id"], "working", speed)
        else:
            await delete_pp_gateway(gw["id"])
            dead_deleted += 1

    if dead_deleted:
        await reorder_pp_gateways()

    elapsed_total = time.time() - start_ts
    stopped       = stop_ev.is_set()

    await _safe_edit(callback.message,
        f"{'⏹' if stopped else '✅'} <b>{'Stopped' if stopped else 'Done'}</b>\n"
        f"★━━━━━━━━━━━━━━━━★\n"
        f"📊 Checked  : <b>{done_c[0]}</b> / {total}\n"
        f"✅ Alive    : <b>{alive_c[0]}</b>\n"
        f"💀 Deleted  : <b>{dead_deleted}</b>\n"
        f"⏱ Time     : <b>{elapsed_total:.1f}s</b>\n"
        f"★━━━━━━━━━━━━━━━━★",
        make_keyboard([[btn("Back", "admin_pp_gw", style="danger")]])
    )

@router.callback_query(F.data == "admin_pp_del_dead")
async def admin_pp_del_dead(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    deleted = await delete_dead_pp_gateways()
    if deleted:
        await reorder_pp_gateways()
    await _safe_edit(callback.message,
        f"💀 <b>Deleted {deleted} dead PayPal gateways.</b>",
        make_keyboard([[btn("Back", "admin_pp_gw", style="danger")]])
    )

class DeletePPGWState(StatesGroup):
    waiting_for_id = State()

@router.callback_query(F.data == "admin_pp_del_id")
async def admin_pp_del_id(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(DeletePPGWState.waiting_for_id)
    await _safe_edit(callback.message,
        "Send the PayPal gateway ID to delete:",
        make_keyboard([[btn("Cancel", "admin_cancel", style="danger")]])
    )

@router.message(DeletePPGWState.waiting_for_id)
async def handle_del_pp_gw(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        gid = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid ID."); return
    gw = await get_pp_gateway(gid)
    if not gw:
        await message.answer("PayPal gateway not found."); await state.clear(); return
    await delete_pp_gateway(gid)
    await reorder_pp_gateways()
    await state.clear()
    await message.answer(
        f"💀 <b>Deleted PP_V{gid}</b>\n<code>{gw['site']}</code>\n✅ IDs renumbered.",
        parse_mode="HTML"
    )
