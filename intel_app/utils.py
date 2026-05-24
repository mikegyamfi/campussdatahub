import re


def parse_momo_sms(sms_body):
    if not sms_body:
        return None, 0.0

    sms_body = sms_body.strip()

    amount_pattern = r"^(?:Payment received for|You have received)\s*(?:GHS|GHC)\s*(\d+\.?\d*)"
    amount_match = re.search(amount_pattern, sms_body, re.IGNORECASE)
    amount = float(amount_match.group(1)) if amount_match else 0.0

    id_pattern = (
        r"(?:Transaction ID|Financial Transaction Id):\s*(\d+)\.?\s*"
        r"(?:TRANSACTION FEE|Fee charged|TRANSACTION FEE IS)"
    )
    id_matches = re.findall(id_pattern, sms_body, re.IGNORECASE)
    txn_id = id_matches[-1] if id_matches else None

    return txn_id, amount
