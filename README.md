<h1 align="center">🐉 Hlídač slev na Baldur's Gate 3</h1>

<p align="center">
  <em>Protože potřetí už to není náhoda, ale povahová vada.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/koupeno-je%C5%A1t%C4%9B%20ne-red?style=for-the-badge" alt="koupeno: ještě ne">
  <img src="https://img.shields.io/badge/p%C5%99ipom%C3%ADnek-3%2B-orange?style=for-the-badge" alt="připomínek: 3+">
  <img src="https://img.shields.io/badge/sebeovl%C3%A1d%C3%A1n%C3%AD-0%25-lightgrey?style=for-the-badge" alt="sebeovládání: 0 %">
  <img src="https://img.shields.io/badge/hostov%C3%A1n%C3%AD-zdarma-brightgreen?style=for-the-badge" alt="hostování: zdarma">
</p>

<p align="center">
  <img src="Toban BG3 Slevomat.webp" width="560">
</p>

## 😔 Problém

Baldur's Gate 3 jde do slevy. Ty to zjistíš. Řekneš si *"jo, koupím to o víkendu"*.

Víkend proběhne. Sleva skončí. Hra není koupená.

**Třikrát po sobě.**

## 🤖 Řešení

Robot, který každých šest hodin zkontroluje cenu na Steamu, a jakmile spadne pod tvůj práh, napíše ti na Discord. S pingem. Veřejně. A počítá si, pokolikáté už to dělá — protože číslo `3` v embedu bolí víc než jakákoli výčitka.

Neběží na žádném serveru. Neplatíš za něj ani korunu. Je to cron v GitHub Actions a webhook. Nic víc.

```mermaid
flowchart LR
    A["⏰ GitHub Actions<br/>1x denně 19:30"] --> B["🐍 check_sale.py"]
    B --> C{"Sleva ≥ práh<br/>a hlubší než minule?"}
    C -->|ne| D["🤷 mlčí<br/>a jde spát"]
    C -->|ano| E["📨 Discord webhook"]
    E --> F["🫵 ping + veřejná ostuda"]
    F --> G{"Koupíš to?"}
    G -->|ne| A
    G -->|ano| H["🎉 nemožné"]
```

## ✨ Co to umí

| | |
|---|---|
| 🕕 | Kontroluje cenu ráno i večer, napořád, zadarmo |
| 🎭 | Náhodné hlášky z osmi seznamů — neopakuje se ani po dvaceti slevách |
| 📈 | **Eskaluje.** První připomínka je milá. Čtvrtá ti počítá aura body do minusu |
| 🧠 | Pamatuje si, co už oznámil — nespamuje, ozve se jen když sleva klesne hlouběji |
| 🎨 | Barva embedu podle hloubky slevy (šedá → oranžová → červená → 🥇 zlatá) |
| 🧪 | Testovací režim, který se přizná, že je testovací |
| 🪶 | Nula závislostí. Jen standardní knihovna Pythonu |

## 🚀 Rozjezd (5 minut, fakt)

<details>
<summary><b>1. Discord webhook</b></summary>

V kanálu, kam to má chodit: **Nastavení kanálu → Integrace → Webhooky → Nový webhook**. Zkopíruj URL.

Žádná bot aplikace, žádný token, žádné intenty. Webhook je hloupá roura a přesně to tu stačí.
</details>

<details>
<summary><b>2. Tvoje Discord ID</b></summary>

V Discordu zapni **Nastavení → Pokročilé → Vývojářský režim**, pak pravý klik na sebe → **Kopírovat ID uživatele**.

Je to 18–19 číslic. Není to tvoje přezdívka. Ne, fakt není.
</details>

<details>
<summary><b>3. Secrets v repozitáři</b></summary>

**Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Co to je |
|---|---|
| `DISCORD_WEBHOOK_URL` | URL z kroku 1 |
| `TARGET_USER_ID` | Číslo z kroku 2 |

Pozor na mezeru nebo enter na konci při vkládání. Pak `urlopen` spadne a ty budeš hodinu hledat proč.
</details>

<details>
<summary><b>4. Zkušební výstřel</b></summary>

Záložka **Actions → BG3 sale watch → Run workflow**, zaškrtni `force` a spusť.

