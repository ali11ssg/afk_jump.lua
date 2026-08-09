import asyncio
import time
import logging
import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS, HIT_CHAT_ID
from helpers import get_html, btn, make_keyboard, is_admin, mention_html, escape, can_use
from data import (
    ban_user, unban_user, is_user_banned,
    get_subscription, set_subscription,
    get_user_info, register_user,
    generate_key, save_key, is_key_valid, mark_key_used,
    get_all_group_chats, save_broadcast, get_broadcast_status
)

router = Router()
log = logging.getLogger("user")

_stop_events: dict[int, asyncio.Event] = {}
_stop_lock = asyncio.Lock()


async def get_stop_event(user_id: int) -> asyncio.Event:
    async with _stop_lock:
        if user_id not in _stop_events:
            _stop_events[user_id] = asyncio.Event()
        return _stop_events[user_id]


async def trigger_stop(user_id: int):
    async with _stop_lock:
        ev = _stop_events.get(user_id)
        if ev:
            ev.set()
        else:
            ev = asyncio.Event()
            ev.set()
            _stop_events[user_id] = ev


async def clear_stop(user_id: int):
    async with _stop_lock:
        _stop_events[user_id] = asyncio.Event()


def is_stopped(user_id: int) -> bool:
    ev = _stop_events.get(user_id)
    return bool(ev and ev.is_set())


