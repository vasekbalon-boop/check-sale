"""
Serverless variant of the BG3 sale watcher — runs once and exits.
Designed for GitHub Actions cron (or any cron: systemd timer, NAS task scheduler).

No dependencies: standard library only.

Environment variables:
    DISCORD_WEBHOOK_URL   (required) channel webhook from Discord > Integrations
    TARGET_USER_ID        (required) numeric ID of the user to ping
    STEAM_APP_ID          default 1086940 (Baldur's Gate 3)
    STEAM_CC              default "cz"
    MIN_DISCOUNT          default 20
    STATE_FILE            default state.json
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
USER_ID = os.environ["TARGET_USER_ID"]
APP_ID = os.getenv("STEAM_APP_ID", "1086940")
COUNTRY = os.getenv("STEAM_CC", "cz")
MIN_DISCOUNT = int(os.getenv("MIN_DISCOUNT", "20"))
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))

UA = {"User-Agent": "bg3-sale-watcher/1.0"}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def steam_lookup() -> tuple[str, dict | None]:
    """Return (name, price_overview | None)."""
    url = (
        f"https://store.steampowered.com/api/appdetails"
        f"?appids={APP_ID}&cc={COUNTRY}&filters=price_overview,basic"
    )
    entry = get_json(url).get(APP_ID) or {}
    if not entry.get("success"):
        raise RuntimeError(f"Steam returned success=false for app {APP_ID}")
    data = entry.get("data") or {}
    return data.get("name", f"App {APP_ID}"), data.get("price_overview")


def post_to_discord(payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK, data=body, headers={**UA, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Discord webhook returned {resp.status}")


def main() -> int:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    announced = int(state.get("announced_discount", 0))

    try:
        name, price = steam_lookup()
    except (urllib.error.URLError, RuntimeError, ValueError) as exc:
        print(f"::warning::Steam lookup failed: {exc}")
        return 0  # don't fail the workflow over a transient hiccup

    state["last_check"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not price:
        print("No price data (free / region-locked / delisted?)")
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return 0

    discount = int(price.get("discount_percent", 0))
    final = price.get("final_formatted", "?")
    initial = price.get("initial_formatted") or final
    state["last_discount"] = discount
    print(f"{name}: -{discount}% -> {final} (last announced {announced}%)")

    should_notify = discount >= MIN_DISCOUNT and discount > announced

    if discount < MIN_DISCOUNT:
        state["announced_discount"] = 0
    elif should_notify:
        post_to_discord(
            {
                "content": f"<@{USER_ID}>",
                "allowed_mentions": {"users": [USER_ID]},
                "embeds": [
                    {
                        "title": f"🔥 {name} — sleva {discount} %",
                        "url": f"https://store.steampowered.com/app/{APP_ID}/",
                        "description": f"**{final}**  ~~{initial}~~",
                        "color": 0xC1440E,
                        "thumbnail": {
                            "url": f"https://cdn.cloudflare.steamstatic.com/"
                            f"steam/apps/{APP_ID}/header.jpg"
                        },
                        "footer": {"text": f"Steam · region {COUNTRY.upper()}"},
                    }
                ],
            }
        )
        state["announced_discount"] = discount
        print("Notification sent.")

    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
