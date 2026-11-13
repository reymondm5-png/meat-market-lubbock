#!/usr/bin/env python3
"""Conservative weekly-ad candidate collector for Lubbock Meat Market.

No passwords, no proxies, no retailer authentication, no guessed prices. It reads
public third-party ad summaries where permitted and emits unverified suggestions;
only positively validated store-specific data should ever be emitted in `prices`.
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

FOOD_KING = "https://foodking.weeklyad.us.com/"
UNITED_LOCAL = "https://dealhivemind.com/weekly-ads/lubbock-tx/united-supermarket/"
UNITED_INDEX = "https://www.weeklyads.now/united-supermarkets"
UA = "MeatMarketPersonalPriceTracker/1.4 (+weekly public ad summary; once daily)"
TARGET = ("Food King", "United")


def classify(title):
    s = " ".join(title.casefold().split())
    if re.search(r"\b(cooked|breaded|nugget|patty|patties|wing|tenderloin|tender|chunk|frozen|sausage|smoked|deli|hot dog)\b", s):
        return None
    if "boneless" in s and "skinless" in s and "breast" in s and "turkey" not in s:
        return "Chicken breast"
    if (("ground beef" in s or "ground chuck" in s or "hamburger meat" in s)
            and "turkey" not in s and "meatball" not in s):
        return "Ground beef"
    if re.search(r"\bpork\b", s) and re.search(r"\bchops?\b", s):
        return "Pork chops"
    if "boneless" in s and "chuck" in s and "roast" in s and "pork" not in s:
        return "Boneless chuck roast"
    return None


def price_per_lb(text):
    """Only accepts explicitly labelled per-pound prices (not an each price)."""
    s = " ".join(text.strip().split())
    m = re.search(r"(\d{1,3})\s*¢\s*(?:/\s*(?:LB|LBS?)|PER\s+(?:POUND|LB))\b", s, re.I)
    if m:
        return round(int(m.group(1)) / 100, 2)
    m = re.search(r"\$\s*(\d{1,4}(?:\.\d{1,2})?)\s*(?:/\s*(?:LB|LBS?)|PER\s+(?:POUND|LB))\b", s, re.I)
    if not m:
        return None
    raw = m.group(1)
    # Some flyer summaries print $389/LB to mean $3.89/LB.
    if "." not in raw and len(raw) >= 3:
        val = int(raw) / 100
    else:
        val = float(raw)
    return round(val, 2) if 0.1 <= val <= 100 else None


def date_window_from_food_king(soup, today):
    header = soup.get_text(" ", strip=True)[:2400]
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s*[-–]\s*([A-Za-z]{3,9})\s+(\d{1,2})\b", header)
    if not m:
        return None
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            start = dt.datetime.strptime(f"{m[1]} {m[2]} {year}", "%d %b %Y").date()
            end_year = year + (dt.datetime.strptime(m[3][:3], "%b").month < start.month)
            end = dt.datetime.strptime(f"{m[4]} {m[3][:3]} {end_year}", "%d %b %Y").date()
        except ValueError:
            continue
        if 4 <= (end - start).days <= 9 and start <= today <= end:
            return start, end
    return None


def food_king_candidates(html, today):
    soup = BeautifulSoup(html, "html.parser")
    window = date_window_from_food_king(soup, today)
    if not window:
        return [], "Ad dates unavailable or not valid today; no prices accepted"
    # Table must explicitly declare the header names, avoiding unrelated tables.
    result = []
    rows_seen = 0
    meat_rows = 0
    matched_rows = 0
    product_tables = 0
    for table in soup.select("table"):
        heads = [h.get_text(" ", strip=True).lower() for h in table.select("th")]
        if not all(k in heads for k in ("product", "price", "unit", "category")):
            continue
        product_tables += 1
        ix = {key: heads.index(key) for key in ("product", "price", "unit", "category")}
        for tr in table.select("tr"):
            cells = tr.find_all("td")
            if len(cells) <= max(ix.values()):
                continue
            rows_seen += 1
            cat = cells[ix["category"]].get_text(" ", strip=True).upper()
            if cat != "MEAT":
                continue
            meat_rows += 1
            product = cells[ix["product"]].get_text(" ", strip=True)
            meat = classify(product)
            if not meat:
                continue
            matched_rows += 1
            price_text = cells[ix["price"]].get_text(" ", strip=True)
            unit = cells[ix["unit"]].get_text(" ", strip=True)
            p = price_per_lb(price_text)
            if p is None and unit.upper() in ("LB", "LBS", "PER LB"):
                # Some tables store LB in a separate column, but still require
                # unambiguous numeric pricing text.
                p = price_per_lb(price_text + "/LB")
            if p is None:
                continue
            result.append({"store": "Food King", "meat": meat, "product": product[:130],
                           "date": today.isoformat(), "saleEnds": window[1].isoformat(),
                           "pricePerLb": p, "priceIncludesMarkup": False,
                           "source": FOOD_KING, "reviewRequired": True,
                           "notes": "UNOFFICIAL flyer summary, not a confirmed Lubbock price. Food King adds 10% at checkout."})
    return result, (f"Food King source checked: {product_tables} product tables, {rows_seen} product rows, "
                    f"{meat_rows} meat rows, {matched_rows} target cuts, "
                    f"{len(result)} usable /lb prices. Unverified regional ads; check 8208 Slide Rd.")


def united_lubbock_candidates(html, today):
    """Read public Lubbock-area flyer text, extracting item names for manual review.

    Advertised amounts are *not* recorded because flyer extraction omits whether
    a number is per item, per pack, or per pound. Unlike the old directory source,
    this explicitly names the Lubbock region. It remains an unofficial listing.
    """
    soup = BeautifulSoup(html, "html.parser")
    txt = soup.get_text(" ", strip=True)
    if "Lubbock" not in txt[:2500] or "United" not in txt[:2500]:
        return [], "Lubbock location not identified; rejected source"
    dates = re.search(r"Current Ad Valid through\s+([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(20\d{2})", txt, re.I)
    if not dates:
        return [], "Current flyer expiry not identified; rejected source"
    try:
        end = dt.datetime.strptime(f"{dates[1][:3]} {dates[2]} {dates[3]}", "%b %d %Y").date()
    except ValueError:
        return [], "Invalid expiry date in Lubbock flyer; rejected source"
    if not (end - dt.timedelta(days=14) <= today <= end):
        return [], f"Local flyer not current (ends {end.isoformat()}); rejected source"
    # Only accept short visible strings corresponding to individual item titles.
    # Ignore site descriptions or huge containers to avoid accidental matches.
    unique = {}
    for value in soup.stripped_strings:
        product = " ".join(value.split())
        if not 8 <= len(product) <= 115 or "\n" in product:
            continue
        meat = classify(product)
        if not meat:
            continue
        if not re.search(r"[A-Za-z]", product):
            continue
        k = (meat, product.casefold())
        unique[k] = {"store":"United", "meat": meat, "product":product,
                     "date":today.isoformat(), "saleEnds":end.isoformat(),
                     "source": UNITED_LOCAL, "reviewRequired":True,
                     "notes":"Unofficial Lubbock-area flyer listing. Product ONLY; price /lb, package and store availability NOT verified. Check United 8010 Frankford Ave."}
    n = re.search(r"(\d{1,4}) items extracted", txt, re.I)
    count = n[1] if n else "unknown"
    return list(unique.values())[:35], (f"Lubbock-area listing read ({count} advertised items reported); "
                                      f"{len(unique)} tracked product names matched; prices not verified per lb")


def united_directory_candidates(getter, today):
    """Fallback: scan all pages of one third-party regional flyer, not just page 1.

    This source may be for Pecos/another Texas region. It is never used to
    assert local Lubbock prices. It is useful only as potential leads.
    """
    idx = getter(UNITED_INDEX)
    flyer = discover_united_url(idx)
    if not flyer:
        return [], "No current regional flyer in the fallback index"
    first = getter(flyer)
    soup = BeautifulSoup(first, "html.parser")
    found = re.search(r"(\d{1,2}) pages", soup.get_text(" ", strip=True)[:600])
    pages = min(int(found[1]) if found else 1, 12)
    location = soup.get_text(" ", strip=True)
    match = re.search(r"Nearest store (.{3,65}?) \d+ mi away", location)
    area = match[1] if match else "unknown region"
    all_rows = []
    errors = []
    for n in range(1, pages+1):
        try:
            html = first if n == 1 else getter(flyer.rstrip('/') + f'/page/{n}')
            rows, status = united_candidates(html, flyer, today)
            all_rows.extend(rows)
        except Exception as exc:
            errors.append(f"page {n}: {type(exc).__name__}")
    # Deduplicate repeated titles in different pages.
    unique = {(r['meat'], r['product'].casefold()):r for r in all_rows}
    for r in unique.values():
        r['notes'] = (f"REGIONAL flyer ({area}); NOT verified for Lubbock. "
                      "Price and /lb unit missing. Check United 8010 Frankford Ave.")
    return list(unique.values())[:35], (f"Regional fallback {area}: checked {pages} pages, "
                                      f"{len(unique)} tracked products; "
                                      + (f"{len(errors)} pages had errors" if errors else "no page errors")
                                      + "; not confirmed local prices")


def united_window(soup, today):
    text = soup.get_text(" ", strip=True)[:1800]
    m = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(20\d\d)\s+to\s+([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(20\d\d)", text, re.I)
    if not m:
        return None
    try:
        st = dt.datetime.strptime(f"{m[1][:3]} {m[2]} {m[3]}", "%b %d %Y").date()
        en = dt.datetime.strptime(f"{m[4][:3]} {m[5]} {m[6]}", "%b %d %Y").date()
        return (st, en) if st <= today <= en else None
    except ValueError:
        return None


def united_candidates(html, url, today):
    soup = BeautifulSoup(html, "html.parser")
    window = united_window(soup, today)
    if not window:
        return [], "Flyer dates unavailable or expired; no suggestions"
    # This public third-party summary often omits whether a price is per pound.
    # Expose matching products for review rather than inventing a $/lb amount.
    matches = []
    for h in soup.find_all("h3"):
        product = h.get_text(" ", strip=True)
        meat = classify(product)
        if not meat:
            continue
        item = {"store": "United", "meat": meat, "product": product[:130],
                "date": today.isoformat(), "saleEnds": window[1].isoformat(),
                "source": url, "reviewRequired": True,
                "notes": "UNOFFICIAL regional flyer. Confirm 8010 Frankford store, price and per-pound unit in the official ad."}
        matches.append(item)
    return matches, f"Found {len(matches)} matching products (unit not reliably published; verify before entering)"


def discover_united_url(index_html):
    soup = BeautifulSoup(index_html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(UNITED_INDEX, a["href"])
        path = urllib.parse.urlparse(href).path
        if re.fullmatch(r"/united-supermarkets/united-supermarkets-flyer-[a-z0-9-]+", path):
            return href
    return None


def public_get(url, wait=1.0):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"foodking.weeklyad.us.com", "www.weeklyads.now", "dealhivemind.com"}:
        raise ValueError("Only approved public HTTPS sources allowed")
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        with urllib.request.urlopen(urllib.request.Request(robots_url, headers={"User-Agent": UA}), timeout=12) as r:
            rp.parse(r.read(100000).decode("utf-8", "ignore").splitlines())
    except Exception as exc:
        raise RuntimeError(f"Could not check robots.txt for {parsed.hostname}: {exc}") from exc
    if not rp.can_fetch(UA, url):
        raise RuntimeError(f"Source does not permit collection according to robots.txt: {parsed.hostname}")
    time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=18) as r:
        if r.status != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            raise RuntimeError("Unexpected page response")
        blob = r.read(1250000)
        if len(blob) >= 1250000:
            raise RuntimeError("Page too large")
        return blob.decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def run(today=None, getter=public_get):
    today = today or dt.datetime.now(ZoneInfo("America/Chicago")).date()
    candidates, notes = [], {}
    try:
        rows, status = food_king_candidates(getter(FOOD_KING), today)
        candidates.extend(rows)
        notes["Food King"] = status
    except Exception as exc:
        notes["Food King"] = f"Source unavailable: {type(exc).__name__}: {exc}"
    try:
        rows, status = united_lubbock_candidates(getter(UNITED_LOCAL), today)
        if not status.startswith("Lubbock-area listing read"):
            raise RuntimeError(status)
        candidates.extend(rows)
        notes["United"] = status
    except Exception as exc:
        # An explicitly local flyer is preferable. If unavailable, fall back
        # to a regional source ONLY as unverified leads.
        local_error = f"{type(exc).__name__}: {exc}"
        try:
            rows, status = united_directory_candidates(getter, today)
            candidates.extend(rows)
            notes["United"] = status + f". Local listing unavailable: {local_error[:140]}"
        except Exception as exc2:
            notes["United"] = (f"No accessible local or regional flyer. "
                               f"Local: {local_error[:130]}; regional: {type(exc2).__name__}: {str(exc2)[:130]}")
    unique = {}
    for c in candidates:
        key = (c["store"], c["meat"], c["product"], c["source"], c["saleEnds"])
        unique[key] = c
    return {"location": "Lubbock, TX", "asOf": today.isoformat(),
            "prices": [],  # NEVER autopublish unverified third-party items as local shelf prices
            "candidates": list(unique.values())[:60],
            "status": notes, "mode": "review_first",
            "disclaimer": "These are unofficial regional-ad suggestions, NOT confirmed local store prices. Verify the official Lubbock ad before saving."}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="site/feed.json")
    p.add_argument("--date", help="Optional YYYY-MM-DD, for tests")
    args = p.parse_args()
    today = dt.date.fromisoformat(args.date) if args.date else None
    feed = run(today)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"asOf": feed["asOf"], "suggestions": len(feed["candidates"]), "status": feed["status"]}, indent=2))


if __name__ == "__main__":
    main()
