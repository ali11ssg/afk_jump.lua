import asyncio
import aiohttp
import random
import re
import time
import logging
from typing import Optional, List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter

from config import ADMIN_IDS, MAX_CARDS
from helpers import get_html, escape, is_admin
from data import (
    get_user_info,
    register_user,
    is_user_banned,
    get_subscription,
    save_bin_lookup,
    get_bin_lookup_cache,
)

router = Router()
BIN_API_URL = "https://bins.antipublic.cc/bins/{}"
log = logging.getLogger(__name__)

# ─── Helpers ────────────────────────────────────────────────────────────────

async def safe_send(target, text, parse_mode="HTML", **kwargs):
    try:
        await target.answer(text, parse_mode=parse_mode, **kwargs)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await target.answer(text, parse_mode=parse_mode, **kwargs)
    except Exception as e:
        log.error(f"Failed to send message: {e}")

def luhn_checksum(card_number: str) -> int:
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13:
        return -1
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10

def is_valid_luhn(card_number: str) -> bool:
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

def is_expired(mm: str, yy: str) -> bool:
    try:
        month = int(mm)
        year = int(yy)
        if len(yy) == 2:
            year += 2000
        now = time.localtime()
        return year < now.tm_year or (year == now.tm_year and month < now.tm_mon)
    except ValueError:
        return True

def is_duplicate(card: str, card_list: List[str]) -> bool:
    return card in card_list

def generate_single_card(bin_prefix: str, length: int = 16) -> Optional[str]:
    if len(bin_prefix) > length or len(bin_prefix) < 6:
        return None
    card = bin_prefix
    while len(card) < length - 1:
        card += str(random.randint(0, 9))
    check = luhn_checksum(card + "0")
    if check < 0:
        return None
    card += str(check)
    if len(card) != length or not is_valid_luhn(card):
        return None
    return card

def generate_random_date() -> tuple[str, str]:
    now = time.localtime()
    year = random.randint(now.tm_year, now.tm_year + 5)
    month = random.randint(1, 12)
    if year == now.tm_year and month < now.tm_mon:
        month = random.randint(now.tm_mon, 12)
    return f"{month:02d}", str(year)[-2:]

def generate_cvv() -> str:
    return f"{random.randint(100, 999)}"

def generate_card_with_bin(bin_prefix: str, length: int = 16) -> Optional[str]:
    card_num = generate_single_card(bin_prefix, length)
    if not card_num:
        return None
    mm, yy = generate_random_date()
    cvv = generate_cvv()
    return f"{card_num}|{mm}|{yy}|{cvv}"

def generate_cards(bin_prefix: str, count: int, length: int = 16) -> List[str]:
    cards = []
    seen = set()
    attempts = 0
    max_attempts = count * 5
    while len(cards) < count and attempts < max_attempts:
        attempts += 1
        card = generate_card_with_bin(bin_prefix, length)
        if card and card not in seen:
            seen.add(card)
            cards.append(card)
    return cards

async def get_bin_info(bin_code: str) -> dict:
    cache = await get_bin_lookup_cache(bin_code)
    if cache:
        return cache
    url = BIN_API_URL.format(bin_code)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = {
                        "bin": data.get("bin", ""),
                        "brand": data.get("brand", "UNKNOWN").upper(),
                        "country": data.get("country", ""),
                        "country_name": data.get("country_name", "UNKNOWN"),
                        "country_flag": data.get("country_flag", ""),
                        "bank": data.get("bank", "UNKNOWN"),
                        "level": data.get("level", ""),
                        "type": data.get("type", "UNKNOWN"),
                        "currency": data.get("country_currencies", [""])[0] if data.get("country_currencies") else ""
                    }
                    await save_bin_lookup(bin_code, result)
                    return result
    except Exception as e:
        log.error(f"BIN lookup failed: {e}")
    return {
        "bin": bin_code,
        "brand": "UNKNOWN",
        "country": "",
        "country_name": "UNKNOWN",
        "country_flag": "",
        "bank": "UNKNOWN",
        "level": "",
        "type": "UNKNOWN",
        "currency": ""
    }

# ─── Commands ──────────────────────────────────────────────────────────────

