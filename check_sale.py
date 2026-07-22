"""
BG3 sale watcher — runs once and exits. Designed for GitHub Actions cron.
Epický vypravěč, který se rozpadne do urážek. Standardní knihovna, žádné závislosti.

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
SYMBOLS = {"EUR": "€", "CZK": "Kč", "USD": "$", "GBP": "£", "PLN": "zł"}

# ═══════════════════════════════════════════════════════════════════════════ #
#  OBSAH. Tady si hraj, logika je níž a nezajímá tě.
# ═══════════════════════════════════════════════════════════════════════════ #

# Řádek s pingem nad embedem.
HOOKS = [
    "🫵 **TY.** Ano, ty.",
    "🚨 **BRATŘE.** Zase.",
    "⚡ Tohle není cvičení.",
    "🧠 Detekován nákupní impuls. Nezahoď ho jako posledně.",
    "📉 Tvůj wishlist ti posílá pozdrav. Zní zklamaně.",
    "🔔 Připomínka, kterou sis sám naprogramoval a stejně ji ignoruješ.",
]

# Patetický vypravěč. Malým písmem nahoře, ať to má grády.
NARRATION = [
    "Kdysi dávno, v zemi zvané Steam, se zjevila sleva.",
    "Toto je příběh muže, který měl hru v košíku. Měsíce.",
    "V dobách, kdy peněženky ještě něco znamenaly, přišel tento okamžik.",
    "Osud tká svou nit. Nit je tentokrát ve slevě.",
    "Legendy praví, že jednou klikne. Legendy se pletou.",
    "Hrdina stál před branou. Brána byla platební.",
]

# Eskalace podle toho, pokolikáté už tohle absolvujeme.
SHAME = {
    1: [
        "Sleva je tady. Ty jsi tady. Zbývá jen ta nejtěžší část — kliknout.",
        "První připomínka. Zatím čistý štít. Zatím.",
    ],
    2: [
        "Podruhé. Minule jsi říkal *až o víkendu*. Víkend byl. Dvakrát.",
        "Druhé kolo. Statistika ti nefandí.",
    ],
    3: [
        "**POTŘETÍ.** Tvoje odhodlání má stabilitu wi-fi na chalupě.",
        "Třetí pokus. I ten nejtrpělivější vypravěč by teď protočil oči.",
    ],
}
SHAME_MANY = [
    "Připomínka č. {n}. Bratr si fakt myslí, že sleva počká.",
    "Pokus číslo {n}. Aura: −{n}000.",
    "Už {n}. kolo. Tohle už není hlídač slev, tohle je terapie.",
    "Ignorováno {n}×. Pomalu z toho je rodinná tradice.",
    "Připomínka č. {n}. Larian mezitím stihl vydat další patch. Ty nic.",
    "Kolo {n}. Vypravěč to vzdal. Píše to teď za něj stážista.",
]

DEEP_CUT = [
    "A tohle je fakt hluboká sleva. Levněji už to nebude.",
    "Za tuhle cenu je to skoro trestný čin. Skoro.",
    "Tohle je ta chvíle. Jiná nepřijde. Ne. Nepřijde.",
]

CTA = [
    "KOUPIT TEĎ, NE ZÍTRA",
    "KLIKNI, ZBABĚLČE",
    "TENTOKRÁT TO DOTÁHNI",
    "JEDNO KLIKNUTÍ. JEDNO.",
]

FOOTERS = [
    "další kontrola za 6 h · uvidíme, jak dopadneš",
    "tenhle bot má lepší docházku než ty",
    "napsal sis mě sám · tohle je celé tvoje vina",
    "hlídám i v noci · na rozdíl od tvého sebeovládání",
]

AUTHORS = [
    "Hlídač slev · hlídá líp než ty",
    "Tvoje svědomí (automatizované)",
    "Oddělení nedokončených nákupů",
    "Úžasná pouť do košíku",
]


def flavour(discount: int, count: int) -> str:
    lines = SHAME.get(count) or [random.choice(SHAME_MANY).format(n=count)]
    text = random.choice(lines)
    if discount >= 50:
        text += " " + random.choice(DEEP_CUT)
    return text


def colour_for(discount: int) -> int:
    if discount >= 60:
        return 0xFFD700  # zlatá
    if discount >= 40:
        return 0xE03131  # červená
    if discount >= 20:
        return 0xF08C00  # oranžová
    return 0x868E96      # šedá


def bar(discount: int) -> str:
    filled = max(1, round(discount / 10))
    return "🟥" * filled + "⬛" * (10 - filled)


def money(value: float, currency: str) -> str:
    sym = SYMBOLS.get(currency, currency)
    return f"{value:,.0f}".replace(",", " ") + f" {sym}"


# ═══════════════════════════════════════════════════════════════════════════ #
#  Steam / Discord
# ═══════════════════════════════════════════════════════════════════════════ #
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
    on_sale = discount > 0

    # Nadpisy (#, ##) fungují jen v description, NE v hodnotách polí.
    # Řádek nesmí začínat číslicí s tečkou, jinak z toho Discord udělá seznam.
    parts = [f"-# {random.choice(NARRATION)}"]

    if on_sale:
        parts += [
            f"## 🐉 SLEVA −{discount} %",
            bar(discount),
            "",
            f"# {final}",
            f"-# původně ~~{initial}~~  ·  ušetříš **{money(saved, currency)}**",
        ]
    else:
        parts += [
            "## 🧪 TESTOVACÍ POPLACH",
            "",
            f"# {final}",
            "-# žádná sleva · tohle je jen zkouška, klid",
        ]

    parts += ["", f"> {flavour(discount, count)}", "",
              f"## [👉 {random.choice(CTA)} 👈]({store})"]

    fields = [
        {"name": "📉 Sleva", "value": f"**−{discount} %**", "inline": True},
        {"name": "🤦 Připomínka", "value": f"**č. {count}**", "inline": True},
    ]
    if on_sale:
        fields.insert(
            0,
            {"name": "💰 Ušetříš", "value": f"**{money(saved, currency)}**",
             "inline": True},
        )

    return {
        "content": f"<@{USER_ID}>  {random.choice(HOOKS)}",
        "allowed_mentions": {"users": [USER_ID]},
        "embeds": [
            {
                "author": {"name": random.choice(AUTHORS)},
                "title": f"🔥 {name}",
                "url": store,
                "description": "\n".join(parts),
                "color": colour_for(discount),
                "fields": fields,
                # header.jpg existuje vždy. Ještě větší banner:
                # .../steam/apps/{APP_ID}/library_hero.jpg
                "image": {
                    "url": f"https://cdn.cloudflare.steamstatic.com/"
                    f"steam/apps/{APP_ID}/header.jpg"
                },
                "footer": {
                    "text": f"Steam · {COUNTRY.upper()} · {random.choice(FOOTERS)}"
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════ #
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
        return 0  # kvůli výpadku Steamu neshazuj workflow

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
        shown = max(count, 1) if FORCE else count + 1
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
