"""Setup Facebook Messenger Webhook via Graph API (no UI needed).

Usage:
    python scripts/setup_webhook.py --ngrok-url https://abc123.ngrok-free.app
    python scripts/setup_webhook.py --status

Requires in .env:
    FACEBOOK_APP_ID, FACEBOOK_PAGE_ID, APP_SECRET, PAGE_ACCESS_TOKEN, VERIFY_TOKEN
"""

import argparse
import os
import sys
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

APP_ID            = os.getenv("FACEBOOK_APP_ID", "")
APP_SECRET        = os.getenv("APP_SECRET", "")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN", "")
PAGE_ID           = os.getenv("FACEBOOK_PAGE_ID", "")
SERVER_URL        = os.getenv("SERVER_URL", "").rstrip("/")

GRAPH = "https://graph.facebook.com/v21.0"
SUBSCRIBE_FIELDS = "messages,messaging_postbacks,messaging_optins"


def get_app_token() -> str:
    r = httpx.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=15,
    )
    data = r.json()
    if "access_token" not in data:
        print(f"[ERROR] Cannot get app token: {data}")
        sys.exit(1)
    return data["access_token"]


def get_page_id() -> str:
    if PAGE_ID:
        print(f"[INFO] Using Page ID from .env: {PAGE_ID}")
        return PAGE_ID
    r = httpx.get(
        f"{GRAPH}/me",
        params={"access_token": PAGE_ACCESS_TOKEN, "fields": "id,name"},
        timeout=15,
    )
    data = r.json()
    if "id" not in data:
        err = data.get("error", {}).get("message", str(data))
        print(f"[ERROR] Cannot get Page ID automatically: {err}")
        print("[HINT] Add FACEBOOK_PAGE_ID=<your page id> to .env and retry")
        print("       Find it: Facebook Page -> About -> Page ID")
        sys.exit(1)
    print(f"[INFO] Page: {data.get('name')} (ID: {data['id']})")
    return data["id"]


def register_webhook(app_token: str, callback_url: str) -> None:
    print(f"[INFO] Registering webhook: {callback_url}/webhook ...")
    r = httpx.post(
        f"{GRAPH}/{APP_ID}/subscriptions",
        data={
            "object": "page",
            "callback_url": f"{callback_url}/webhook",
            "fields": SUBSCRIBE_FIELDS,
            "verify_token": VERIFY_TOKEN,
            "access_token": app_token,
        },
        timeout=20,
    )
    data = r.json()
    if data.get("success"):
        print("[OK] Webhook registered!")
    else:
        print(f"[ERROR] Webhook registration failed: {data}")
        sys.exit(1)


def subscribe_page(page_id: str) -> None:
    print(f"[INFO] Subscribing Page {page_id} to App ...")
    r = httpx.post(
        f"{GRAPH}/{page_id}/subscribed_apps",
        data={
            "subscribed_fields": SUBSCRIBE_FIELDS,
            "access_token": PAGE_ACCESS_TOKEN,
        },
        timeout=15,
    )
    data = r.json()
    if data.get("success"):
        print("[OK] Page subscribed!")
    else:
        err = data.get("error", {}).get("message", str(data))
        print(f"[WARN] Page subscribe skipped (likely already connected): {err[:120]}")


def check_status(app_token: str) -> None:
    r = httpx.get(
        f"{GRAPH}/{APP_ID}/subscriptions",
        params={"access_token": app_token},
        timeout=15,
    )
    data = r.json()
    subs = data.get("data", [])
    if not subs:
        print("[INFO] No webhooks registered yet.")
        return
    for sub in subs:
        print(f"[INFO] Object : {sub.get('object')}")
        print(f"       URL    : {sub.get('callback_url')}")
        print(f"       Active : {sub.get('active')}")
        print(f"       Fields : {sub.get('fields', [])}")


def main():
    parser = argparse.ArgumentParser(description="Setup Facebook Messenger Webhook")
    parser.add_argument("--ngrok-url", help="Server base URL (e.g. https://abc.ngrok-free.app)")
    parser.add_argument("--status", action="store_true", help="Check current webhook status only")
    args = parser.parse_args()

    missing = [v for v in ["FACEBOOK_APP_ID", "APP_SECRET", "PAGE_ACCESS_TOKEN", "VERIFY_TOKEN"] if not os.getenv(v)]
    if missing:
        print(f"[ERROR] Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    app_token = get_app_token()

    if args.status:
        check_status(app_token)
        return

    callback = (args.ngrok_url or SERVER_URL).rstrip("/")
    if not callback:
        parser.print_help()
        print("\n[ERROR] Provide --ngrok-url or set SERVER_URL in .env")
        sys.exit(1)
    page_id = get_page_id()
    register_webhook(app_token, callback)
    subscribe_page(page_id)

    print(f"\n[DONE] Webhook configured: {callback}/webhook")
    print(f"       Verify token: {VERIFY_TOKEN}")


if __name__ == "__main__":
    main()
