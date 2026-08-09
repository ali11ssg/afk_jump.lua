import asyncio
import re
import time
import logging
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import MAX_USER_PROXIES, ADMIN_IDS, PROXY_CHECK_WORKERS
from helpers import get_html, btn, make_keyboard, is_admin
from shopify import test_proxy, is_valid_proxy
from data import (
    count_user_proxies,
    user_has_proxy,
    global_has_proxy,
    add_user_proxy,
    add_global_proxy,
    get_user_proxies_with_details,
    get_user_proxies,
    delete_user_proxy,
    delete_global_proxy,
    update_user_proxy_speed,
    update_global_proxy_speed,
    get_all_global_proxies,
    count_global_proxies_added_since,
    count_global_proxies,
    count_global_proxies_alive,
    is_user_banned,
)

router = Router()
log = logging.getLogger(__name__)


async def get_pool_proxies_random(n: int = 50) -> list[str]:
    proxies = await get_all_global_proxies()
    if not proxies:
        return []
    import random as _rnd
    _rnd.shuffle(proxies)
    return proxies[:n]


class ProxyPages(StatesGroup):
    viewing = State()


def parse_proxy_line(line: str) -> Optional[str]:
    line = line.strip()
    if not line:
        return None
    if re.match(r'^(http|https|socks5)://', line, re.I):
        return line
    parts = line.split(':')
    if len(parts) == 4:
        host, port, user, pwd = parts
        if re.match(r'^[a-zA-Z0-9._-]+$', host) and port.isdigit() and user and pwd:
            return f"http://{user}:{pwd}@{host}:{port}"
    return None


def format_proxy_display(proxy: str, speed: int = 0, country: str = "?") -> str:
    if proxy.startswith(('http://', 'https://', 'socks5://')):
        parts = proxy.split('@')
        if len(parts) == 2:
            host_part = parts[1]
            user_pass = parts[0].split('://')[1]
            user = user_pass.split(':')[0]
            return f"{host_part} | {user} | {speed}ms | {country}"
        return f"{proxy} | {speed}ms | {country}"
    return f"{proxy} | {speed}ms | {country}"


