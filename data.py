import aiosqlite
import asyncio
import time
import random
import string
import json
import logging
import os
from typing import Optional, List, Dict, Any

from config import DB_PATH

log = logging.getLogger(__name__)

def ensure_data_dir():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

_db_connection: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()

async def get_db() -> aiosqlite.Connection:
    global _db_connection
    if _db_connection is None:
        async with _db_lock:
            if _db_connection is None:
                ensure_data_dir()
                _db_connection = await aiosqlite.connect(DB_PATH, timeout=30)
                await _db_connection.execute("PRAGMA journal_mode=WAL")
                await _db_connection.execute("PRAGMA synchronous=NORMAL")
                await _db_connection.execute("PRAGMA cache_size=-10000")
    return _db_connection

async def init_db():
    db = await get_db()
    await db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_date INTEGER DEFAULT (strftime('%s', 'now')),
            subscription_expiry INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            key_code TEXT PRIMARY KEY,
            hours INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS user_proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            proxy TEXT NOT NULL,
            speed INTEGER DEFAULT 0,
            country TEXT DEFAULT '?',
            added_at INTEGER DEFAULT (strftime('%s', 'now')),
            UNIQUE(user_id, proxy)
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS global_proxies (
            proxy TEXT PRIMARY KEY,
            speed INTEGER DEFAULT 0,
            country TEXT DEFAULT '?',
            added_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS bin_cache (
            bin_code TEXT PRIMARY KEY,
            data TEXT,
            cached_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS check_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            card TEXT,
            status TEXT,
            response TEXT,
            price REAL,
            elapsed REAL,
            gateway TEXT,
            proxy TEXT,
            checked_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            caption TEXT,
            photo_id TEXT,
            status TEXT,
            created_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS user_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            card TEXT NOT NULL,
            added_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS gateways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            site TEXT NOT NULL,
            added_by INTEGER,
            added_at INTEGER DEFAULT (strftime('%s', 'now')),
            status TEXT DEFAULT 'unknown',
            last_check INTEGER DEFAULT 0,
            speed INTEGER DEFAULT 0
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS apis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_url TEXT NOT NULL,
            added_by INTEGER,
            added_at INTEGER DEFAULT (strftime('%s', 'now')),
            status TEXT DEFAULT 'unknown',
            last_check INTEGER DEFAULT 0,
            speed INTEGER DEFAULT 0
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS paypal_gateways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT NOT NULL UNIQUE,
            added_by INTEGER,
            added_at INTEGER DEFAULT (strftime('%s', 'now')),
            status TEXT DEFAULT 'unknown',
            speed INTEGER DEFAULT 0
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS pp_user_price (
            user_id INTEGER PRIMARY KEY,
            price REAL DEFAULT 1.0
        )
    ''')
    # عامود الهتس العالمي المشترك - يبدأ من 5840
    await db.execute('''
        CREATE TABLE IF NOT EXISTS global_hits (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total INTEGER DEFAULT 5840
        )
    ''')
    await db.execute(
        'INSERT OR IGNORE INTO global_hits (id, total) VALUES (1, 5840)'
    )
    await db.commit()

async def execute_query(query: str, params: tuple = (), commit: bool = False):
    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        if commit:
            await db.commit()
        return cursor
    except Exception as e:
        log.error(f"Database error: {e}, query: {query}, params: {params}")
        raise

# ──────────────────────────────────────────────
#  Users
# ──────────────────────────────────────────────

async def register_user(user_id: int, username: str = "", first_name: str = ""):
    await execute_query(
        'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
        (user_id, username, first_name), commit=True
    )

async def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cur:
        row = await cur.fetchone()
        if row:
            return {
                "user_id": row[0],
                "username": row[1],
                "first_name": row[2],
                "joined_date": row[3],
                "subscription_expiry": row[4],
                "is_banned": row[5]
            }
        return None

async def get_all_users() -> List[int]:
    db = await get_db()
    async with db.execute('SELECT user_id FROM users') as cur:
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def ban_user(user_id: int):
    await execute_query('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,), commit=True)

async def unban_user(user_id: int):
    await execute_query('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,), commit=True)

async def is_user_banned(user_id: int) -> bool:
    db = await get_db()
    async with db.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,)) as cur:
        row = await cur.fetchone()
        return bool(row and row[0] == 1)

# ──────────────────────────────────────────────
#  Subscription
# ──────────────────────────────────────────────

async def get_subscription(user_id: int) -> Optional[int]:
    db = await get_db()
    async with db.execute('SELECT subscription_expiry FROM users WHERE user_id = ?', (user_id,)) as cur:
        row = await cur.fetchone()
        return row[0] if row else None

async def set_subscription(user_id: int, expiry: int):
    await execute_query('UPDATE users SET subscription_expiry = ? WHERE user_id = ?', (expiry, user_id), commit=True)

# ──────────────────────────────────────────────
#  Keys
# ──────────────────────────────────────────────

def generate_key(hours: int, created_by: int, max_uses: int = 1) -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=16))

async def save_key(key_code: str, hours: int, created_by: int, max_uses: int = 1):
    await execute_query(
        'INSERT OR IGNORE INTO keys (key_code, hours, max_uses, created_by) VALUES (?, ?, ?, ?)',
        (key_code, hours, max_uses, created_by), commit=True
    )

async def is_key_valid(key_code: str) -> Optional[int]:
    db = await get_db()
    async with db.execute(
        'SELECT hours, max_uses, used_count FROM keys WHERE key_code = ?',
        (key_code,)
    ) as cur:
        row = await cur.fetchone()
        if not row:
            return None
        hours, max_uses, used_count = row
        if used_count >= max_uses:
            return None
        return hours

async def mark_key_used(key_code: str):
    await execute_query('UPDATE keys SET used_count = used_count + 1 WHERE key_code = ?', (key_code,), commit=True)

async def get_key_uses_left(key_code: str) -> Optional[int]:
    db = await get_db()
    async with db.execute('SELECT max_uses, used_count FROM keys WHERE key_code = ?', (key_code,)) as cur:
        row = await cur.fetchone()
        if row:
            return row[0] - row[1]
        return None

# ──────────────────────────────────────────────
#  User Proxies
# ──────────────────────────────────────────────

async def count_user_proxies(user_id: int) -> int:
    db = await get_db()
    async with db.execute('SELECT COUNT(*) FROM user_proxies WHERE user_id = ?', (user_id,)) as cur:
        row = await cur.fetchone()
        return row[0] if row else 0

async def user_has_proxy(user_id: int, proxy: str) -> bool:
    db = await get_db()
    async with db.execute('SELECT 1 FROM user_proxies WHERE user_id = ? AND proxy = ?', (user_id, proxy)) as cur:
        return await cur.fetchone() is not None

async def add_user_proxy(user_id: int, proxy: str, speed: int = 0, country: str = "?"):
    await execute_query(
        'INSERT OR IGNORE INTO user_proxies (user_id, proxy, speed, country) VALUES (?, ?, ?, ?)',
        (user_id, proxy, speed, country), commit=True
    )

async def get_user_proxies_with_details(user_id: int) -> List[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        'SELECT proxy, speed, country FROM user_proxies WHERE user_id = ? ORDER BY speed ASC',
        (user_id,)
    ) as cur:
        rows = await cur.fetchall()
        return [{'proxy': r[0], 'speed': r[1], 'country': r[2]} for r in rows]

async def get_user_proxies(user_id: int) -> List[str]:
    db = await get_db()
    async with db.execute('SELECT proxy FROM user_proxies WHERE user_id = ?', (user_id,)) as cur:
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def delete_user_proxy(user_id: int, proxy: str):
    await execute_query('DELETE FROM user_proxies WHERE user_id = ? AND proxy = ?', (user_id, proxy), commit=True)

async def update_user_proxy_speed(user_id: int, proxy: str, speed: int, country: str):
    await execute_query(
        'UPDATE user_proxies SET speed = ?, country = ? WHERE user_id = ? AND proxy = ?',
        (speed, country, user_id, proxy), commit=True
    )

# ──────────────────────────────────────────────
#  Global Proxies
# ──────────────────────────────────────────────

async def global_has_proxy(proxy: str) -> bool:
    db = await get_db()
    async with db.execute('SELECT 1 FROM global_proxies WHERE proxy = ?', (proxy,)) as cur:
        return await cur.fetchone() is not None

async def add_global_proxy(proxy: str, speed: int = 0, country: str = "?"):
    await execute_query(
        'INSERT OR IGNORE INTO global_proxies (proxy, speed, country) VALUES (?, ?, ?)',
        (proxy, speed, country), commit=True
    )

async def delete_global_proxy(proxy: str):
    await execute_query('DELETE FROM global_proxies WHERE proxy = ?', (proxy,), commit=True)

async def get_all_global_proxies() -> List[str]:
    db = await get_db()
    async with db.execute('SELECT proxy FROM global_proxies') as cur:
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def update_global_proxy_speed(proxy: str, speed: int, country: str):
    await execute_query(
        'UPDATE global_proxies SET speed = ?, country = ? WHERE proxy = ?',
        (speed, country, proxy), commit=True
    )

async def count_global_proxies() -> int:
    db = await get_db()
    async with db.execute('SELECT COUNT(*) FROM global_proxies') as cur:
        row = await cur.fetchone()
        return row[0] if row else 0

async def count_global_proxies_alive() -> int:
    return await count_global_proxies()

async def count_global_proxies_added_since(timestamp: float) -> int:
    db = await get_db()
    async with db.execute(
        'SELECT COUNT(*) FROM global_proxies WHERE added_at >= ?',
        (int(timestamp),)
    ) as cur:
        row = await cur.fetchone()
        return row[0] if row else 0

# ──────────────────────────────────────────────
#  BIN Cache
# ──────────────────────────────────────────────

async def save_bin_lookup(bin_code: str, data: Dict[str, Any]):
    await execute_query(
        'INSERT OR REPLACE INTO bin_cache (bin_code, data) VALUES (?, ?)',
        (bin_code, json.dumps(data)), commit=True
    )

async def get_bin_lookup_cache(bin_code: str) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute('SELECT data FROM bin_cache WHERE bin_code = ?', (bin_code,)) as cur:
        row = await cur.fetchone()
        if row:
            return json.loads(row[0])
        return None

# ──────────────────────────────────────────────
#  Check Results
# ──────────────────────────────────────────────

async def save_check_result(user_id: int, card: str, status: str, response: str, price: float, elapsed: float, gateway: str, proxy: str = ""):
    await execute_query(
        'INSERT INTO check_results (user_id, card, status, response, price, elapsed, gateway, proxy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (user_id, card, status, response, price, elapsed, gateway, proxy), commit=True
    )

# ──────────────────────────────────────────────
#  Broadcasts
# ──────────────────────────────────────────────

async def get_all_group_chats() -> List[int]:
    return []

async def save_broadcast(user_id: int, caption: str, photo_id: str, status: str):
    await execute_query(
        'INSERT INTO broadcasts (user_id, caption, photo_id, status) VALUES (?, ?, ?, ?)',
        (user_id, caption, photo_id, status), commit=True
    )

async def get_broadcast_status(broadcast_id: int) -> Optional[str]:
    db = await get_db()
    async with db.execute('SELECT status FROM broadcasts WHERE id = ?', (broadcast_id,)) as cur:
        row = await cur.fetchone()
        return row[0] if row else None

# ──────────────────────────────────────────────
#  User Cards
# ──────────────────────────────────────────────

async def save_cards(user_id: int, cards: List[str]):
    db = await get_db()
    for card in cards:
        await db.execute(
            'INSERT OR IGNORE INTO user_cards (user_id, card) VALUES (?, ?)',
            (user_id, card)
        )
    await db.commit()

async def get_user_cards(user_id: int) -> List[str]:
    db = await get_db()
    async with db.execute('SELECT card FROM user_cards WHERE user_id = ?', (user_id,)) as cur:
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def delete_card(card_id: int):
    await execute_query('DELETE FROM user_cards WHERE id = ?', (card_id,), commit=True)

# ──────────────────────────────────────────────
#  Gateways (sites/services)
# ──────────────────────────────────────────────

async def add_gateway(name: str, site: str, added_by: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        'INSERT INTO gateways (name, site, added_by) VALUES (?, ?, ?)',
        (name, site, added_by)
    )
    await db.commit()
    return cursor.lastrowid

async def get_gateways(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        'SELECT id, name, site, added_by, added_at, status, last_check, speed FROM gateways ORDER BY id LIMIT ? OFFSET ?',
        (limit, offset)
    ) as cur:
        rows = await cur.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "site": r[2],
                "added_by": r[3],
                "added_at": r[4],
                "status": r[5] or "unknown",
                "last_check": r[6],
                "speed": r[7] or 0
            }
            for r in rows
        ]

async def get_gateway(gateway_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        'SELECT id, name, site, added_by, added_at, status, last_check, speed FROM gateways WHERE id = ?',
        (gateway_id,)
    ) as cur:
        row = await cur.fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "site": row[2],
                "added_by": row[3],
                "added_at": row[4],
                "status": row[5] or "unknown",
                "last_check": row[6],
                "speed": row[7] or 0
            }
        return None

async def update_gateway_status(gateway_id: int, status: str, speed: float = 0):
    await execute_query(
        'UPDATE gateways SET status = ?, last_check = strftime("%s", "now"), speed = ? WHERE id = ?',
        (status, speed, gateway_id), commit=True
    )

async def count_gateways() -> int:
    db = await get_db()
    async with db.execute('SELECT COUNT(*) FROM gateways') as cur:
        row = await cur.fetchone()
        return row[0] if row else 0

async def delete_gateway(gateway_id: int):
    await execute_query('DELETE FROM gateways WHERE id = ?', (gateway_id,), commit=True)

async def delete_dead_gateways() -> int:
    """حذف جميع البوابات الميتة دفعة واحدة. يرجع عدد المحذوفات."""
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM gateways WHERE status = 'dead'") as cur:
        row = await cur.fetchone()
        count = row[0] if row else 0
    if count:
        await db.execute("DELETE FROM gateways WHERE status = 'dead'")
        await db.commit()
    return count

async def reorder_gateways():
    """إعادة ترقيم جميع البوابات بشكل متسلسل ابتداءً من 1."""
    db = await get_db()
    async with db.execute(
        'SELECT name, site, added_by, added_at, status, last_check, speed FROM gateways ORDER BY id'
    ) as cur:
        rows = await cur.fetchall()

    await db.execute('DROP TABLE IF EXISTS _gateways_tmp')
    await db.execute('ALTER TABLE gateways RENAME TO _gateways_tmp')
    await db.execute('''
        CREATE TABLE gateways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            site TEXT NOT NULL,
            added_by INTEGER,
            added_at INTEGER DEFAULT (strftime('%s', 'now')),
            status TEXT DEFAULT 'unknown',
            last_check INTEGER DEFAULT 0,
            speed INTEGER DEFAULT 0
        )
    ''')
    for row in rows:
        await db.execute(
            'INSERT INTO gateways (name, site, added_by, added_at, status, last_check, speed) VALUES (?, ?, ?, ?, ?, ?, ?)',
            row
        )
    await db.execute('DROP TABLE _gateways_tmp')
    await db.commit()

# ──────────────────────────────────────────────
#  APIs (endpoints)
# ──────────────────────────────────────────────

async def add_api(api_url: str, added_by: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        'INSERT INTO apis (api_url, added_by) VALUES (?, ?)',
        (api_url, added_by)
    )
    await db.commit()
    return cursor.lastrowid

async def get_apis(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        'SELECT id, api_url, added_by, added_at, status, last_check, speed FROM apis ORDER BY id LIMIT ? OFFSET ?',
        (limit, offset)
    ) as cur:
        rows = await cur.fetchall()
        return [
            {
                "id": r[0],
                "api_url": r[1],
                "added_by": r[2],
                "added_at": r[3],
                "status": r[4] or "unknown",
                "last_check": r[5],
                "speed": r[6] or 0
            }
            for r in rows
        ]

async def get_api(api_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        'SELECT id, api_url, added_by, added_at, status, last_check, speed FROM apis WHERE id = ?',
        (api_id,)
    ) as cur:
        row = await cur.fetchone()
        if row:
            return {
                "id": row[0],
                "api_url": row[1],
                "added_by": row[2],
                "added_at": row[3],
                "status": row[4] or "unknown",
                "last_check": row[5],
                "speed": row[6] or 0
            }
        return None

async def update_api_status(api_id: int, status: str, speed: float = 0):
    await execute_query(
        'UPDATE apis SET status = ?, last_check = strftime("%s", "now"), speed = ? WHERE id = ?',
        (status, speed, api_id), commit=True
    )

async def count_apis() -> int:
    db = await get_db()
    async with db.execute('SELECT COUNT(*) FROM apis') as cur:
        row = await cur.fetchone()
        return row[0] if row else 0

async def delete_api(api_id: int):
    await execute_query('DELETE FROM apis WHERE id = ?', (api_id,), commit=True)
# ──────────────────────────────────────────────
#  PayPal Gateways
# ──────────────────────────────────────────────

async def add_pp_gateway(site: str, added_by: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        'INSERT OR IGNORE INTO paypal_gateways (site, added_by) VALUES (?, ?)',
        (site, added_by)
    )
    await db.commit()
    return cursor.lastrowid

async def get_pp_gateways(limit: int = 200) -> List[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        'SELECT id, site, added_by, added_at, status, speed FROM paypal_gateways ORDER BY id LIMIT ?',
        (limit,)
    ) as cur:
        rows = await cur.fetchall()
        return [{"id": r[0], "site": r[1], "added_by": r[2],
                 "added_at": r[3], "status": r[4], "speed": r[5]} for r in rows]

async def get_pp_gateway(gid: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        'SELECT id, site, added_by, added_at, status, speed FROM paypal_gateways WHERE id = ?',
        (gid,)
    ) as cur:
        row = await cur.fetchone()
        if row:
            return {"id": row[0], "site": row[1], "added_by": row[2],
                    "added_at": row[3], "status": row[4], "speed": row[5]}
        return None

async def count_pp_gateways() -> int:
    db = await get_db()
    async with db.execute('SELECT COUNT(*) FROM paypal_gateways') as cur:
        row = await cur.fetchone()
        return row[0] if row else 0

async def delete_pp_gateway(gid: int):
    await execute_query('DELETE FROM paypal_gateways WHERE id = ?', (gid,), commit=True)

async def delete_dead_pp_gateways() -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM paypal_gateways WHERE status = 'dead'") as cur:
        row = await cur.fetchone()
        count = row[0] if row else 0
    if count:
        await db.execute("DELETE FROM paypal_gateways WHERE status = 'dead'")
        await db.commit()
    return count

async def update_pp_gateway_status(gid: int, status: str, speed: float = 0):
    await execute_query(
        'UPDATE paypal_gateways SET status = ?, speed = ? WHERE id = ?',
        (status, speed, gid), commit=True
    )

async def reorder_pp_gateways():
    db = await get_db()
    async with db.execute(
        'SELECT site, added_by, added_at, status, speed FROM paypal_gateways ORDER BY id'
    ) as cur:
        rows = await cur.fetchall()
    await db.execute('DROP TABLE IF EXISTS _pp_gw_tmp')
    await db.execute('ALTER TABLE paypal_gateways RENAME TO _pp_gw_tmp')
    await db.execute('''
        CREATE TABLE paypal_gateways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT NOT NULL UNIQUE,
            added_by INTEGER,
            added_at INTEGER DEFAULT (strftime('%s', 'now')),
            status TEXT DEFAULT 'unknown',
            speed INTEGER DEFAULT 0
        )
    ''')
    for row in rows:
        await db.execute(
            'INSERT INTO paypal_gateways (site, added_by, added_at, status, speed) VALUES (?, ?, ?, ?, ?)',
            row
        )
    await db.execute('DROP TABLE _pp_gw_tmp')
    await db.commit()

# ──────────────────────────────────────────────
#  PP User Price
# ──────────────────────────────────────────────

async def get_pp_gateway_price(user_id: int) -> float:
    db = await get_db()
    async with db.execute('SELECT price FROM pp_user_price WHERE user_id = ?', (user_id,)) as cur:
        row = await cur.fetchone()
        return row[0] if row else 1.0

async def set_pp_gateway_price(user_id: int, price: float):
    await execute_query(
        'INSERT OR REPLACE INTO pp_user_price (user_id, price) VALUES (?, ?)',
        (user_id, price), commit=True
    )

# ──────────────────────────────────────────────
#  Global Hit Counter (مشترك لجميع البوابات)
# ──────────────────────────────────────────────

async def get_global_hit_count() -> int:
    db = await get_db()
    async with db.execute('SELECT total FROM global_hits WHERE id = 1') as cur:
        row = await cur.fetchone()
        return row[0] if row else 5840

async def increment_global_hit() -> int:
    db = await get_db()
    await db.execute('UPDATE global_hits SET total = total + 1 WHERE id = 1')
    await db.commit()
    async with db.execute('SELECT total FROM global_hits WHERE id = 1') as cur:
        row = await cur.fetchone()
        return row[0] if row else 5840
