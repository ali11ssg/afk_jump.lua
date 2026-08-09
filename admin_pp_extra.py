"""
admin_pp_extra.py
═════════════════════════════════════════════════════════════════
يُسجَّل هذا الـ router قبل admin.router في main.py:
    dp.include_router(admin_pp_extra.router)
    dp.include_router(admin.router)

الميزات المضافة:
  ① حذف بوابة PayPal بالـ ID (إصلاح + زر حذف مباشر في القائمة)
  ② زر عرض + فحص + حذف لكل بوابة على حدة
  ③ Add And Test — يجرب URL/ملف، يفحص البوابة، يشغل البطاقة 10 مرات،
     يجمع الردود مع عدد التكرار، يرسل ملف إذا النتائج > 5
═════════════════════════════════════════════════════════════════
"""
import asyncio
import re
import time
from collections import Counter

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
)
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_IDS, TEST_CARD
from helpers import get_html, btn, make_keyboard, is_admin
from data import (
    get_pp_gateways, get_pp_gateway, count_pp_gateways,
    add_pp_gateway, delete_pp_gateway,
    update_pp_gateway_status, reorder_pp_gateways,
)
from paypal import PayPal, pp_check

router = Router()

_LIGHT = get_html("lightning1")
_SEP1  = "★━━━━━━━━━━━━━━━━━━━━━━━━━━★"
_SEP2  = "━━━━━━━━━━━━━━━━━━━━"

# الردود التي تدل على أن البوابة شغّالة (باي بال يستجيب لعمليات البطاقة)
_LIVE_KEYWORDS = {
    "DECLINED", "APPROVED", "CHARGE",
    "INSUFFICIENT_FUNDS", "CVV2_FAILURE", "DO_NOT_HONOR",
    "GENERIC_DECLINE", "CARD_DECLINED", "SECURITY_VIOLATION",
    "TRANSACTION_NOT_PERMITTED", "INVALID_OR_RESTRICTED_CARD",
    "EXPIRED_CARD", "LOST_OR_STOLEN", "CVV2_MISMATCH",
    "ACCOUNT_CLOSED", "REATTEMPT_NOT_PERMITTED",
}


# ─── helpers ─────────────────────────────────────────────────────────────────

def _is_live(resp: str) -> bool:
    r = resp.upper()
    return any(kw in r for kw in _LIVE_KEYWORDS)


async def _safe_edit(msg, text: str, markup=None):
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            pass
    except Exception:
        pass


def _back_pp_gw():
    return make_keyboard([[btn("◀ Back", "admin_pp_gw", style="default")]])


# ─── ① admin_pp_gw — panel رئيسي مع زر Add And Test ──────────────────────────
# يوفر override للـ callback الأصلي في admin.py