def make_proxy_keyboard(page: int, total_pages: int, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 1:
        nav.append(btn("Previous", f"pxy_page:{user_id}:{page-1}", style="primary"))
    nav.append(btn(f"{page}/{total_pages}", "ignore", style="default"))
    if page < total_pages:
        nav.append(btn("Next", f"pxy_page:{user_id}:{page+1}", style="primary"))
    rows.append(nav)
    rows.append([btn("Refresh", f"pxy_refresh:{user_id}:{page}", style="info")])
    return make_keyboard(rows)


@router.message(Command("proxy"))
async def cmd_add_proxy(message: Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer(f"{get_html('denied')} <b>You are banned.</b>", parse_mode="HTML")
        return

    if message.reply_to_message:
        if message.reply_to_message.document:
            file = await message.bot.get_file(message.reply_to_message.document.file_id)
            content = await message.bot.download_file(file.file_path)
            text = content.read().decode('utf-8', errors='ignore')
        else:
            text = message.reply_to_message.text or message.reply_to_message.caption
            if not text:
                await message.answer(f"{get_html('error')} <b>Reply must contain text or a file.</b>", parse_mode="HTML")
                return
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(f"{get_html('error')} <b>Send proxies or reply to a message/file.</b>", parse_mode="HTML")
            return
        text = parts[1]

    lines       = [l for l in text.splitlines() if l.strip()]
    total_lines = len(lines)
    current_count = await count_user_proxies(user_id)
    remaining_slots = MAX_USER_PROXIES - current_count

    if remaining_slots <= 0:
        await message.answer(
            f"{get_html('warning')} <b>Proxy limit reached ({MAX_USER_PROXIES}).</b>",
            parse_mode="HTML"
        )
        return

    live_msg = await message.answer(
        f"{get_html('time')} <b>Checking proxies...</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('approved')} Added: <b>0</b>  •  {get_html('error')} Dead: <b>0</b>  •  {get_html('warning')} Dup: <b>0</b>\n"
        f"{get_html('list')} Progress: <b>0/{total_lines}</b>",
        parse_mode="HTML"
    )

    added       = 0
    skipped_dup = 0
    invalid     = 0
    _last_edit  = [0.0]
    _checked    = [0]
    _lock       = asyncio.Lock()

    async def _update_live():
        import time as _t
        if _t.time() - _last_edit[0] < 1.5:
            return
        _last_edit[0] = _t.time()
        try:
            await live_msg.edit_text(
                f"{get_html('time')} <b>Checking proxies...</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{get_html('approved')} Added: <b>{added}</b>  •  {get_html('error')} Dead: <b>{invalid}</b>  •  {get_html('warning')} Duplicate: <b>{skipped_dup}</b>\n"
                f"{get_html('list')} Progress: <b>{_checked[0]}/{total_lines}</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    sem = asyncio.Semaphore(PROXY_CHECK_WORKERS)

    async def _check_one(line):
        nonlocal added, skipped_dup, invalid
        async with sem:
            async with _lock:
                if added >= remaining_slots:
                    _checked[0] += 1
                    return
            proxy = parse_proxy_line(line)
            if not proxy or not is_valid_proxy(proxy):
                async with _lock:
                    invalid += 1
                    _checked[0] += 1
                await _update_live()
                return
            # إذا عند المستخدم هذا البروكسي مسبقاً → تكرار
            if await user_has_proxy(user_id, proxy):
                async with _lock:
                    skipped_dup += 1
                    _checked[0] += 1
                await _update_live()
                return
            # فحص حياة البروكسي
            ok, speed, country = await test_proxy(proxy)
            if not ok:
                async with _lock:
                    invalid += 1
                    _checked[0] += 1
                await _update_live()
                return
            # البروكسي شغال → أضفه للمستخدم دائماً
            async with _lock:
                if added >= remaining_slots:
                    _checked[0] += 1
                    return
                added += 1
                _checked[0] += 1
            await add_user_proxy(user_id, proxy, speed, country)
            # أضفه للخزان فقط إذا مو مكرر فيه
            if not await global_has_proxy(proxy):
                await add_global_proxy(proxy, speed, country)
            await _update_live()

    await asyncio.gather(*[_check_one(line) for line in lines])

    final_count = current_count + added
    try:
        await live_msg.delete()
    except Exception:
        pass

    result = (
        f"{get_html('proxy')} <b>Proxy Results</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('approved')} Added: <b>{added}</b>\n"
        f"{get_html('warning')} Duplicate: <b>{skipped_dup}</b>\n"
        f"{get_html('error')} Dead/Invalid: <b>{invalid}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('list')} Total: <b>{final_count}/{MAX_USER_PROXIES}</b>"
    )
    await message.answer(result, parse_mode="HTML")


@router.message(Command("vpxy"))
async def cmd_view_proxies(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer(f"{get_html('denied')} <b>You are banned.</b>", parse_mode="HTML")
        return

    proxies = await get_user_proxies_with_details(user_id)
    if not proxies:
        await message.answer(f"{get_html('error')} <b>You have no proxies.</b>", parse_mode="HTML")
        return
    total = len(proxies)
    page_size = 10
    total_pages = (total + page_size - 1) // page_size
    page = 1
    await state.update_data(proxies=proxies, total_pages=total_pages)
    await state.set_state(ProxyPages.viewing)
    await show_proxy_page(message, user_id, proxies, page, total_pages)


async def show_proxy_page(target, user_id: int, proxies: list, page: int, total_pages: int):
    start = (page - 1) * 10
    end   = start + 10
    chunk = proxies[start:end]
    text  = f"{get_html('list')} <b>Your Proxies  [{page}/{total_pages}]</b>\n"
    text += "━━━━━━━━━━━━━━━━━━\n"
    for idx, p in enumerate(chunk, start=start + 1):
        display = format_proxy_display(p['proxy'], p.get('speed', 0), p.get('country', '?'))
        text += f"<b>{idx}.</b> {display}\n"
    text += f"━━━━━━━━━━━━━━━━━━\n"
    text += f"{get_html('list')} Total: <b>{len(proxies)}</b>"
    keyboard = make_proxy_keyboard(page, total_pages, user_id)
    if isinstance(target, Message):
        await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        try:
            await target.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            pass


@router.callback_query(ProxyPages.viewing, F.data.startswith("pxy_page:"))
async def proxy_page_callback(callback: CallbackQuery, state: FSMContext):
    data    = callback.data.split(':')
    user_id = int(data[1])
    page    = int(data[2])
    if callback.from_user.id != user_id:
        await callback.answer(f"{get_html('denied')} Not your session.", show_alert=True)
        return
    if await is_user_banned(user_id):
        await callback.answer(f"{get_html('denied')} You are banned.", show_alert=True)
        return
    state_data  = await state.get_data()
    proxies     = state_data.get('proxies')
    total_pages = state_data.get('total_pages')
    if not proxies:
        await callback.answer(f"{get_html('warning')} Session expired — use /vpxy again.")
        return
    await show_proxy_page(callback.message, user_id, proxies, page, total_pages)
    await callback.answer()


@router.callback_query(ProxyPages.viewing, F.data.startswith("pxy_refresh:"))
async def proxy_refresh_callback(callback: CallbackQuery, state: FSMContext):
    data    = callback.data.split(':')
    user_id = int(data[1])
    page    = int(data[2])
    if callback.from_user.id != user_id:
        await callback.answer(f"{get_html('denied')} Not your session.", show_alert=True)
        return
    if await is_user_banned(user_id):
        await callback.answer(f"{get_html('denied')} You are banned.", show_alert=True)
        return
    proxies = await get_user_proxies_with_details(user_id)
    if not proxies:
        await callback.message.edit_text(f"{get_html('error')} <b>You have no proxies.</b>", parse_mode="HTML")
        await state.clear()
        return
    total       = len(proxies)
    page_size   = 10
    total_pages = (total + page_size - 1) // page_size
    if page > total_pages:
        page = total_pages
    await state.update_data(proxies=proxies, total_pages=total_pages)
    await show_proxy_page(callback.message, user_id, proxies, page, total_pages)
    await callback.answer(f"{get_html('approved')} Refreshed.")


@router.message(Command("chkpxy"))
async def cmd_check_proxies(message: Message):
    """فحص بروكسيات المستخدم بشكل متوازٍ (سريع)"""
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer(f"{get_html('denied')} <b>You are banned.</b>", parse_mode="HTML")
        return

    proxies = await get_user_proxies(user_id)
    if not proxies:
        await message.answer(f"{get_html('error')} <b>You have no proxies to check.</b>", parse_mode="HTML")
        return

    total_p  = len(proxies)
    live_msg = await message.answer(
        f"{get_html('time')} <b>Checking {total_p} proxies...</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('approved')} Alive: <b>0</b>  •  {get_html('error')} Dead: <b>0</b>\n"
        f"{get_html('list')} Progress: <b>0/{total_p}</b>",
        parse_mode="HTML"
    )

    import time as _t
    _last_edit  = [0.0]
    _checked    = [0]
    alive_count = [0]
    dead_count  = [0]
    _lock       = asyncio.Lock()

    async def _upd2():
        if _t.time() - _last_edit[0] < 1.5:
            return
        _last_edit[0] = _t.time()
        try:
            await live_msg.edit_text(
                f"{get_html('time')} <b>Checking proxies...</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{get_html('approved')} Alive: <b>{alive_count[0]}</b>  •  {get_html('error')} Dead: <b>{dead_count[0]}</b>\n"
                f"{get_html('list')} Progress: <b>{_checked[0]}/{total_p}</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    sem = asyncio.Semaphore(PROXY_CHECK_WORKERS)

    async def _check_one(p):
        async with sem:
            ok, speed, country = await test_proxy(p)
            async with _lock:
                _checked[0] += 1
                if not ok:
                    dead_count[0] += 1
                else:
                    alive_count[0] += 1
            if not ok:
                await delete_user_proxy(user_id, p)
                # الخزان لا يُحذف منه — يبقى للأدمن يفحصه من لوحة الإدارة
            else:
                await update_user_proxy_speed(user_id, p, speed, country)
                await update_global_proxy_speed(p, speed, country)
            await _upd2()

    await asyncio.gather(*[_check_one(p) for p in proxies])

    try:
        await live_msg.delete()
    except Exception:
        pass

    result = (
        f"{get_html('proxy')} <b>Check Results</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('approved')} Alive: <b>{alive_count[0]}</b>\n"
        f"{get_html('error')} Dead (removed): <b>{dead_count[0]}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('list')} Remaining: <b>{alive_count[0]}</b>"
    )
    await message.answer(result, parse_mode="HTML")


@router.message(Command("rmpxy"))
async def cmd_remove_proxy(message: Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer(f"{get_html('denied')} <b>You are banned.</b>", parse_mode="HTML")
        return

    if message.reply_to_message and message.reply_to_message.text:
        proxy = parse_proxy_line(message.reply_to_message.text)
        if not proxy:
            await message.answer(f"{get_html('error')} <b>Invalid proxy format.</b>", parse_mode="HTML")
            return
    else:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(f"{get_html('error')} <b>Usage:</b> <code>/rmpxy proxy</code>", parse_mode="HTML")
            return
        proxy = parse_proxy_line(parts[1])
        if not proxy:
            await message.answer(f"{get_html('error')} <b>Invalid proxy format.</b>", parse_mode="HTML")
            return
    if not await user_has_proxy(user_id, proxy):
        await message.answer(f"{get_html('error')} <b>Proxy not found in your list.</b>", parse_mode="HTML")
        return
    await delete_user_proxy(user_id, proxy)
    # الخزان لا يُحذف منه — يبقى للأدمن يفحصه من لوحة الإدارة
    await message.answer(f"{get_html('trash')} <b>Proxy removed.</b>", parse_mode="HTML")


@router.message(Command("rmlpxy"))
async def cmd_remove_all_proxies(message: Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer(f"{get_html('denied')} <b>You are banned.</b>", parse_mode="HTML")
        return

    proxies = await get_user_proxies(user_id)
    if not proxies:
        await message.answer(f"{get_html('error')} <b>You have no proxies.</b>", parse_mode="HTML")
        return

    # حذف متوازٍ من قائمة المستخدم فقط — الخزان يبقى للأدمن
    await asyncio.gather(*[delete_user_proxy(user_id, p) for p in proxies])
    await message.answer(f"{get_html('trash')} <b>Removed all proxies ({len(proxies)}).</b>", parse_mode="HTML")


async def background_global_check():
    while True:
        await asyncio.sleep(3 * 3600)
        proxies = await get_all_global_proxies()
        if not proxies:
            continue
        sem  = asyncio.Semaphore(PROXY_CHECK_WORKERS)
        dead = [0]

        async def check_one(p):
            async with sem:
                ok, _, _ = await test_proxy(p)
                if not ok:
                    await delete_global_proxy(p)
                    dead[0] += 1

        await asyncio.gather(*[check_one(p) for p in proxies])
        if dead[0]:
            log.info(f"Global check: removed {dead[0]} dead proxies")


async def background_admin_report(bot: Bot):
    last_report = time.time()
    while True:
        await asyncio.sleep(9 * 3600)
        now   = time.time()
        added = await count_global_proxies_added_since(last_report)
        total = await count_global_proxies()
        alive = await count_global_proxies_alive()
        dead  = total - alive
        report = (
            f"{get_html('stats')} <b>Proxy Pool Report</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{get_html('plus')} <b>Added (9h): {added}</b>\n"
            f"{get_html('list')} <b>Total: {total}</b>\n"
            f"{get_html('approved')} <b>Alive: {alive}</b>\n"
            f"{get_html('error')} <b>Dead: {dead}</b>\n"
            f"{get_html('time')} <b>Last 9 hours</b>"
        )
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(admin, report, parse_mode="HTML")
            except Exception:
                pass
        last_report = now


def setup_proxy_tasks(bot: Bot):
    asyncio.create_task(background_global_check())
    asyncio.create_task(background_admin_report(bot))
