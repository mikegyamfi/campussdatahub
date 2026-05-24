import logging

import requests
from decouple import config

logger = logging.getLogger(__name__)

BASE_URL = "https://www.geosams.com"
GEOSAMS_TOKEN = config("GEOSAMS_TOKEN", default=None)

NETWORK_MTN = "MTN"
NETWORK_TELECEL = "Telecel"
NETWORK_AT = "AT"


def is_configured():
    return bool(GEOSAMS_TOKEN)


def _headers():
    return {
        "Authorization": f"Token {GEOSAMS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


class GeosamsResult:
    __slots__ = ("kind", "message", "metadata", "code")

    def __init__(self, kind, message="", metadata=None, code=None):
        self.kind = kind
        self.message = message
        self.metadata = metadata
        self.code = code

    @property
    def accepted(self):
        return self.kind in ("accepted", "duplicate")

    @property
    def retryable(self):
        return self.kind == "retryable"

    @property
    def rejected(self):
        return self.kind == "rejected"

    def __repr__(self):
        return f"GeosamsResult(kind={self.kind!r}, code={self.code!r}, message={self.message!r})"


def send_bundle(phone_number, amount_mb, network, reference, timeout=30):
    if not is_configured():
        logger.warning("GEOSAMS_TOKEN not configured; treating send_bundle as retryable")
        return GeosamsResult("retryable", message="GEOSAMS_TOKEN not configured")

    payload = {
        "phone_number": str(phone_number),
        "amount": int(amount_mb),
        "network": network,
        "reference": reference,
    }

    try:
        r = requests.post(
            f"{BASE_URL}/controller/api/send_bundle/",
            headers=_headers(),
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as e:
        logger.warning("Geosams send_bundle network error for %s: %s", reference, e)
        return GeosamsResult("retryable", message=str(e))

    if r.status_code in (401, 403):
        logger.error("Geosams auth failure (%d): %s", r.status_code, r.text[:200])
        return GeosamsResult("rejected", message="Auth failed", code=str(r.status_code))
    if r.status_code >= 500:
        return GeosamsResult("retryable", message=r.text[:200], code=str(r.status_code))

    try:
        body = r.json()
    except ValueError:
        return GeosamsResult("retryable", message="non-json response", code=str(r.status_code))

    code = str(body.get("code", ""))
    msg = body.get("message", "")
    meta = body.get("metadata")

    if code == "200":
        return GeosamsResult("accepted", message=msg, metadata=meta, code=code)
    if code == "409":
        return GeosamsResult("duplicate", message=msg, code=code)
    if code == "500":
        return GeosamsResult("retryable", message=msg, code=code)
    return GeosamsResult("rejected", message=msg or "rejected", code=code)


def get_detail(reference, timeout=15):
    if not is_configured():
        return None
    try:
        r = requests.get(
            f"{BASE_URL}/controller/api/transaction_detail/{reference}/",
            headers=_headers(),
            timeout=timeout,
        )
    except requests.RequestException as e:
        logger.warning("Geosams get_detail network error for %s: %s", reference, e)
        return None
    if r.status_code == 404:
        return None
    if not r.ok:
        logger.warning("Geosams get_detail returned %d for %s", r.status_code, reference)
        return None
    try:
        return r.json()
    except ValueError:
        return None
