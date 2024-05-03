import re
import secrets
import json
import requests
from datetime import datetime
from decouple import config

ishare_map = {
    2: 50,
    4: 52,
    7: 2000,
    10: 3000,
    12: 4000,
    15: 5000,
    18: 6000,
    22: 7000,
    25: 8000,
    30: 10000,
    45: 15000,
    60: 20000,
    75: 25000,
    90: 30000,
    120: 40000,
    145: 50000,
    285: 100000,
    560: 200000
}


def ref_generator():
    now_time = datetime.now().strftime('%H%M%S')
    secret = secrets.token_hex(2)

    return f"{now_time}{secret}".upper()


def top_up_ref_generator():
    now_time = datetime.now().strftime('%H%M')
    secret = secrets.token_hex(1)

    return f"TOPUP-{now_time}{secret}".upper()


def send_bundle(receiver, bundle_amount, reference):
    url = "https://controller.geosams.com/api/v1/new_transaction"
    print(receiver, bundle_amount, reference)

    payload = json.dumps({
        "account_number": receiver,
        "reference": reference,
        "bundle_amount": bundle_amount
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': config("BEARER_TOKEN")
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)
    return response




