#!/usr/bin/env python3
"""iPhone Duo in-store pickup tracker. Alerts your phone via the ntfy app."""
import os
import random
import time
import requests

PART = "MK1E4LL/A"             # iPhone Duo 256GB Star White, US
LOCATION = "07302"             # Jersey City; also searches nearby NYC/NJ stores
NTFY_TOPIC = os.environ["NTFY_TOPIC"] # subscribe to this exact name in the ntfy app
POLL_SECONDS = 40
MAX_STORES = 12

API = "https://www.apple.com/shop/retail/pickup-message"
NTFY = f"https://ntfy.sh/{NTFY_TOPIC}"
BUY_URL = "https://www.apple.com/shop/buy-iphone/iphone-duo"
IN_CLOUD = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("GITHUB_ACTIONS"))
WHERE = " (cloud)" if IN_CLOUD else " (Mac)"
# GitHub runs repeat every few hours; only announce on a manual start
ANNOUNCE = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") == "workflow_dispatch"
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "0"))  # 0 = run forever

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "application/json",
    "Referer": BUY_URL,
}


def notify(title, msg, priority="urgent"):
    try:
        requests.post(NTFY, data=msg.encode("utf-8"),
                      headers={"Title": title, "Priority": priority,
                               "Tags": "iphone,rotating_light", "Click": BUY_URL},
                      timeout=10)
    except requests.RequestException as e:
        print(f"  (phone alert failed: {e})")


def fetch():
    params = {"pl": "true", "parts.0": PART, "location": LOCATION}
    r = requests.get(API, params=params, headers=HEADERS, timeout=15)
    if r.status_code in (403, 429, 503):
        raise RuntimeError(f"Apple is slowing us down (HTTP {r.status_code})")
    r.raise_for_status()
    return r.json()["body"]["stores"][:MAX_STORES]


def main():
    print("Starting iPhone Duo tracker...\n")
    try:
        stores = fetch()
    except Exception as e:
        notify("Duo tracker problem" + WHERE, f"Couldn't reach Apple: {e}", priority="high")
        raise
    if not stores or PART not in stores[0].get("partsAvailability", {}):
        raise SystemExit("Apple didn't recognize the part number.")
    title = (stores[0]["partsAvailability"][PART].get("messageTypes", {})
             .get("regular", {}).get("storePickupProductTitle", "(unknown)"))
    print(f"Watching for: {title}")
    print("Stores: " + ", ".join(s["storeName"] for s in stores) + "\n")
    if ANNOUNCE:
        notify("Duo tracker is running" + WHERE, f"Watching for {title}. You'll get a loud alert when it's in stock.",
               priority="default")

    alerted, backoff = set(), 0
    started = time.time()
    while not MAX_MINUTES or time.time() - started < MAX_MINUTES * 60:
        try:
            stores = fetch()
            backoff = 0
            available = set()
            for s in stores:
                info = s["partsAvailability"].get(PART, {})
                if info.get("pickupDisplay") == "available":
                    name = s["storeName"]
                    available.add(name)
                    if name not in alerted:
                        msg = f"In stock at Apple {name}! Open the Apple Store app and order for pickup NOW."
                        print(f"[{time.strftime('%I:%M %p')}] *** {msg}")
                        notify("iPhone Duo IN STOCK", msg)
            alerted = available
            if not available:
                print(f"[{time.strftime('%I:%M %p')}] checked - none nearby yet")
        except Exception as e:
            backoff = min(backoff + 1, 3)
            print(f"[{time.strftime('%I:%M %p')}] problem: {e} - waiting a bit")
            time.sleep(60 * backoff)
        time.sleep(POLL_SECONDS + random.randint(5, 15))


if __name__ == "__main__":
    main()
