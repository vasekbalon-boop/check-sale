"""
BG3 sale watcher — runs once and exits. Designed for GitHub Actions cron.
Now with escalating public shaming.

No dependencies: standard library only.

Environment variables:
    DISCORD_WEBHOOK_URL   (required) channel webhook from Discord > Integrations
    TARGET_USER_ID        (required) numeric ID of the user to ping
    STEAM_APP_ID          default 1086940 (Baldur's Gate 3)
    STEAM_CC              default "cz"
    MIN_DISCOUNT          default 20
    STATE_FILE            default state.json
    FORCE_NOTIFY          "1"/"true" -> send regardless of discount (test runs)
"""

import json
import os
import random
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
FORCE = os.getenv("FORCE_NOTIFY", "").strip().lower() in ("1", "true", "yes")

UA = {"User-Agent": "bg3-sale-watcher/1.0"}

# --------------------------------------------------------------------------- #
# The important part
# --------------------------------------------------------------------------- #
HOOKS = [
    "🚨 **TOHLE NENÍ CVIČNÝ POPLACH**",
    "🎲 Hoď si na záchranu proti prokrastinaci. Postihem je tvoje historie.",
    "📢 Slyšíš to? To je zvuk tvé peněženky, jak se pokouší utéct.",
    "⚔️ Iniciativa hozena. Jsi na řadě. Zase.",
    "🔔 Připomínka, kterou si sám nastavil a stejně ji ignoruješ.",
]

# Indexed by how many times we've already been through this.
SHAME = {
    1: [
        "Sleva je tady. Ty jsi tady. Co by se mohlo pokazit?",
        "První připomínka. Ještě máš čistý štít.",
    ],
    2: [
        "Podruhé. Minule jsi to taky viděl a pak jsi šel spát.",
        "Druhá připomínka. Statisticky vzato už to nekoupíš.",
    ],
    3: [
        "Potřetí. **POTŘETÍ.** Hodil sis přirozenou 1 už třikrát za sebou.",
        "Třetí pokus. I ten nejtrpělivější vypravěč by už protočil oči.",
    ],
}
SHAME_MANY = [
    "{n}. připomínka. V tomhle tempu to koupíš, až vyjde pokračování.",
    "Tohle je {n}. kolo. Bot má lepší docházku než ty.",
    "{n}× jsem tě upozornil. Začínám to brát osobně.",
    "Připomínka číslo {n}. Archeologové to jednou najdou a budou se divit.",
]

DEEP_CUT = [
    "A tohle je fakt hluboká sleva. Žádná další nepřijde.",
    "Levněji už to nebude. Vážně.",
    "Za tuhle cenu je to skoro krádež — a ty pořád váháš.",
]


def flavour(discount: int, count: int) -> str:
    lines = SHAME.get(count) or [random.choice(SHAME_MANY).format(n=count)]
    text = random.choice(lines)
    if discount >= 50:
        text += "\n\n" + random.choice(DEEP_CUT)
    return text


def colour_for(discount: int) -> int:
    if discount >= 60:
        return 0xFFD700  # gold
    if discount >= 40:
        return 0xE03131  # red
    if discount >= 20:
        return 0xF08C00  # orange
    return 0x868E96      # grey


def bar(discount: int) -> str:
    filled = round(discount / 10)
    return "🟥" * filled + "⬛" * (10 - filled)


# --------------------------------------------------------------------------- #
# Steam / Discord plumbing
# --------------------------------------------------------------------------- #
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


def build_payload(name: str, price: dict, discount: int, count: int) -> dict:
    final = price.get("final_formatted", "?")
    initial = price.get("initial_formatted") or final
    currency = price.get("currency", "")
    saved = (price.get("initial", 0) - price.get("final", 0)) / 100
    store = f"https://store.steampowered.com/app/{APP_ID}/"

    return {
        "content": f"<@{USER_ID}>  {random.choice(HOOKS)}",
        "allowed_mentions": {"users": [USER_ID]},
        "embeds": [
            {
                "author": {"name": "Hlídač slev · hlídá líp než ty"},
                "title": f"🔥 {name} — SLEVA {discount} %",
                "url": store,
                "description": (
                    f"{bar(discount)}\n\n"
                    f"# {final}\n"
                    f"~~{initial}~~\n\n"
                    f"{flavour(discount, count)}"
                ),
                "color": colour_for(discount),
                "fields": [
                    {
                        "name": "💰 Ušetříš",
                        "value": f"**{saved:,.0f} {currency}**".replace(",", " "),
                        "inline": True,
                    },
                    {
                        "name": "📉 Sleva",
                        "value": f"**−{discount} %**",
                        "inline": True,
                    },
                    {
                        "name": "🤦 Kolikátá připomínka",
                        "value": f"**{count}.**",
                        "inline": True,
                    },
                    {
                        "name": "\u200b",
                        "value": f"### [👉 KOUPIT TEĎ, NE ZÍTRA 👈]({store})",
                        "inline": False,
                    },
                ],
                # header.jpg always exists. For an even bigger banner try:
                # .../steam/apps/{APP_ID}/library_hero.jpg
                "image": {
                    "url": f"https://cdn.cloudflare.steamstatic.com/"
                    f"steam/apps/{APP_ID}/header.jpg"
                },
                "footer": {
                    "text": f"Steam · region {COUNTRY.upper()} · "
                    f"další kontrola za 6 hodin, jestli to zas nekoupíš"
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    announced = int(state.get("announced_discount", 0))
    count = int(state.get("reminder_count", 0))

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
    state["last_discount"] = discount
    print(f"{name}: -{discount}% (last announced {announced}%, reminder #{count})")

    if FORCE:
        print("FORCE_NOTIFY set — sending regardless of discount.")

    if FORCE or (discount >= MIN_DISCOUNT and discount > announced):
        shown = count if FORCE else count + 1
        post_to_discord(build_payload(name, price, discount, shown))
        if not FORCE:
            state["announced_discount"] = discount
            state["reminder_count"] = shown
        print("Notification sent.")
    elif discount < MIN_DISCOUNT:
        state["announced_discount"] = 0

    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
