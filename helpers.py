import html
import logging
import re
import time
from typing import Optional, List

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CopyTextButton,
)

from config import ADMIN_IDS

EMOJIS: dict[str, tuple[str, str]] = {
    "approved":     ("✅",   "6017332873428733925"),
    "error":        ("❌",   "5316660455744223443"),
    "declined":     ("❌",   "6016914431944953922"),
    "error_emoji":  ("⚠️",  "5447381715293074599"),
    "warning":      ("⚠️",  "5447592907424955482"),
    "info":         ("ℹ️",  "5444889156792646660"),
    "denied":       ("🚫",   "6017004072207388976"),
    "stop":         ("🚫",   "5454156248813432363"),
    "dead":         ("💀",   "4958642964181025908"),
    "money":        ("💵",   "5447579253723918909"),
    "bank":         ("🏦",   "5258476306152038031"),
    "card":         ("💳",   "5447453226498552490"),
    "charge":       ("🔥",   "5222148368955877900"),
    "user":         ("👤",   "5992129361090711368"),
    "crown":        ("👑",   "6017070992092829026"),
    "admin":        ("👑",   "6016865155785167117"),
    "lock":         ("🔒",   "5393302369024882368"),
    "star":         ("⭐",   "5258165702707125574"),
    "globe":        ("🌐",   "5447602197439218445"),
    "flag":         ("🏳️",  "5256143829672672750"),
    "proxy":        ("🛡️",  "5372917041193828849"),
    "shopify":      ("🛍️",  "6014739593650247255"),
    "time":         ("⏱️",  "5445350406215465190"),
    "speed":        ("⏱️",  "5850317551090800862"),
    "tools":        ("⚙️",  "5444869180899752137"),
    "tool_bin":     ("🔎",   "5226513232549664618"),
    "tool_gen":     ("⚡",   "5219943216781995020"),
    "tool_fake":    ("🎭",   "5220197908342648622"),
    "tool_proxy":   ("🛡️",  "5292226786229236118"),
    "bin":          ("🔢",   "5226513232549664618"),
    "search":       ("🔍",   "6032850693348399258"),
    "megaphone":    ("📢",   "6021418126061605425"),
    "back":         ("🔙",   "5447506720316225765"),
    "forward":      ("▶️",  "5870450390679425417"),
    "stats":        ("📊",   "5870995486453796729"),
    "wallet":       ("💰",   "5447579253723918909"),
    "target":       ("🎯",   "5258165702707125574"),
    "growth":       ("📈",   "5870450390679425417"),
    "calendar":     ("📅",   "5870995486453796729"),
    "id_card":      ("🪪",   "5447453226498552490"),
    "key":          ("🔑",   "5226513232549664618"),
    "recycle":      ("♻️",  "5402104393396931859"),
    "notebook":     ("📋",   "5870995486453796729"),
    "rocket":       ("🚀",   "5219943216781995020"),
    "rabbit":       ("🐇",   "5850317551090800862"),
    "turtle":       ("🐢",   "5316977222467206948"),
    "slow":         ("🐌",   "5316977222467206948"),
    "chat":         ("💬",   "5444889156792646660"),
    "trash":        ("🗑️",  "5316660455744223443"),
    "clip":         ("📎",   "5447592907424955482"),
    "video_cam":    ("🎬",   "5220197908342648622"),
    "photo_icon":   ("🖼",   "5447592907424955482"),
    "shop_bag":     ("🛒",   "6014739593650247255"),
    "sparkle":      ("✨",   "5402104393396931859"),
    "seedling":     ("🌱",   "5402104393396931859"),
    "eagle_icon":   ("🦅",   "6017070992092829026"),
    "medal1":       ("🥇",   "5316544002000958685"),
    "medal2":       ("🥈",   "5316673387890751150"),
    "medal3":       ("🥉",   "5316702039617583319"),
    "star_glow":    ("🌟",   "5402104393396931859"),
    "list":         ("📋",   "5870995486453796729"),
    "diamond":      ("💎",   "5316809461044623413"),
    "success":      ("✅",   "6017332873428733925"),
    "gate":         ("🛍️",  "6014739593650247255"),
    "status":       ("📊",   "5870995486453796729"),
    "cooking_time": ("⏳",   "5445350406215465190"),
    "lightning1":   ("⚡",   "5219943216781995020"),
    "fire":         ("🔥",   "5222148368955877900"),
    "hit":          ("🔥",   "5222148368955877900"),
    "link":         ("🔗",   "5447506720316225765"),
    "plus":         ("➕",   "5258476306152038031"),
}

def get_html(name: str) -> str:
    entry = EMOJIS.get(name)
    if not entry:
        return ""
    fallback, emoji_id = entry
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def get_emoji_id(name: str) -> str | None:
    entry = EMOJIS.get(name)
    return entry[1] if entry else None

def get_fallback(name: str) -> str:
    entry = EMOJIS.get(name)
    return entry[0] if entry else ""

_STYLE_EMOJI: dict[str, str] = {
    "success": "approved",
    "danger":  "stop",
    "primary": "forward",
    "warning": "warning",
    "info":    "info",
    "default": "",
}

VALID_STYLES = {"success", "primary", "danger"}

def btn(
    text: str,
    callback: str = "",
    *,
    style: str = "default",
    emoji_id: str | None = None,
    url: str | None = None,
) -> InlineKeyboardButton:
    icon_id = emoji_id
    if not icon_id and style in _STYLE_EMOJI:
        icon_id = get_emoji_id(_STYLE_EMOJI[style])
    
    kwargs = {}
    if icon_id:
        kwargs["icon_custom_emoji_id"] = str(icon_id)
    if style in VALID_STYLES:
        kwargs["style"] = style
        
    if url:
        return InlineKeyboardButton(text=text, url=url, **kwargs)
    
    return InlineKeyboardButton(text=text, callback_data=callback or "noop", **kwargs)

def copy_btn(text: str, copy_text: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=f"🟢 {text}", copy_text=CopyTextButton(text=copy_text))

def url_btn(text: str, url: str, style: str = "default", emoji_id: str | None = None) -> InlineKeyboardButton:
    return btn(text, url=url, style=style, emoji_id=emoji_id)

def make_keyboard(rows: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)

def single_keyboard(text: str, callback: str, style: str = "default") -> InlineKeyboardMarkup:
    return make_keyboard([[btn(text, callback, style=style)]])

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def can_use(user_id: int) -> bool:
    """يفحص إذا المستخدم يقدر يستخدم البوت (أدمن أو عنده اشتراك نشط)."""
    if is_admin(user_id):
        return True
    try:
        from data import get_subscription
        sub = await get_subscription(user_id)
        return bool(sub and sub > time.time())
    except Exception:
        return False

def safe_html_truncate(text: str, max_len: int = 4096) -> str:
    if len(text) <= max_len:
        return text
    cut = text[:max_len - 3]
    last_open = cut.rfind('<')
    last_close = cut.rfind('>')
    if last_open > last_close:
        cut = cut[:last_open]
    return cut + "..."

def strip_tg_emoji(text: str) -> str:
    return re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', text, flags=re.DOTALL)

def strip_html(text: str) -> str:
    clean = strip_tg_emoji(text)
    return re.sub(r'<[^>]+>', '', clean)

def mention_html(user_id: int, name: str) -> str:
    safe = html.escape(name[:30])
    return f'<a href="tg://user?id={user_id}">{safe}</a>'

def escape(text: str) -> str:
    return html.escape(str(text))

gate_log = logging.getLogger("gate")
