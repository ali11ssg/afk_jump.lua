import asyncio
import time
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, SuccessfulPayment
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_IDS, FREE_USERS_BLOCKED
from helpers import get_html, btn, make_keyboard, escape, mention_html, is_admin, can_use
from data import (
    register_user, get_user_info, is_user_banned,
    get_subscription, set_subscription,
    count_user_proxies,
    get_user_proxies,
)

router = Router()
log = logging.getLogger(__name__)

VIP_PRICES = {
    1: 10,
    3: 25,
    12: 75,
    24: 100,
    72: 150,
    168: 300,
    720: 1000,
}
BUY_PRICE_PER_HOUR = 10

REQUIRED_CHANNELS = [
    {"name": "Channel Bot", "chat_id": -1003351751257, "url": "https://t.me/+xon72ZxJpeBmODUy"},
    {"name": "Group Bot",   "chat_id": -1004303420890, "url": "https://t.me/+iWHeWE8fLmRiNTRi"},
]

async def check_subscription(bot: Bot, user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception:
            return False
    return True

def subscription_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for ch in REQUIRED_CHANNELS:
        rows.append([InlineKeyboardButton(text=ch["name"], url=ch["url"])])
    rows.append([InlineKeyboardButton(text="✅ Check Subscription", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def _sub_guard(bot: Bot, user_id: int, message: Message = None, callback: CallbackQuery = None) -> bool:
    if is_admin(user_id):
        return True
    if await check_subscription(bot, user_id):
        return True

    channels_text = "\n".join(
        f"{get_html('lightning1')} <b>{ch['name']}</b>" for ch in REQUIRED_CHANNELS
    )
    text = (
        f"{get_html('lock')} <b>Mandatory Subscription</b>\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"You must join the following to use this bot:\n\n"
        f"{channels_text}\n\n"
        f"After joining, press <b>Check Subscription</b>."
    )
    kb = subscription_keyboard()
    if callback:
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback.answer("You must join first!", show_alert=True)
    elif message:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    return False

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    if await check_subscription(callback.bot, user_id):
        await callback.message.edit_text(
            f"{get_html('approved')} <b>Verified!</b>\n"
            f"★━━━━━━━━━━━━━━★\n"
            f"Welcome to P3 SHOPI {get_html('lightning1')}\n"
            f"Press the button to continue.",
            parse_mode="HTML",
            reply_markup=make_keyboard([[btn("Menu", "main_menu", style="primary")]])
        )
    else:
        await callback.answer("You haven't joined all channels yet!", show_alert=True)

async def _sub_status(user_id: int):
    try:
        exp = await get_subscription(user_id)
        if exp and exp > time.time():
            r = exp - time.time()
            d = int(r // 86400)
            h = int((r % 86400) // 3600)
            m = int((r % 3600) // 60)
            parts = []
            if d: parts.append(f"{d}d")
            if h: parts.append(f"{h}h")
            if m: parts.append(f"{m}m")
            return True, " ".join(parts) or "< 1m"
    except Exception:
        pass
    return False, "None"

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user = message.from_user
    await register_user(user_id, user.username or "", user.first_name or "")

    if not await _sub_guard(message.bot, user_id, message=message):
        return

    text = (
        f"Welcome! @{user.username or user.first_name} • Welcome to P3 SHOPI {get_html('lightning1')}\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{get_html('star')} Use the buttons below to explore bot features!\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{get_html('crown')} Bot Status: <b>Online</b> {get_html('fire')}"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=make_keyboard([
        [
            btn("Group Bot",   "main_group",   style="success", url="https://t.me/+iWHeWE8fLmRiNTRi"),
            btn("Channel Bot", "main_channel", style="success", url="https://t.me/+xon72ZxJpeBmODUy"),
        ],
        [btn("Menu", "main_menu", style="primary")],
    ]))

@router.callback_query(F.data == "main_group")
async def main_group(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "main_channel")
async def main_channel(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user    = callback.from_user

    if not await _sub_guard(callback.bot, user_id, callback=callback):
        return

    info    = await get_user_info(user_id) or {}
    uname   = info.get("username") or user.username or "—"
    fname   = escape(info.get("first_name") or user.first_name or "User")
    active, remaining = await _sub_status(user_id)
    sub_icon = get_html("crown") if active else get_html("lock")

    try:
        proxies     = await get_user_proxies(user_id)
        proxy_count = len(proxies)
    except Exception:
        proxy_count = 0

    text = (
        f"Welcome To P3 SHOPI {get_html('lightning1')}\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{get_html('user')} <b>{fname}</b> • <code>{user_id}</code> • @{escape(uname)}\n"
        f"{sub_icon} <b>Subscription:</b> {remaining}\n"
        f"{get_html('proxy')} <b>Proxies:</b> {proxy_count}\n"
        f"• High Speed\n"
        f"• Clean Results\n\n"
        f"Fast • Stable • Powerful\n"
        f"★━━━━━━━━━━━━━━★"
    )
    rows = [
        [
            btn("GATE",    "menu_gate",    style="primary"),
            btn("TOOLS",   "menu_tools",   style="primary"),
        ],
        [
            btn("PROXIES", "menu_proxies", style="danger"),
            btn("BUY",     "menu_vip",     style="success"),
        ],
    ]
    if is_admin(user_id):
        rows.append([btn("Admin Panel", "menu_admin", style="danger")])
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=make_keyboard(rows))
    except TelegramBadRequest as _e:
        if "message is not modified" not in str(_e): log.error(f"edit: {_e}")

@router.callback_query(F.data == "menu_gate")
async def menu_gate(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if not await _sub_guard(callback.bot, user_id, callback=callback):
        return

    try:
        proxies     = await get_user_proxies(user_id)
        proxy_count = len(proxies)
    except Exception:
        proxy_count = 0
    active, remaining = await _sub_status(user_id)
    sub_icon = get_html("crown") if active else get_html("lock")
    text = (
        f"{get_html('gate')} <b>Gateway</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{get_html('proxy')} <b>Your Proxies:</b> {proxy_count}\n"
        f"{sub_icon} <b>Subscription:</b> {remaining}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{get_html('lightning1')} <b>Commands:</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Shopify:</b>\n"
        f"<blockquote>/sh [card] — Check single card\n/msh (reply to .txt) — Mass check</blockquote>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>PayPal:</b>\n"
        f"<blockquote>/pp [card] — Check single card\n/mpp (reply to .txt) — Mass check\n/setpp [price] — Set check price ($0.01–$10.00)</blockquote>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{get_html('info')} Use commands directly in chat."
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=make_keyboard([
            [btn("Back", "gate_back", style="danger")]
        ]))
    except TelegramBadRequest as _e:
        if "message is not modified" not in str(_e): log.error(f"edit: {_e}")

@router.callback_query(F.data == "gate_back")
async def gate_back(callback: CallbackQuery):
    await callback.answer()
    await main_menu(callback)

TOOLS_COMMANDS = [
    "/bin [BIN] - Get BIN info",
    "/gen [BIN] [count] - Generate cards",
    "/id - Show your ID and others",
    "/me - Show your profile",
    "/stats [ID] - Show user stats",
    "/redeem [key] - Redeem a key",
    "/stop - Stop all processes",
    "/f (reply to photo) - Broadcast a photo",
    "/buy [hours] - Buy subscription",
]

def tools_page(page: int = 0) -> tuple[InlineKeyboardMarkup, str]:
    rows  = []
    start = page * 5
    end   = min(start + 5, len(TOOLS_COMMANDS))
    text  = f"<b>Tools</b>\n━━━━━━━━━━━━━━━━\n"
    for i in range(start, end):
        text += f"<blockquote>{TOOLS_COMMANDS[i]}</blockquote>\n"
    nav = []
    if page > 0:
        nav.append(btn("Back", f"tools_page:{page-1}", style="primary"))
    if end < len(TOOLS_COMMANDS):
        nav.append(btn("Next", f"tools_page:{page+1}", style="primary"))
    if nav:
        rows.append(nav)
    rows.append([btn("Exit", "tools_back", style="danger")])
    return make_keyboard(rows), text

@router.callback_query(F.data == "menu_tools")
async def menu_tools(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id

    if not await _sub_guard(callback.bot, user_id, callback=callback):
        return

    await state.update_data(tools_page=0)
    keyboard, text = tools_page(0)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest as _e:
        if "message is not modified" not in str(_e): log.error(f"edit: {_e}")

@router.callback_query(F.data.startswith("tools_page:"))
async def tools_page_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    page = int(callback.data.split(":")[1])
    await state.update_data(tools_page=page)
    keyboard, text = tools_page(page)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except TelegramBadRequest as _e:
        if "message is not modified" not in str(_e): log.error(f"edit: {_e}")

@router.callback_query(F.data == "tools_back")
async def tools_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await main_menu(callback)

def vip_menu() -> InlineKeyboardMarkup:
    rows = []
    plan_names = {
        1: "1 Hour",
        3: "3 Hours",
        12: "12 Hours",
        24: "1 Day",
        72: "3 Days",
        168: "1 Week",
        720: "1 Month",
    }
    for hours in sorted(VIP_PRICES.keys()):
        stars = VIP_PRICES[hours]
        label = plan_names.get(hours, f"{hours}h")
        rows.append([btn(f"{label} - {stars}", f"vip_buy:{hours}", style="success")])
    rows.append([btn("Back", "vip_back", style="danger")])
    return make_keyboard(rows)

@router.callback_query(F.data == "menu_vip")
async def menu_vip(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if not await _sub_guard(callback.bot, user_id, callback=callback):
        return

    text = (
        f"{get_html('crown')} <b>VIP Pricing</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Choose your plan:\n"
        f"You can use /buy [hours] To buy a custom hours"
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=vip_menu())
    except TelegramBadRequest as _e:
        if "message is not modified" not in str(_e): log.error(f"edit: {_e}")

@router.callback_query(F.data.startswith("vip_buy:"))
async def vip_buy(callback: CallbackQuery):
    await callback.answer()
    hours = int(callback.data.split(":")[1])
    stars = VIP_PRICES.get(hours)
    if not stars:
        return
    await send_invoice(callback.bot, callback.from_user.id, hours, stars)

@router.callback_query(F.data == "vip_back")
async def vip_back(callback: CallbackQuery):
    await callback.answer()
    await main_menu(callback)

PROXIES_TEXT = (
    f"{get_html('proxy')} <b>Proxy Commands</b>\n"
    f"━━━━━━━━━━━━━━━━\n"
    f"<blockquote>/proxy [proxies] - Add proxies (reply to file or text)</blockquote>\n"
    f"<blockquote>/vpxy - View your proxies (paginated)</blockquote>\n"
    f"<blockquote>/chkpxy - Check all your proxies (parallel)</blockquote>\n"
    f"<blockquote>/rmpxy [proxy] - Remove a specific proxy</blockquote>\n"
    f"<blockquote>/rmlpxy - Remove all your proxies</blockquote>\n"
    f"━━━━━━━━━━━━━━━━\n"
    f"{get_html('info')} Proxies are used for card checking automatically."
)

@router.callback_query(F.data == "menu_proxies")
async def menu_proxies(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if not await _sub_guard(callback.bot, user_id, callback=callback):
        return

    try:
        await callback.message.edit_text(
            PROXIES_TEXT,
            parse_mode="HTML",
            reply_markup=make_keyboard([
                [btn("Back", "proxies_back", style="danger")]
            ])
        )
    except TelegramBadRequest as _e:
        if "message is not modified" not in str(_e): log.error(f"edit: {_e}")

@router.callback_query(F.data == "proxies_back")
async def proxies_back(callback: CallbackQuery):
    await callback.answer()
    await main_menu(callback)

@router.callback_query(F.data == "menu_admin")
async def menu_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("You are not an admin.", show_alert=True)
        return
    await callback.answer()
    from admin import ADMIN_MAIN_BUTTONS
    text = (
        f"{get_html('crown')} <b>Admin Panel</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Manage your bot settings."
    )
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=make_keyboard(ADMIN_MAIN_BUTTONS)
        )
    except TelegramBadRequest as _e:
        if "message is not modified" not in str(_e): log.error(f"edit: {_e}")

@router.message(Command("buy"))
async def cmd_buy(message: Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer("You are banned.")
        return
    if not await _sub_guard(message.bot, user_id, message=message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            f"{get_html('warning')} Usage: <code>/buy [hours]</code>\nExample: <code>/buy 24</code>",
            parse_mode="HTML"
        )
        return
    try:
        hours = int(parts[1])
        if hours <= 0:
            raise ValueError
    except ValueError:
        await message.answer(f"{get_html('error')} Invalid hours. Must be a positive integer.", parse_mode="HTML")
        return
    stars = hours * BUY_PRICE_PER_HOUR
    await send_invoice(message.bot, user_id, hours, stars)

async def send_invoice(bot: Bot, user_id: int, hours: int, stars: int):
    try:
        await bot.send_invoice(
            chat_id=user_id,
            title="P3 SHOPI Subscription",
            description=f"{hours} hours subscription",
            payload=f"sub_{hours}_{int(time.time())}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{hours} hours", amount=stars)],
            need_name=False,
            need_email=False,
            need_phone_number=False,
            is_flexible=False,
        )
    except Exception as e:
        log.error(f"Failed to send invoice: {e}")
        await bot.send_message(user_id, f"{get_html('error')} Payment system error. Try again later.")

@router.pre_checkout_query()
async def pre_checkout(pre_check: PreCheckoutQuery):
    await pre_check.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payment    = message.successful_payment
    payload    = payment.invoice_payload
    total_stars = payment.total_amount
    user_id    = message.from_user.id
    try:
        parts = payload.split("_")
        hours = int(parts[1])
    except Exception:
        hours = 0
    if hours <= 0:
        await message.answer("Payment error. Contact admin.")
        return
    now     = time.time()
    old     = await get_subscription(user_id) or now
    new_exp = max(old, now) + hours * 3600
    await set_subscription(user_id, new_exp)
    exp_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(new_exp))
    await message.answer(
        f"{get_html('crown')} <b>Subscription Activated!</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{get_html('time')} <b>Duration:</b> {hours}h\n"
        f"{get_html('star')} <b>Paid:</b> {total_stars} {get_html('star')}\n"
        f"{get_html('calendar')} <b>Expires:</b> {exp_str}",
        parse_mode="HTML"
    )