import asyncio, os, re, sys, datetime as dt
from typing import Dict, Tuple, Optional, List

import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from playwright.async_api import async_playwright

# ----------- Config via ENV -----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

LIMIT_LOTTO        = int(os.getenv("LIMIT_LOTTO", "3000000"))
LIMIT_VIKINGLOTTO  = int(os.getenv("LIMIT_VIKINGLOTTO", "5000000"))
LIMIT_EUROJACKPOT  = int(os.getenv("LIMIT_EUROJACKPOT", "30000000"))

TZ                 = os.getenv("TIMEZONE", "Europe/Helsinki")
CRON_SUN_HOUR      = int(os.getenv("CRON_SUN_HOUR", "9"))
CRON_WED_HOUR      = int(os.getenv("CRON_WED_HOUR", "18"))
CRON_THU_HOUR      = int(os.getenv("CRON_THU_HOUR", "18"))  # Added for Vikinglotto

RUN_ONCE           = os.getenv("RUN_ONCE", "0") == "1"
TEST_GAMES         = os.getenv("TEST_GAMES", "").strip()

# ----------- Targets -----------
TARGETS = {
    "LOTTO": {
        "url": "https://www.veikkaus.fi/fi/lotto",
        "limit": LIMIT_LOTTO,
        "keywords": ["Jättipotti", "Potti", "Päävoitto", "jackpot", "Jackpot"],
        "selectors": [".jackpot", "[class*='jackpot']", "[id*='jackpot']", ".pot-value"],
    },
    "VIKINGLOTTO": {
        "url": "https://www.veikkaus.fi/fi/vikinglotto",
        "limit": LIMIT_VIKINGLOTTO,
        "keywords": ["Jättipotti", "Potti", "Päävoitto", "jackpot", "Jackpot"],
        "selectors": [".jackpot", "[class*='jackpot']", "[id*='jackpot']", ".pot-value"],
    },
    "EUROJACKPOT": {
        "url": "https://www.veikkaus.fi/fi/eurojackpot",
        "limit": LIMIT_EUROJACKPOT,
        "keywords": ["Jättipotti", "Potti", "Päävoitto", "jackpot", "Jackpot"],
        "selectors": [".jackpot", "[class*='jackpot']", "[id*='jackpot']", ".pot-value"],
    },
}

MONEY_RE = re.compile(r"(\d{1,3}(?:[ . ]\d{3})+|\d+)\s*€")

def _to_int_euros(s: str) -> Optional[int]:
    try:
        n = re.sub(r"[ . ]", "", s)
        return int(n)
    except Exception:
        return None

async def fetch_jackpot_for_page(page, url: str, keywords: List[str], selectors: List[str] = None) -> Optional[int]:
    """Loads page and searches for jackpot amounts using selectors first, then HTML parsing."""
    await page.goto(url, wait_until="networkidle", timeout=60000)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight/3)")
    await page.wait_for_timeout(2000)

    # Try selectors first (more reliable)
    selector_best: Optional[int] = None
    if selectors:
        for sel in selectors:
            try:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    text = await el.text_content()
                    if text:
                        matches = MONEY_RE.findall(text)
                        for m in matches:
                            val = _to_int_euros(m)
                            if val and val >= 100000:
                                if selector_best is None or val > selector_best:
                                    selector_best = val
            except Exception:
                continue
        if selector_best is not None:
            return selector_best

    # Fallback: HTML parsing
    html = await page.content()
    amounts = [m.group(1) for m in MONEY_RE.finditer(html)]
    euro_values = [_to_int_euros(num) for num in amounts if _to_int_euros(num) is not None]

    if not euro_values:
        return None

    # Find amounts near keywords
    html_lc = html.lower()
    best_keyword_amount: Optional[int] = None
    for kw in keywords:
        kw_lc = kw.lower()
        start = 0
        while True:
            idx = html_lc.find(kw_lc, start)
            if idx == -1:
                break
            win = html[max(0, idx - 500): idx + 500]
            cand = MONEY_RE.findall(win)
            cand_vals = [_to_int_euros(re.sub(r"[ . ]", "", c.replace("€","").strip())) for c in cand]
            cand_vals = [v for v in cand_vals if v is not None]
            if cand_vals:
                local = max(cand_vals)
                if (best_keyword_amount is None) or (local > best_keyword_amount):
                    best_keyword_amount = local
            start = idx + 1

    if best_keyword_amount is not None:
        return best_keyword_amount

    # Return largest amount >= 100000
    large_amounts = [v for v in euro_values if v >= 100000]
    if large_amounts:
        return max(large_amounts)

    return max(euro_values) if euro_values else None

