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
    RESET_COUNTER         "1"/"true" -> vynuluj počítadlo připomínek (po koupi)
"""

import http.client
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _required(name: str) -> str:
    """Čitelná hláška místo holého KeyError traceback při chybějícím secretu."""
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit(
            f"::error::Chybí povinná proměnná {name}. "
            f"Nastav ji v Settings → Secrets and variables → Actions."
        )
    return value


# .strip() je tu schválně — zalomení řádku na konci secretu tiše rozbije ping.
WEBHOOK = _required("DISCORD_WEBHOOK_URL")
USER_ID = _required("TARGET_USER_ID")
APP_ID = os.getenv("STEAM_APP_ID", "1086940").strip() or "1086940"
COUNTRY = os.getenv("STEAM_CC", "cz").strip() or "cz"
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json").strip() or "state.json")
FORCE = _flag("FORCE_NOTIFY")
RESET = _flag("RESET_COUNTER")

try:
    MIN_DISCOUNT = int(os.getenv("MIN_DISCOUNT", "20").strip() or "20")
except ValueError:
    print("::warning::MIN_DISCOUNT není číslo, používám 20.")
    MIN_DISCOUNT = 20

if not USER_ID.isdigit():
    print(
        "::warning::TARGET_USER_ID není čistě číselné — ping nikoho neoznačí. "
        "Discord → Nastavení → Pokročilé → Vývojářský režim → pravý klik → Kopírovat ID."
    )

UA = {"User-Agent": "bg3-sale-watcher/1.1"}
SYMBOLS = {"EUR": "€", "CZK": "Kč", "USD": "$", "GBP": "£", "PLN": "zł"}
# Měny, které se v obchodech běžně uvádějí bez desetinných míst.
ZERO_DECIMAL = {"CZK", "JPY", "HUF", "KRW", "CLP", "IDR", "VND", "ISK"}

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
    "ozvu se zas · uvidíme, jak dopadneš",
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
    # +0.5 a int() místo round() — round() zaokrouhluje k sudým (25 → 2, 35 → 4).
    clamped = min(max(discount, 0), 100)
    filled = int(clamped / 10 + 0.5)
    return "🟥" * filled + "⬛" * (10 - filled)


def money(value: float, currency: str) -> str:
    """1 799 Kč · 19,99 € — mezera po tisících, čárka desetinná."""
    sym = SYMBOLS.get(currency, currency)
    decimals = 0 if currency in ZERO_DECIMAL or float(value).is_integer() else 2
    text = f"{value:,.{decimals}f}".replace(",", "\u202f").replace(".", ",")
    return f"{text} {sym}" if sym else text


def now_iso(seconds: bool = False) -> str:
    stamp = datetime.now(timezone.utc)
    return stamp.isoformat(timespec="seconds") if seconds else stamp.isoformat()


# ═══════════════════════════════════════════════════════════════════════════ #
#  Síť — jeden retry helper pro Steam i Discord
# ═══════════════════════════════════════════════════════════════════════════ #
def with_retry(call, label: str, attempts: int = 3):
    """Opakuje při 429 a 5xx a při síťových výpadcích. Respektuje Retry-After."""
    delay = 3
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except urllib.error.HTTPError as exc:
            # HTTPError musí být PŘED OSError — je to jeho potomek.
            wait = delay
            if exc.code == 429:
                try:
                    wait = max(wait, int(float(exc.headers.get("Retry-After", delay))))
                except (TypeError, ValueError):
                    pass
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == attempts:
                raise
            print(f"::warning::{label}: HTTP {exc.code}, znovu za {wait} s ({attempt}/{attempts})")
            time.sleep(min(wait, 60))
        except (OSError, http.client.HTTPException) as exc:
            # OSError pokrývá URLError, TimeoutError i ConnectionResetError.
            if attempt == attempts:
                raise
            print(f"::warning::{label}: {exc}, znovu za {delay} s ({attempt}/{attempts})")
            time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def get_json(url: str) -> dict:
    def call() -> dict:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    data = with_retry(call, "Steam")
    if not isinstance(data, dict):
        raise ValueError(f"Steam vrátil {type(data).__name__} místo objektu")
    return data


def steam_lookup(cached_name: str | None) -> tuple[str, dict | None]:
    """Return (name, price_overview | None).

    Filtr `basic` tahá i celý detailed_description (stovky kB), takže ho
    posíláme jen tehdy, když jméno hry ještě neznáme ze state.json.
    """
    filters = "price_overview" if cached_name else "price_overview,basic"
    url = (
        f"https://store.steampowered.com/api/appdetails"
        f"?appids={APP_ID}&cc={COUNTRY}&filters={filters}"
    )
    entry = get_json(url).get(APP_ID) or {}
    if not entry.get("success"):
        raise RuntimeError(f"Steam returned success=false for app {APP_ID}")
    data = entry.get("data") or {}
    name = data.get("name") or cached_name or f"App {APP_ID}"
    return name, data.get("price_overview")


def post_to_discord(payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")

    def call() -> None:
        req = urllib.request.Request(
            WEBHOOK, data=body, headers={**UA, "Content-Type": "application/json"}
        )
        # urlopen sám vyhodí HTTPError na 4xx/5xx, ruční kontrola status kódu
        # by byla mrtvý kód. Discord na úspěch vrací 204.
        with urllib.request.urlopen(req, timeout=30):
            return None

    with_retry(call, "Discord")


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
        {
            "name": "📉 Sleva",
            "value": f"**−{discount} %**" if on_sale else "**žádná**",
            "inline": True,
        },
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
                "timestamp": now_iso(),
            }
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════ #
#  Stav
# ═══════════════════════════════════════════════════════════════════════════ #
def load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    """Musí se zavolat na KAŽDÉ cestě ven — čerstvý last_check drží repo
    'aktivní', jinak GitHub po 60 dnech naplánovaný workflow vypne."""
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    except OSError as exc:
        print(f"::error::Nepodařilo se zapsat {STATE_FILE}: {exc}")


def as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════════════════ #
def main() -> int:
    state = load_state()

    if RESET:
        state["announced_discount"] = 0
        state["reminder_count"] = 0
        print("RESET_COUNTER — počítadlo připomínek vynulováno.")

    # Nastavíme HNED, ať se zapíše i když Steam nebo Discord spadne.
    state["last_check"] = now_iso(seconds=True)

    announced = as_int(state.get("announced_discount"))
    count = as_int(state.get("reminder_count"))
    cached_name = state.get("app_name") if str(state.get("app_id")) == APP_ID else None

    try:
        name, price = steam_lookup(cached_name)
    except (OSError, http.client.HTTPException, RuntimeError, ValueError) as exc:
        print(f"::warning::Steam lookup failed: {exc}")
        state["last_error"] = f"steam: {exc}"[:300]
        save_state(state)
        return 0  # kvůli výpadku Steamu neshazuj workflow

    state["app_id"] = APP_ID
    state["app_name"] = name
    state.pop("last_error", None)

    if not price:
        print("No price data (free / region-locked / delisted?)")
        save_state(state)
        return 0

    discount = as_int(price.get("discount_percent"))
    state["last_discount"] = discount
    print(f"{name}: -{discount}% (last announced {announced}%, reminder #{count})")

    qualifies = discount >= MIN_DISCOUNT and discount > announced
    if FORCE and not qualifies:
        print("FORCE_NOTIFY set — posílám i bez kvalifikující slevy (test).")

    if FORCE or qualifies:
        # Kvalifikující sleva = plnohodnotné oznámení, i když ho spustil FORCE.
        # Bez tohohle by následující plánovaný běh poslal tu samou slevu podruhé.
        shown = count + 1 if qualifies else max(count, 1)
        try:
            post_to_discord(build_payload(name, price, discount, shown))
        except (OSError, http.client.HTTPException, RuntimeError, ValueError) as exc:
            print(f"::error::Discord post failed: {exc}")
            state["last_error"] = f"discord: {exc}"[:300]
            save_state(state)  # stav ulož i při pádu, ať se commitne last_check
            return 1
        if qualifies:
            state["announced_discount"] = discount
            state["reminder_count"] = shown
        print("Notification sent.")
    elif discount < MIN_DISCOUNT:
        state["announced_discount"] = 0

    save_state(state)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # poslední záchranná síť — ať se stav neztratí
        print(f"::error::Neočekávaná chyba: {type(exc).__name__}: {exc}")
        save_state({**load_state(), "last_check": now_iso(seconds=True),
                    "last_error": f"crash: {exc}"[:300]})
        raise
