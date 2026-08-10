#!/usr/bin/env python3
"""Check rodentpro.com item prices against target prices and notify on drops."""

import html
import json
import logging
import os
import re
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
ITEMS_PATH = BASE_DIR / "items.json"
SECRETS_PATH = BASE_DIR / "secrets.json"
LOG_PATH = BASE_DIR / "logs" / "price_tracker.log"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
LD_JSON_RE = re.compile(
    r'<script type="application/ld[^"]*">(.*?)</script>', re.S
)

logger = logging.getLogger("price_tracker")


def setup_logging():
    logger.setLevel(logging.INFO)
    LOG_PATH.parent.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(LOG_PATH)
    stream_handler = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(fmt)
    stream_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def fetch_price(url):
    """Return (name, price) for a rodentpro.com product page."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=15) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    match = LD_JSON_RE.search(page)
    if not match:
        raise ValueError("no ld+json block found on page")

    data = json.loads(html.unescape(match.group(1)))
    nodes = data.get("@graph", [data]) if isinstance(data, dict) else data

    for node in nodes:
        if node.get("@type") == "Product":
            return node["name"], float(node["offers"]["price"])

    raise ValueError("no Product node found in ld+json data")


def send_email(to_address, subject, body, secrets):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = secrets["gmail_address"]
    msg["To"] = to_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(secrets["gmail_address"], secrets["gmail_app_password"])
        server.send_message(msg)


def load_secrets():
    if SECRETS_PATH.exists():
        return json.loads(SECRETS_PATH.read_text())

    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not (gmail_address and gmail_app_password):
        return None

    return {
        "gmail_address": gmail_address,
        "gmail_app_password": gmail_app_password,
        "notify_email": os.environ.get("NOTIFY_EMAIL", gmail_address),
        "sms_gateway": os.environ.get("SMS_GATEWAY"),
    }


def main():
    setup_logging()
    items = json.loads(ITEMS_PATH.read_text())
    secrets = load_secrets()

    hits = []

    for item in items:
        try:
            name, price = fetch_price(item["url"])
            target = item["target_price"]
            if price <= target:
                logger.info(
                    "HIT  %s: $%.2f <= target $%.2f", name, price, target
                )
                hits.append((item["name"], price, target))
            else:
                logger.info(
                    "     %s: $%.2f > target $%.2f", name, price, target
                )
        except Exception as exc:
            logger.error("FAIL %s (%s): %s", item["name"], item["url"], exc)

    if hits:
        lines = [
            f"{name}: ${price:.2f} (target ${target:.2f})"
            for name, price, target in hits
        ]
        title = "RodentPro price drop!"
        body = "\n".join(lines)
        if secrets:
            try:
                send_email(secrets["notify_email"], title, body, secrets)
            except Exception as exc:
                logger.error("Failed to send email: %s", exc)

            sms_gateway = secrets.get("sms_gateway")
            if sms_gateway:
                sms_body = "; ".join(
                    f"{name} ${price:.2f}" for name, price, target in hits
                )
                try:
                    send_email(sms_gateway, title, sms_body, secrets)
                except Exception as exc:
                    logger.error("Failed to send SMS: %s", exc)
        else:
            logger.warning("secrets.json not found, skipping email/SMS notification")


if __name__ == "__main__":
    main()