async def get_all_jackpots() -> Dict[str, Tuple[Optional[int], int, str]]:
    out: Dict[str, Tuple[Optional[int], int, str]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for game, cfg in TARGETS.items():
                page = await browser.new_page()
                try:
                    amt = await fetch_jackpot_for_page(page, cfg["url"], cfg.get("keywords", []), cfg.get("selectors", []))
                except Exception:
                    amt = None
                finally:
                    await page.close()
                out[game] = (amt, cfg["limit"], cfg["url"])
        finally:
            await browser.close()
    return out

def send_telegram(msg: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("Telegram not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=20)
    except Exception as e:
        print("Telegram send failed:", e, file=sys.stderr)

def euro_fmt(n: int) -> str:
    return f"{n:,} €".replace(",", " ")

async def check_and_notify(games: Optional[List[str]] = None):
    tz = timezone(TZ)
    now = dt.datetime.now(tz)
    jackpots = await get_all_jackpots()

    lines = []
    alerts = []
    for game, (amount, limit, url) in jackpots.items():
        if games and game not in games:
            continue
        if amount is None:
            lines.append(f"• {game}: ei lukemaa — {url}")
            continue
        status = "OK" if amount < limit else "ALERT"
        lines.append(f"• {game}: {euro_fmt(amount)} (raja {euro_fmt(limit)}) [{status}]")
        if amount >= limit:
            alerts.append((game, amount, limit, url))

    header = f"Veikkaus jackpot-tarkistus {now.strftime('%Y-%m-%d %H:%M %Z')}"
    report = header + "\n" + "\n".join(lines)

    print(report, flush=True)

    if alerts:
        alert_lines = ["<b>Jackpot-hälytys</b>"]
        for game, amount, limit, url in alerts:
            alert_lines.append(f"• <b>{game}</b>: {euro_fmt(amount)} (raja {euro_fmt(limit)})\n{url}")
        send_telegram("\n".join(alert_lines))

def schedule_jobs():
    tz = timezone(TZ)
    sched = AsyncIOScheduler(timezone=tz)

    # Lotto: Sunday
    sched.add_job(check_and_notify, CronTrigger(day_of_week="sun", hour=CRON_SUN_HOUR, minute=0), kwargs={"games": ["LOTTO"]})

    # Eurojackpot: Wednesday & Saturday
    sched.add_job(check_and_notify, CronTrigger(day_of_week="wed", hour=CRON_WED_HOUR, minute=0), kwargs={"games": ["EUROJACKPOT"]})
    sched.add_job(check_and_notify, CronTrigger(day_of_week="sat", hour=CRON_WED_HOUR, minute=0), kwargs={"games": ["EUROJACKPOT"]})

    # Vikinglotto: Thursday
    sched.add_job(check_and_notify, CronTrigger(day_of_week="thu", hour=CRON_THU_HOUR, minute=0), kwargs={"games": ["VIKINGLOTTO"]})

    # Initial check
    sched.add_job(check_and_notify, next_run_time=dt.datetime.now(tz) + dt.timedelta(seconds=5))

    sched.start()
    return sched

if __name__ == "__main__":
    if TEST_GAMES:
        games_to_test = [g.strip().upper() for g in TEST_GAMES.split(",")]
        asyncio.run(check_and_notify(games=games_to_test))
        sys.exit(0)

    if RUN_ONCE:
        asyncio.run(check_and_notify())
        sys.exit(0)

    loop = asyncio.get_event_loop()
    schedule_jobs()
    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