Přijde ti zpráva s aktuální (nejspíš nulovou) slevou. Tím máš ověřený webhook, ping i embed najednou. Vynucený běh se **nepočítá** do počítadla připomínek, takže si testem nespálíš tu ostřejší hlášku.
</details>

## 🎛️ Nastavení

Vše se ladí v `env:` bloku ve `.github/workflows/sale-watch.yml`:

| Proměnná | Výchozí | K čemu |
|---|---|---|
| `STEAM_APP_ID` | `1086940` | AppID hry. BG3. Klidně si tam dej cokoli jiného |
| `STEAM_CC` | `cz` | Region pro ceny |
| `MIN_DISCOUNT` | `20` | Od kolika procent má vůbec otravovat |
| `FORCE_NOTIFY` | `false` | Pošli to bez ohledu na slevu (jen testy) |

> [!TIP]
> Larian slevuje zřídka a mělce. S prahem `20` se můžeš načekat opravdu dlouho — `10` je realističtější.

> [!NOTE]
> Cron je v **UTC**, GitHub jiné pásmo neumí — v zimě ti tedy časy o hodinu poskočí.
>
> | Cron | Léto (SELČ) | Zima (SEČ) | Proč |
> |---|---|---|---|
> | `30 18 * * *` | 20:30 | 19:30 | Steam spouští slevy kolem 19:00 |


## 🎪 Kde bydlí vtipy

Všechny hlášky jsou nahoře v `check_sale.py` v seznamech `HOOKS`, `NARRATION`, `SHAME`, `SHAME_MANY`, `DEEP_CUT`, `CTA`, `FOOTERS` a `AUTHORS`.

Přidat vlastní = dopsat řádek do seznamu. Logiky se to nedotkne. Bav se.

## ❓ FAQ

<details>
<summary><b>Proč to neběží jako normální bot 24/7?</b></summary>

Protože dělá **dva HTTP requesty denně**. Držet kvůli tomu naživu proces je jako topit v paneláku krbem.

Navíc v roce 2026 free tiery pro always-on boty prakticky umřely — Fly.io free tier zrušil, Render free služby usínají po 15 minutách a background workery má placené, Railway dává jen kredit. Oracle Always Free funguje, ale sbírá idle instance. Cron v Actions žádný z těchto problémů nemá.
</details>

<details>
<summary><b>Nevypne GitHub naplánovaný workflow po 60 dnech nečinnosti?</b></summary>

Vypnul by. Proto skript při každém běhu zapíše čerstvý `last_check` do `state.json` a workflow ho commitne zpátky. Repozitář je tím pádem pořád "aktivní" a plánovač běží dál.

Cenou jsou dva mikro-commity denně v historii. V privátním repu to nikoho netrápí.
</details>

<details>
<summary><b>Kolik to žere minut?</b></summary>

Veřejný repo: nic, Actions jsou zdarma neomezeně. Privátní: ~1 minuta za běh, při dvou denních spuštěních tedy asi **60 z 2000** měsíčních minut zdarma.
</details>

<details>
<summary><b>Přišla mi zpráva, ale ping nikoho neoznačil.</b></summary>

`TARGET_USER_ID` není číselné ID. Viz krok 2.
</details>

<details>
<summary><b>Můžu tím hlídat jinou hru?</b></summary>

Jasně, přepiš `STEAM_APP_ID`. AppID najdeš v URL obchodu: `store.steampowered.com/app/`**`1086940`**`/...`

Hlášky ale mluví o tom, že jsi to zapomněl koupit potřetí. Tak si je uprav, ať to sedí.
</details>

## 🗺️ Roadmap

- [x] Zjistit, že je sleva
- [x] Napsat na Discord
- [x] Počítat, kolikrát jsem to ignoroval
- [x] Urážet přímo úměrně tomu číslu
- [ ] Hlídat i GOG (přes IsThereAnyDeal)
- [ ] **Skutečně tu hru koupit** ← jediná položka, na které záleží
- [ ] Zahrát si ji


<p align="center">
  <sub>Postaveno proti vlastní vůli · MIT licence · hru jsem pořád nekoupil</sub>
</p>