@router.callback_query(F.data == "admin_pp_gw")
async def admin_pp_gw_override(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    total = await count_pp_gateways()
    text = (
        f"[{_LIGHT}] <b>PayPal Panel</b>\n"
        f"{_SEP2}\n"
        f"📊 Total gateways: <b>{total}</b>"
    )
    rows = [
        [btn("➕ Add",           "admin_pp_add",         style="success"),
         btn("👁 View",          "admin_pp_view:1",      style="primary")],
        [btn("⚡ Check All",     "admin_pp_check_all",   style="primary"),
         btn("💀 Del Dead",      "admin_pp_del_dead",    style="danger")],
        [btn("🗑 Delete by ID",  "admin_pp_del_id",      style="danger"),
         btn("🔢 Renumber",      "admin_pp_renumber",    style="default")],
        [btn("🧪 Add And Test",  "admin_pp_add_test",    style="success")],   # ← جديد
        [btn("◀ Back",           "admin_back",            style="default")],
    ]
    await _safe_edit(callback.message, text, make_keyboard(rows))


# ─── ② View — مع زر Inspect لكل بوابة ───────────────────────────────────────

@router.callback_query(F.data.startswith("admin_pp_view:"))
async def admin_pp_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer()

    page     = max(1, int(callback.data.split(":")[1]))
    per_page = 8
    total    = await count_pp_gateways()
    pages    = max(1, (total + per_page - 1) // per_page)
    page     = min(page, pages)
    offset   = (page - 1) * per_page
    all_gws  = await get_pp_gateways(total)
    gws      = all_gws[offset:offset + per_page]

    text = (
        f"[{_LIGHT}] <b>PayPal Gateways</b>  ·  {page}/{pages}  ·  Total: {total}\n"
        f"{_SEP2}\n"
    )
    rows = []
    for g in gws:
        ic    = "✅" if g["status"] == "working" else "💀" if g["status"] == "dead" else "⏳"
        spd   = f"  {g['speed']}ms" if g.get("speed") else ""
        text += f"{ic} <b>PP_V{g['id']}</b>{spd}  <code>{g['site'][:38]}</code>\n"
        rows.append([
            btn(f"PP_V{g['id']} — Inspect", f"admin_pp_inspect:{g['id']}", style="primary"),
        ])

    nav = []
    if page > 1:
        nav.append(btn("◀", f"admin_pp_view:{page-1}", style="primary"))
    nav.append(btn(f"{page}/{pages}", "ignore_nav", style="default"))
    if page < pages:
        nav.append(btn("▶", f"admin_pp_view:{page+1}", style="primary"))
    if nav:
        rows.append(nav)
    rows.append([
        btn("🗑 Delete by ID", "admin_pp_del_id", style="danger"),
        btn("◀ Back",          "admin_pp_gw",     style="default"),
    ])
    await _safe_edit(callback.message, text, make_keyboard(rows))


# ─── Inspect — عرض بوابة + أزرار فحص وحذف ───────────────────────────────────

@router.callback_query(F.data.startswith("admin_pp_inspect:"))
async def admin_pp_inspect(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer()

    gid = int(callback.data.split(":")[1])
    gw  = await get_pp_gateway(gid)
    if not gw:
        await _safe_edit(callback.message, "❌ Gateway not found.", _back_pp_gw()); return

    ic = "✅" if gw["status"] == "working" else "💀" if gw["status"] == "dead" else "⏳"
    text = (
        f"[{_LIGHT}] <b>PP_V{gid}</b>  {ic}\n"
        f"{_SEP2}\n"
        f"🌐 <b>Site:</b>\n<code>{gw['site']}</code>\n\n"
        f"📊 Status : <b>{gw['status']}</b>\n"
        f"⚡ Speed  : <b>{gw.get('speed', 0)}ms</b>\n"
        f"{_SEP2}"
    )
    rows = [
        [btn("🧪 Test (10×)", f"admin_pp_test_gw:{gid}", style="primary")],
        [btn("🗑 Delete",     f"admin_pp_del_confirm:{gid}", style="danger"),
         btn("◀ Back",       "admin_pp_view:1",             style="default")],
    ]
    await _safe_edit(callback.message, text, make_keyboard(rows))


# ─── Test بوابة واحدة 10 مرات ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_pp_test_gw:"))
async def admin_pp_test_gw(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer("Testing... ⏳")

    gid = int(callback.data.split(":")[1])
    gw  = await get_pp_gateway(gid)
    if not gw:
        await _safe_edit(callback.message, "❌ Gateway not found.", _back_pp_gw()); return

    site = gw["site"]
    await _safe_edit(callback.message,
        f"🧪 <b>Testing PP_V{gid}...</b>\n"
        f"<code>{site[:50]}</code>\n"
        f"⏳ Running 10 attempts with test card...")

    loop      = asyncio.get_event_loop()
    responses = []

    for attempt in range(1, 11):
        try:
            resp = await loop.run_in_executor(
                None, pp_check, TEST_CARD, "1.00", site
            )
        except Exception as e:
            resp = f"ERROR: {str(e)[:35]}"
        responses.append(resp)

        # تحديث مؤقت كل 3 محاولات
        if attempt % 3 == 0:
            partial = Counter(responses)
            partial_txt = "\n".join(
                f"  {'🔥' if _is_live(r) else '▪'} <code>{r}</code> ×{c}"
                for r, c in partial.most_common()
            )
            try:
                await callback.message.edit_text(
                    f"🧪 <b>Testing PP_V{gid}  [{attempt}/10]</b>\n"
                    f"<code>{site[:45]}</code>\n"
                    f"{_SEP2}\n{partial_txt}",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        await asyncio.sleep(0.4)

    # ── تحديث الحالة في DB ──
    counts   = Counter(responses)
    is_alive = any(_is_live(r) for r in responses)
    new_status = "working" if is_alive else "dead"
    await update_pp_gateway_status(gid, new_status)

    # ── نص النتيجة ──
    text = (
        f"[{_LIGHT}] <b>Test Results — PP_V{gid}</b>\n"
        f"{'✅ ALIVE' if is_alive else '💀 DEAD'}  —  Status updated\n"
        f"{_SEP1}\n"
        f"🌐 <code>{site[:50]}</code>\n"
        f"{_SEP2}\n"
        f"<b>Responses (10 attempts):</b>\n"
    )
    for resp, cnt in counts.most_common():
        flag  = "🔥" if _is_live(resp) else "❌"
        bar   = "█" * min(cnt, 10)
        text += f"  {flag} <code>{resp:<38}</code> ×{cnt}  {bar}\n"
    text += (
        f"{_SEP2}\n"
        f"📊 Status → <b>{new_status}</b>"
    )
    rows = [
        [btn("🗑 Delete", f"admin_pp_del_confirm:{gid}", style="danger"),
         btn("◀ Back",   f"admin_pp_inspect:{gid}",     style="default")],
    ]
    await _safe_edit(callback.message, text, make_keyboard(rows))


# ─── حذف بتأكيد ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_pp_del_confirm:"))
async def admin_pp_del_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    gid = int(callback.data.split(":")[1])
    gw  = await get_pp_gateway(gid)
    if not gw:
        await _safe_edit(callback.message, "❌ Not found.", _back_pp_gw()); return

    text = (
        f"⚠️ <b>Delete PP_V{gid}?</b>\n\n"
        f"<code>{gw['site']}</code>\n\n"
        f"This cannot be undone."
    )
    rows = [
        [btn("✅ Yes, Delete", f"admin_pp_del_yes:{gid}", style="danger"),
         btn("❌ Cancel",      f"admin_pp_inspect:{gid}",  style="default")],
    ]
    await _safe_edit(callback.message, text, make_keyboard(rows))


@router.callback_query(F.data.startswith("admin_pp_del_yes:"))
async def admin_pp_del_yes(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer("Deleting...")
    gid  = int(callback.data.split(":")[1])
    gw   = await get_pp_gateway(gid)
    site = gw["site"] if gw else "?"
    await delete_pp_gateway(gid)
    await reorder_pp_gateways()
    await _safe_edit(
        callback.message,
        f"🗑 <b>Deleted PP_V{gid}</b>\n"
        f"<code>{site[:55]}</code>\n\n"
        f"✅ IDs renumbered.",
        make_keyboard([[btn("◀ Back", "admin_pp_view:1", style="default")]])
    )


# ─── ③ Add And Test ────────────────────────────────────────────────────────────

class AddTestState(StatesGroup):
    waiting = State()


@router.callback_query(F.data == "admin_pp_add_test")
async def admin_pp_add_test_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True); return
    await callback.answer()
    await state.set_state(AddTestState.waiting)
    await _safe_edit(callback.message,
        f"[{_LIGHT}] <b>Add And Test — PayPal</b>\n"
        f"{_SEP2}\n"
        f"أرسل <b>ملف .txt</b> أو <b>روابط</b> (سطر واحد لكل رابط).\n\n"
        f"لكل بوابة شغّالة:\n"
        f"• تشغيل بطاقة الاختبار <b>10 مرات</b>\n"
        f"• جمع الردود مع عدد التكرار\n"
        f"• <b>Declined / Approved / Charge</b> = بوابة حية\n"
        f"• البوابات الحية تُضاف لـ DB تلقائياً\n"
        f"• إذا > 5 بوابات → النتائج تُرسل كـ <b>.txt</b>\n"
        f"{_SEP2}",
        make_keyboard([[btn("❌ Cancel", "admin_pp_gw", style="danger")]])
    )


@router.message(AddTestState.waiting)
async def admin_pp_add_test_input(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()

    # ── جمع الروابط ──────────────────────────────────────────────────────────
    raw_lines: list[str] = []
    if message.document:
        try:
            file  = await message.bot.get_file(message.document.file_id)
            bdata = await message.bot.download_file(file.file_path)
            raw_lines = bdata.read().decode("utf-8", errors="ignore").splitlines()
        except Exception as e:
            await message.answer(f"❌ Could not read file: {e}", parse_mode="HTML"); return
    elif message.text:
        raw_lines = message.text.splitlines()
    else:
        await message.answer("❌ No input.", parse_mode="HTML"); return

    def _norm_url(s: str) -> str | None:
        s = s.strip()
        if not s: return None
        if not re.match(r'^[a-zA-Z0-9._:/\-?=%&@#]+$', s): return None
        if not s.startswith("http"):
            s = "https://" + s
        return s if re.match(r'^https?://', s) else None

    urls = list(dict.fromkeys(filter(None, (_norm_url(l) for l in raw_lines))))

    if not urls:
        await message.answer("❌ No valid URLs found.", parse_mode="HTML"); return

    uid  = message.from_user.id
    loop = asyncio.get_event_loop()

    prog = await message.answer(
        f"⚡ <b>Add And Test</b>\n{_SEP2}\n"
        f"🔗 URLs: <b>{len(urls)}</b>\n⏳ Starting...",
        parse_mode="HTML"
    )

    # ── struct: (url, is_alive, responses_counter, db_id) ────────────────────
    results: list[tuple] = []
    start_ts = time.time()

    for idx, url in enumerate(urls, 1):

        # Step 1: هل البوابة حية؟ (يجرب Key())
        try:
            pp       = PayPal(url, "1.00")
            _        = await loop.run_in_executor(None, pp.Key)
            gw_alive = True
        except Exception:
            gw_alive = False

        if not gw_alive:
            results.append((url, False, Counter(), None))
            pct = int(idx / len(urls) * 100)
            try:
                await prog.edit_text(
                    f"⚡ <b>Add And Test</b>  [{idx}/{len(urls)}  {pct}%]\n"
                    f"{_SEP2}\n"
                    f"💀 Dead: <code>{url[:48]}</code>",
                    parse_mode="HTML"
                )
            except Exception: pass
            continue

        # Step 2: تشغيل البطاقة 10 مرات
        responses: list[str] = []
        for attempt in range(10):
            try:
                resp = await loop.run_in_executor(
                    None, pp_check, TEST_CARD, "1.00", url
                )
            except Exception as e:
                resp = f"ERROR:{str(e)[:25]}"
            responses.append(resp)
            await asyncio.sleep(0.3)

        counts   = Counter(responses)
        is_live  = any(_is_live(r) for r in responses)

        # Step 3: أضف لـ DB إذا حية
        db_id = None
        if is_live:
            try:
                db_id = await add_pp_gateway(url, uid)
                await update_pp_gateway_status(db_id, "working")
            except Exception:
                pass

        results.append((url, is_live, counts, db_id))

        # progress update
        alive_now = sum(1 for _, alive, _, _ in results if alive)
        top_resp  = counts.most_common(1)[0][0] if counts else "—"
        ic        = "✅" if is_live else "💀"
        pct       = int(idx / len(urls) * 100)
        try:
            await prog.edit_text(
                f"⚡ <b>Add And Test</b>  [{idx}/{len(urls)}  {pct}%]\n"
                f"{_SEP2}\n"
                f"✅ Alive so far: <b>{alive_now}</b>\n"
                f"━━━\n"
                f"{ic} <code>{url[:45]}</code>\n"
                f"📋 Top: <code>{top_resp}</code>",
                parse_mode="HTML"
            )
        except Exception: pass

    # ── ملخص نهائي ────────────────────────────────────────────────────────────
    elapsed   = time.time() - start_ts
    alive_gws = [(url, counts, db_id) for url, alive, counts, db_id in results if alive]
    dead_gws  = [url for url, alive, _, _ in results if not alive]

    summary = (
        f"[{_LIGHT}] <b>Add And Test — Done</b>\n"
        f"{_SEP1}\n"
        f"🔗 Tested   : <b>{len(urls)}</b>\n"
        f"✅ Alive    : <b>{len(alive_gws)}</b>  (added to DB)\n"
        f"💀 Dead     : <b>{len(dead_gws)}</b>\n"
        f"⏱ Time     : <b>{elapsed:.1f}s</b>\n"
        f"{_SEP1}\n"
    )

    if len(alive_gws) == 0:
        await _safe_edit(prog, summary + "❌ No working gateways found.", _back_pp_gw())
        return

    if len(alive_gws) <= 5:
        # نعرض النتيجة inline
        for url, counts, db_id in alive_gws:
            id_str   = f"PP_V{db_id}" if db_id else "Added"
            resp_txt = ""
            for resp, cnt in counts.most_common():
                flag      = "🔥" if _is_live(resp) else "▪"
                resp_txt += f"  {flag} <code>{resp}</code> ×{cnt}\n"
            summary += (
                f"✅ <b>{id_str}</b>\n"
                f"<code>{url[:45]}</code>\n"
                f"{resp_txt}"
            )
        await _safe_edit(prog, summary, _back_pp_gw())

    else:
        # > 5 بوابات → نرسل ملف مرتب
        file_lines = [
            "=" * 65,
            "  ADD AND TEST — PayPal Gateways",
            f"  Tested: {len(urls)}   Alive: {len(alive_gws)}   Dead: {len(dead_gws)}",
            f"  Duration: {elapsed:.1f}s",
            "=" * 65,
            "",
            f"WORKING GATEWAYS ({len(alive_gws)})",
            "─" * 65,
        ]
        for i, (url, counts, db_id) in enumerate(alive_gws, 1):
            id_str = f"PP_V{db_id}" if db_id else f"GW_{i}"
            file_lines += [
                f"",
                f"[{i:>3}]  {id_str}  ✅",
                f"  URL : {url}",
                f"  Responses (10 attempts):",
            ]
            for resp, cnt in counts.most_common():
                live_tag   = "  ← LIVE ✓" if _is_live(resp) else ""
                bar        = "█" * cnt
                file_lines.append(f"    {cnt:>2}×  {resp:<42}{live_tag}  {bar}")

        if dead_gws:
            file_lines += [
                "",
                "─" * 65,
                f"DEAD GATEWAYS ({len(dead_gws)})",
                "─" * 65,
            ]
            for i, url in enumerate(dead_gws, 1):
                file_lines.append(f"  [{i:>3}]  ✗  {url}")

        file_lines += ["", "=" * 65]

        fbytes = "\n".join(file_lines).encode("utf-8")
        fobj   = BufferedInputFile(
            fbytes, filename=f"pp_add_test_{uid}.txt"
        )
        cap = (
            f"[{_LIGHT}] <b>Add And Test — Results</b>\n"
            f"{_SEP2}\n"
            f"✅ Alive : <b>{len(alive_gws)}</b>\n"
            f"💀 Dead  : <b>{len(dead_gws)}</b>\n"
            f"⏱ Time  : <b>{elapsed:.1f}s</b>"
        )
        await _safe_edit(
            prog,
            summary + f"📄 <b>Results sent as file below.</b>",
            _back_pp_gw()
        )
        await message.answer_document(fobj, caption=cap, parse_mode="HTML")


# ─── ignore nav ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "ignore_nav")
async def ignore_nav(callback: CallbackQuery):
    await callback.answer()