def _fmt_time(seconds: float) -> str:
    if seconds <= 0:
        return "Expired"
    d = int(seconds // 86400)
    h = int((seconds % 86400) // 3600)
    m = int((seconds % 3600) // 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts) or "Less than a minute"


async def _sub_status(user_id: int) -> tuple[bool, str]:
    try:
        exp = await get_subscription(user_id)
        if exp and exp > time.time():
            return True, _fmt_time(exp - time.time())
    except Exception:
        pass
    return False, "None"


async def _admin_guard(message: Message) -> bool:
    if is_admin(message.from_user.id):
        return True
    await message.answer(
        f"{get_html('denied')} <b>You don't have permission.</b>",
        parse_mode="HTML",
    )
    return False


def _parse_uid_args(message: Message) -> tuple[int | None, list[str]]:
    parts = message.text.split()[1:]
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id, parts
    if parts:
        try:
            return int(parts[0]), parts[1:]
        except ValueError:
            pass
    return None, parts


async def _user_card(user_id: int, extra: str = "") -> str:
    info = await get_user_info(user_id) or {}
    username = info.get("username") or "—"
    firstname = info.get("first_name") or "—"
    joined = info.get("joined_date") or "—"
    active, remaining = await _sub_status(user_id)
    sub_icon = get_html("approved") if active else get_html("error")
    banned = await is_user_banned(user_id)
    ban_icon = get_html("stop") if banned else get_html("approved")
    text = (
        f"{get_html('user')} <b>User Info</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('id_card')} <b>ID:</b> <code>{user_id}</code>\n"
        f"{get_html('info')} <b>Name:</b> {escape(firstname)}\n"
        f"{get_html('chat')} <b>Username:</b> @{escape(username)}\n"
        f"{get_html('calendar')} <b>Joined:</b> {escape(str(joined))[:10]}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{sub_icon} <b>Subscription:</b> {remaining}\n"
        f"{ban_icon} <b>Status:</b> {'Banned' if banned else 'Active'}\n"
    )
    if extra:
        text += f"━━━━━━━━━━━━━━━━━━\n{extra}\n"
    return text


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not await _admin_guard(message):
        return
    uid, _ = _parse_uid_args(message)
    if not uid:
        await message.answer(
            f"{get_html('warning')} Usage: <code>/ban [ID]</code> or reply to a message",
            parse_mode="HTML",
        )
        return
    if is_admin(uid):
        await message.answer(
            f"{get_html('denied')} <b>You cannot ban an admin.</b>",
            parse_mode="HTML",
        )
        return
    await ban_user(uid)
    await message.answer(
        f"{get_html('stop')} <b>User Banned</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('id_card')} <b>ID:</b> <code>{uid}</code>",
        parse_mode="HTML",
    )


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not await _admin_guard(message):
        return
    uid, _ = _parse_uid_args(message)
    if not uid:
        await message.answer(
            f"{get_html('warning')} Usage: <code>/unban [ID]</code> or reply to a message",
            parse_mode="HTML",
        )
        return
    await unban_user(uid)
    await message.answer(
        f"{get_html('approved')} <b>User Unbanned</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('id_card')} <b>ID:</b> <code>{uid}</code>",
        parse_mode="HTML",
    )


@router.message(Command("give"))
async def cmd_give(message: Message):
    if not await _admin_guard(message):
        return
    uid, rest = _parse_uid_args(message)
    if not uid or not rest:
        await message.answer(
            f"{get_html('warning')} Usage: <code>/give [ID] [hours]</code>",
            parse_mode="HTML",
        )
        return
    try:
        hours = float(rest[0])
    except (ValueError, IndexError):
        await message.answer(
            f"{get_html('error')} Hours must be a number.",
            parse_mode="HTML",
        )
        return
    now = time.time()
    old = await get_subscription(uid) or now
    new_exp = max(old, now) + hours * 3600
    await set_subscription(uid, new_exp)
    exp_str = datetime.datetime.fromtimestamp(new_exp).strftime("%Y-%m-%d %H:%M")
    await message.answer(
        f"{get_html('crown')} <b>Time Added</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('id_card')} <b>ID:</b> <code>{uid}</code>\n"
        f"{get_html('time')} <b>Added:</b> {hours}h\n"
        f"{get_html('calendar')} <b>Expires:</b> {exp_str}",
        parse_mode="HTML",
    )


@router.message(Command("key"))
async def cmd_key(message: Message):
    if not await _admin_guard(message):
        return
    parts = message.text.split()[1:]
    if len(parts) < 1:
        await message.answer(
            f"{get_html('warning')} Usage:\n"
            "<code>/key [hours] [amount=1] [max_uses=1]</code>\n\n"
            "Example: <code>/key 24 5 3</code>\n"
            "→ 5 keys, each usable by 3 people for 24 hours",
            parse_mode="HTML",
        )
        return
    try:
        hours = int(parts[0])
        amount = int(parts[1]) if len(parts) > 1 else 1
        max_uses = int(parts[2]) if len(parts) > 2 else 1
    except ValueError:
        await message.answer(
            f"{get_html('error')} Invalid numbers. Example: <code>/key 24 5 3</code>",
            parse_mode="HTML",
        )
        return
    amount = min(amount, 50)
    max_uses = max(1, max_uses)
    keys = []
    for _ in range(amount):
        code = generate_key(hours, message.from_user.id, max_uses)
        await save_key(code, hours, message.from_user.id, max_uses)
        keys.append(code)

    dev_link = f"[{get_html('lightning1')}] <b>𝐁𝐲:</b> {mention_html(ADMIN_IDS[0], '3LTZ | Ali') if ADMIN_IDS else '3LTZ | Ali'}"

    if amount == 1:
        key = keys[0]
        text = (
            f"<b>𝐍𝐞𝐰 𝐊𝐞𝐲 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝</b>\n"
            f"★━━━━━━━━━━━━━━★\n"
            f"[{get_html('lightning1')}] <b>𝐊𝐞𝐲:</b> {key}\n"
            f"[{get_html('lightning1')}] <b>𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:</b> {hours}h\n"
            f"[{get_html('lightning1')}] <b>𝐌𝐚𝐱 𝐔𝐬𝐞𝐬:</b> {max_uses}\n"
            f"★━━━━━━━━━━━━━━★\n"
            f"<code>/redeem {key}</code>\n"
            f"★━━━━━━━━━━━━━━★\n"
            f"{dev_link}"
        )
    else:
        keys_lines = [f"<code>{k}</code>" for k in keys]
        keys_text = "\n".join(keys_lines)
        text = (
            f"<b>𝐍𝐞𝐰 𝐊𝐞𝐲𝐬 𝐆𝐞𝐧𝐞𝐫𝐚𝐭𝐞𝐝</b>\n"
            f"★━━━━━━━━━━━━━━★\n"
            f"[{get_html('lightning1')}] <b>𝐀𝐦𝐨𝐮𝐧𝐭:</b> {amount}\n"
            f"[{get_html('lightning1')}] <b>𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:</b> {hours}h\n"
            f"[{get_html('lightning1')}] <b>𝐌𝐚𝐱 𝐔𝐬𝐞𝐬:</b> {max_uses}\n"
            f"★━━━━━━━━━━━━━━★\n"
            f"[{get_html('lightning1')}] <b>𝐊𝐞𝐲𝐬:</b>\n\n"
            f"{keys_text}\n\n"
            f"Use /redeem [key] to activate\n"
            f"★━━━━━━━━━━━━━━★\n"
            f"{dev_link}"
        )

    await message.answer(text, parse_mode="HTML")


@router.message(Command("ung"))
async def cmd_ung(message: Message):
    if not await _admin_guard(message):
        return
    uid, rest = _parse_uid_args(message)
    if not uid:
        await message.answer(
            f"{get_html('warning')} Usage:\n"
            "<code>/ung [ID]</code> ← Remove all time\n"
            "<code>/ung [ID] [hours]</code> ← Remove specific time",
            parse_mode="HTML",
        )
        return
    now = time.time()
    current_exp = await get_subscription(uid) or now
    if not rest:
        await set_subscription(uid, now)
        await message.answer(
            f"{get_html('trash')} <b>All Time Removed</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{get_html('id_card')} <b>ID:</b> <code>{uid}</code>",
            parse_mode="HTML",
        )
        return
    try:
        hours = float(rest[0])
    except ValueError:
        await message.answer(
            f"{get_html('error')} Hours must be a number.",
            parse_mode="HTML",
        )
        return
    remaining = max(current_exp - hours * 3600, now)
    await set_subscription(uid, remaining)
    left = _fmt_time(remaining - now)
    await message.answer(
        f"{get_html('money')} <b>Time Deducted</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('id_card')} <b>ID:</b> <code>{uid}</code>\n"
        f"{get_html('trash')} <b>Deducted:</b> {hours}h\n"
        f"{get_html('time')}  <b>Remaining:</b> {left}",
        parse_mode="HTML",
    )


@router.message(Command("id"))
async def cmd_id(message: Message):
    lines = [f"{get_html('id_card')} <b>ID Info</b>\n━━━━━━━━━━━━━━━━━━"]
    u = message.from_user
    lines.append(
        f"\n{get_html('user')} <b>You</b>\n"
        f"  <b>ID:</b> <code>{u.id}</code>\n"
        f"  <b>Name:</b> {escape(u.full_name)}\n"
        f"  <b>Username:</b> @{u.username or '—'}"
    )
    if message.reply_to_message and message.reply_to_message.from_user:
        r = message.reply_to_message.from_user
        lines.append(
            f"\n{get_html('chat')} <b>Reply To</b>\n"
            f"  <b>ID:</b> <code>{r.id}</code>\n"
            f"  <b>Name:</b> {escape(r.full_name)}\n"
            f"  <b>Username:</b> @{r.username or '—'}"
        )
    if message.chat.type in ("group", "supergroup", "channel"):
        c = message.chat
        lines.append(
            f"\n{get_html('globe')} <b>Group</b>\n"
            f"  <b>ID:</b> <code>{c.id}</code>\n"
            f"  <b>Name:</b> {escape(c.title or '—')}\n"
            f"  <b>Username:</b> @{c.username or '—'}"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("me"))
async def cmd_me(message: Message):
    uid = message.from_user.id
    user = message.from_user
    await register_user(uid, user.username or "", user.first_name or "")
    active, remaining = await _sub_status(uid)
    sub_icon = get_html("crown") if active else get_html("lock")
    banned = await is_user_banned(uid)
    ban_icon = get_html("stop") if banned else get_html("approved")
    adm_icon = get_html("admin") if is_admin(uid) else get_html("user")
    exp_ts = await get_subscription(uid) or 0
    exp_str = (
        datetime.datetime.fromtimestamp(exp_ts).strftime("%Y-%m-%d %H:%M")
        if exp_ts > time.time() else "—"
    )
    text = (
        f"{get_html('sparkle')} <b>Your Profile</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{adm_icon} <b>Name:</b> {escape(user.full_name)}\n"
        f"{get_html('id_card')} <b>ID:</b> <code>{uid}</code>\n"
        f"{get_html('chat')} <b>Username:</b> @{user.username or '—'}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{sub_icon} <b>Subscription:</b> {remaining}\n"
        f"{get_html('calendar')} <b>Expires:</b> {exp_str}\n"
        f"{ban_icon} <b>Status:</b> {'Banned' if banned else 'Active'}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('info')} <b>Role:</b> {'Admin' if is_admin(uid) else 'User'}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("stop"))
async def cmd_stop(message: Message):
    uid = message.from_user.id
    await trigger_stop(uid)
    await message.answer(
        f"{get_html('stop')} <b>All Processes Stopped</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('info')} Card checking, proxies, and other operations\n"
        f"have been stopped.",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    parts = message.text.split()[1:]
    uid = message.from_user.id
    if message.reply_to_message and message.reply_to_message.from_user:
        uid = message.reply_to_message.from_user.id
    elif parts:
        try:
            uid = int(parts[0])
        except ValueError:
            uname = parts[0].lstrip("@")
            info = await get_user_info(0)
            if not info:
                await message.answer(
                    f"{get_html('error')} <b>User not found.</b>",
                    parse_mode="HTML",
                )
                return
    info = await get_user_info(uid)
    if not info:
        await message.answer(
            f"{get_html('warning')} <b>User not registered.</b>",
            parse_mode="HTML",
        )
        return
    active, remaining = await _sub_status(uid)
    sub_icon = get_html("crown") if active else get_html("lock")
    banned = await is_user_banned(uid)
    text = (
        f"{get_html('stats')} <b>User Stats</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('id_card')} <b>ID:</b> <code>{uid}</code>\n"
        f"{get_html('info')} <b>Name:</b> {escape(info.get('first_name','—'))}\n"
        f"{get_html('chat')} <b>Username:</b> @{info.get('username','—')}\n"
        f"{get_html('calendar')} <b>Joined:</b> {str(info.get('joined_date','—'))[:10]}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{sub_icon} <b>Subscription:</b> {remaining}\n"
        f"{get_html('stop') if banned else get_html('approved')} "
        f"<b>Status:</b> {'Banned' if banned else 'Active'}\n"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("redeem"))
async def cmd_redeem(message: Message):
    uid = message.from_user.id
    user = message.from_user
    parts = message.text.split()[1:]
    if not parts:
        await message.answer(
            f"{get_html('key')} Usage: <code>/redeem [key]</code>",
            parse_mode="HTML",
        )
        return
    key_code = parts[0].strip().upper()
    active, remaining = await _sub_status(uid)
    if active:
        await message.answer(
            f"{get_html('warning')} <b>You have an active subscription!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{get_html('time')} Remaining: <b>{remaining}</b>\n"
            f"{get_html('info')} You cannot use a new key until your subscription expires.",
            parse_mode="HTML",
        )
        return
    hours = await is_key_valid(key_code)
    if hours is None:
        await message.answer(
            f"{get_html('error')} <b>Invalid or used key.</b>",
            parse_mode="HTML",
        )
        return
    await register_user(uid, user.username or "", user.first_name or "")
    await mark_key_used(key_code)
    new_exp = time.time() + hours * 3600
    await set_subscription(uid, new_exp)
    exp_str = datetime.datetime.fromtimestamp(new_exp).strftime("%Y-%m-%d %H:%M")
    await message.answer(
        f"{get_html('sparkle')} <b>Key Activated!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{get_html('key')} <b>Key:</b> <code>{key_code}</code>\n"
        f"{get_html('time')} <b>Duration:</b> {hours}h\n"
        f"{get_html('calendar')} <b>Expires:</b> {exp_str}",
        parse_mode="HTML",
    )

    try:
        if HIT_CHAT_ID:
            dev_link = f"[{get_html('lightning1')}] <b>𝐁𝐲:</b> {mention_html(ADMIN_IDS[0], '3LTZ | Ali') if ADMIN_IDS else '3LTZ | Ali'}"
            notification = (
                f"{get_html('lightning1')} <b>𝗡𝗲𝘄 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗔𝗰𝘁𝗶𝘃𝗮𝘁𝗲𝗱</b>\n"
                f"★━━━━━━━━━━━━━━★\n"
                f"[{get_html('lightning1')}] <b>𝐔𝐬𝐞𝐫:</b> {escape(user.full_name)}\n"
                f"[{get_html('lightning1')}] <b>𝐊𝐞𝐲:</b> {key_code}\n"
                f"[{get_html('lightning1')}] <b>𝐃𝐮𝐫𝐚𝐭𝐢𝐨𝐧:</b> {hours}h\n"
                f"[{get_html('lightning1')}] <b>𝐄𝐱𝐩𝐢𝐫𝐞𝐬:</b> {exp_str}\n"
                f"★━━━━━━━━━━━━━━★\n"
                f"{dev_link}"
            )
            await message.bot.send_message(HIT_CHAT_ID, notification, parse_mode="HTML")
    except Exception as e:
        log.error(f"Failed to send subscription notification: {e}")


@router.message(Command("f"))
async def cmd_broadcast(message: Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer("You are banned.")
        return
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.answer(
            f"{get_html('warning')} <b>Usage:</b> Reply to a photo with <code>/f</code>\n"
            "Optional: Add a caption after the command.",
            parse_mode="HTML",
        )
        return
    caption = message.text.replace("/f", "").strip() if message.text else ""
    photo = message.reply_to_message.photo[-1]
    file_id = photo.file_id
    user = message.from_user
    first_name = escape(user.full_name)
    uid = user.id
    username = user.username or "—"
    lightning = get_html("lightning1")
    user_icon = get_html("user")
    id_icon = get_html("id_card")
    chat_icon = get_html("chat")
    msg_icon = get_html("chat")
    admin_preview = (
        f"★━━━━━━━━━━━━━━★\n"
        f"{lightning} <b>New Broadcast Request</b>\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{user_icon} <b>User:</b> {first_name}\n"
        f"{id_icon} <b>UID:</b> <code>{uid}</code>\n"
        f"{chat_icon} <b>Username:</b> @{username}\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{msg_icon} <b>Message:</b>\n{caption if caption else 'None'}\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{lightning} <b>Approve or Reject:</b>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Accept", callback_data=f"f_accept:{uid}:{message.message_id}"),
            InlineKeyboardButton(text="Reject", callback_data=f"f_reject:{uid}:{message.message_id}"),
        ]
    ])
    await message.bot.send_photo(
        chat_id=ADMIN_IDS[0] if ADMIN_IDS else user_id,
        photo=file_id,
        caption=admin_preview,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await message.answer(
        f"{get_html('approved')} <b>Broadcast submitted for admin approval.</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("f_accept:"))
async def broadcast_accept(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("You are not an admin.", show_alert=True)
        return
    data = callback.data.split(":")
    user_id = int(data[1])
    msg_id = int(data[2])
    await callback.message.delete()
    await callback.answer("Broadcast approved.")
    msg = callback.message
    caption_parts = msg.caption.split("★━━━━━━━━━━━━━━★")
    user_info = caption_parts[1] if len(caption_parts) > 1 else ""
    msg_content = caption_parts[3] if len(caption_parts) > 3 else ""
    user_name = ""
    user_uid = ""
    user_uname = ""
    for line in user_info.split("\n"):
        if "User:" in line:
            user_name = line.replace("User:", "").strip()
        if "UID:" in line:
            user_uid = line.replace("UID:", "").strip()
        if "Username:" in line:
            user_uname = line.replace("Username:", "").strip()
    for line in msg_content.split("\n"):
        if "Message:" in line:
            caption = line.replace("Message:", "").strip()
            break
    lightning = get_html("lightning1")
    user_icon = get_html("user")
    id_icon = get_html("id_card")
    chat_icon = get_html("chat")
    star_icon = get_html("star")
    dev_id = ADMIN_IDS[0] if ADMIN_IDS else 0
    dev_mention = mention_html(dev_id, "3LTZ | Ali") if dev_id else "3LTZ | Ali"
    broadcast_text = (
        f"★━━━━━━━━━━━━━━★\n"
        f"{user_icon} <b>User:</b> {user_name}\n"
        f"{id_icon} <b>UID:</b> {user_uid}\n"
        f"{chat_icon} <b>Username:</b> @{user_uname}\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{star_icon} <b>Message:</b>\n{caption if caption else 'None'}\n"
        f"★━━━━━━━━━━━━━━★\n"
        f"{lightning} <b>Bot By:</b> {dev_mention}"
    )
    groups = await get_all_group_chats()
    success = 0
    for group_id in groups:
        try:
            await callback.bot.send_photo(
                chat_id=group_id,
                photo=msg.photo[-1].file_id,
                caption=broadcast_text,
                parse_mode="HTML"
            )
            success += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error(f"Failed to send to {group_id}: {e}")
    await callback.bot.send_message(
        chat_id=user_id,
        text=f"{get_html('approved')} <b>Your broadcast was published to {success} groups.</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("f_reject:"))
async def broadcast_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("You are not an admin.", show_alert=True)
        return
    data = callback.data.split(":")
    user_id = int(data[1])
    msg_id = int(data[2])
    await callback.message.delete()
    await callback.answer("Broadcast rejected.")
    await callback.bot.send_message(
        chat_id=user_id,
        text=f"{get_html('denied')} <b>Your broadcast was rejected by admin.</b>",
        parse_mode="HTML"
    )