@router.message(Command("bin"))
async def cmd_bin(message: Message):
    user_id = message.from_user.id
    user = message.from_user
    await register_user(user_id, user.username or "", user.first_name or "")
    if await is_user_banned(user_id):
        await safe_send(message, "🚫 You are banned.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await safe_send(message, "📌 Usage: <code>/bin [BIN]</code> (first 6 digits)")
        return
    bin_code = parts[1].strip()[:6]
    if not bin_code.isdigit() or len(bin_code) < 6:
        await safe_send(message, "❌ Invalid BIN. Must be 6 digits.")
        return

    start_time = time.time()
    info = await get_bin_info(bin_code)
    elapsed = round(time.time() - start_time, 2)

    first_name = escape(message.from_user.first_name or "User")
    dev_name = "3LTZ | Ali"

    text = (
        f"🔹 <b>BIN Lookup</b> 🔹\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💳 <b>BIN:</b> <code>{info['bin']}</code>\n"
        f"🏷️ <b>Brand:</b> {info['brand']}\n"
        f"📊 <b>Type:</b> {info['type']}\n"
        f"🏛️ <b>Bank:</b> {info['bank']}\n"
        f"🌍 <b>Country:</b> {info['country_name']} {info['country_flag']}\n"
        f"💰 <b>Currency:</b> {info['currency'] or 'N/A'}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Time:</b> {elapsed}s\n"
        f"👤 <b>Checked by:</b> {first_name}\n"
        f"⚡ <b>By:</b> {dev_name}"
    )
    await safe_send(message, text)

@router.message(Command("gen"))
async def cmd_gen(message: Message):
    user_id = message.from_user.id
    user = message.from_user
    await register_user(user_id, user.username or "", user.first_name or "")
    if await is_user_banned(user_id):
        await safe_send(message, "🚫 You are banned.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await safe_send(
            message,
            "💳 <b>Usage:</b>\n"
            "<code>/gen [BIN] [count]</code>\n\n"
            "Example: <code>/gen 424242 50</code>\n"
            "Max count: <b>5000</b> cards",
            parse_mode="HTML"
        )
        return

    bin_prefix = parts[1].strip()[:6]
    if not bin_prefix.isdigit() or len(bin_prefix) < 6:
        await safe_send(message, "❌ Invalid BIN. Must be 6 digits.")
        return

    count = 10
    if len(parts) >= 3:
        try:
            count = max(1, int(parts[2]))
        except ValueError:
            pass

    if count > 5000:
        count = 5000

    bin_info = await get_bin_info(bin_prefix)
    brand    = bin_info.get("brand", "UNKNOWN")
    btype    = bin_info.get("type", "UNKNOWN")
    bank     = bin_info.get("bank", "UNKNOWN")
    country  = bin_info.get("country_name", "UNKNOWN")
    flag     = bin_info.get("country_flag", "")
    level    = bin_info.get("level", "")

    cards = generate_cards(bin_prefix, count)
    if not cards:
        await safe_send(message, "❌ Generation failed. Try another BIN.")
        return

    first_name = escape(user.first_name or "User")
    dev_name   = "3LTZ | Ali"

    bin_header = (
        f"🎰 <b>BIN Generator</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💳 <b>BIN:</b> <code>{bin_prefix}</code>\n"
        f"🏛️ <b>Bank:</b> {bank}\n"
        f"🌍 <b>Country:</b> {country} {flag}\n"
        f"🏷️ <b>Brand:</b> {brand}{f' · {level}' if level else ''}\n"
        f"📊 <b>Type:</b> {btype}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Generated:</b> {len(cards)} cards\n"
        f"👤 <b>By:</b> {first_name} • {dev_name}"
    )

    if len(cards) <= 20:
        cards_text = "\n".join(cards)
        await safe_send(
            message,
            bin_header + "\n━━━━━━━━━━━━━━━━\n" + f"<code>{cards_text}</code>",
            parse_mode="HTML"
        )
    else:
        txt_content = "\n".join(cards)
        file = BufferedInputFile(txt_content.encode(), filename=f"gen_{bin_prefix}_{len(cards)}.txt")
        try:
            await message.answer_document(file, caption=bin_header, parse_mode="HTML")
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await message.answer_document(file, caption=bin_header, parse_mode="HTML")
        except Exception as e:
            log.error(f"Failed to send gen file: {e}")
            await safe_send(message, f"❌ Failed to send file: {str(e)[:100]}")