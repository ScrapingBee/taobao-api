"""Taobao keyword pages to a translation-ready record set.

Taobao's own product search (s.taobao.com) and item pages
(item.taobao.com, detail.tmall.com) push a logged-out visitor to a login
page. The pages this module reads are the public, indexable keyword pages
Taobao publishes for overseas shoppers:

    https://world.taobao.com/product/<keyword>.htm        Traditional Chinese
    https://<cc>.world.taobao.com/product/<keyword>.htm   Simplified Chinese
                                                          plus a local price

Each page lists 20 products with title, CNY price, a local currency
estimate on the regional hosts, a star score and a short promo tag. Verified
live on 2026-10-29 through ScrapingBee classic proxies, no JavaScript,
1 credit per page.

Usage:
    export SCRAPINGBEE_API_KEY=...
    python taobao_world.py 手机壳 --region sg --json cases.jsonl --csv cases.csv
    python taobao_world.py "蓝牙耳机" --region jp
"""

from __future__ import annotations

import argparse
import base64
import csv
import html as htmllib
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from urllib.parse import quote

import requests

API = "https://app.scrapingbee.com/api/v1/"

# Regional hosts listed in the page's own hreflang alternates.
REGIONS = ["my", "sg", "vn", "mo", "au", "kr", "jp", "th", "nz", "ca", "ph", "kh"]


class Blocked(RuntimeError):
    """Taobao did not serve the public page."""


class LoginWall(Blocked):
    """Redirected to login.taobao.com. Not retried: it is not a public page."""


class SliderCheck(Blocked):
    """The x5secdata slider page. Retried once on premium proxies."""


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass
class Product:
    position: int
    item_url: str
    item_code: str                 # the opaque token in /item/<code>.htm
    item_key: str                  # decode_code(item_code), stable hex key
    title_zh: str
    script: str                    # "Hant" or "Hans", from <html lang>
    price_cny: float | None
    local_price: float | None      # regional hosts only
    local_currency: str | None
    local_price_raw: str | None    # as printed, e.g. "约SGD $22.61"
    rating: float | None
    tag_zh: str | None             # promo or review snippet under the title
    tag_en: str | None             # filled from GLOSSARY when it is a stock label
    title_en: str | None = None    # left empty for your translation step
    image_alt_zh: str | None = None


@dataclass
class KeywordPage:
    url: str
    canonical: str | None
    lang: str | None
    page_title: str | None
    listed_count: int | None       # from the meta description, "21,218件"
    category_path: list[str] = field(default_factory=list)
    alternates: dict[str, str] = field(default_factory=dict)
    products: list[Product] = field(default_factory=list)
    credits: int = 0


# Stock labels Taobao prints under prices. English is ours. Both scripts are
# listed, since world.taobao.com prints Traditional and the regional hosts
# print Simplified for the same label.
GLOSSARY = {
    "优惠价": "discounted price",
    "優惠價": "discounted price",
    "新品促销": "new product promotion",
    "新品促銷": "new product promotion",
}


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------


def keyword_url(keyword: str, region: str | None = None) -> str:
    host = f"{region}.world.taobao.com" if region else "world.taobao.com"
    # Percent-encode the Chinese path segment as UTF-8. requests would do it
    # too, but building it here keeps logged URLs copy-pasteable.
    return f"https://{host}/product/{quote(keyword, safe='')}.htm"


def fetch(url: str, premium: bool = False, retries: int = 3,
          session: requests.Session | None = None) -> tuple[str, dict]:
    """No JS. Classic proxy 1 credit, premium 10. Retries free HTTP 500s."""
    key = os.environ.get("SCRAPINGBEE_API_KEY") or sys.exit("Set SCRAPINGBEE_API_KEY first.")
    s = session or requests.Session()
    for attempt in range(1, retries + 1):
        r = s.get(
            API,
            headers={"Authorization": f"Bearer {key}"},
            params={"url": url, "render_js": "false", **({"premium_proxy": "true"} if premium else {})},
            timeout=120,
        )
        if r.status_code == 500 and attempt < retries:
            time.sleep(2 * attempt)
            continue
        r.raise_for_status()
        # The pages declare UTF-8 in the header and in <meta charSet>. Decode
        # the bytes ourselves rather than trusting requests' guess.
        body = r.content.decode("utf-8", errors="replace")
        meta = {k: r.headers.get(k) for k in ("spb-cost", "spb-resolved-url", "spb-initial-status-code")}
        if "login_jump" in body or "login.taobao.com" in (meta["spb-resolved-url"] or ""):
            raise LoginWall(f"{url}: redirected to the Taobao login page")
        if "_____tmd_____/punish" in body:
            raise SliderCheck(f"{url}: Taobao slider check (x5secdata)")
        return body, meta
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------
# Parse
# --------------------------------------------------------------------------

ITEM = re.compile(r'<a href="(https://world\.taobao\.com/item/([^".?]+)\.htm[^"]*)" class="item"(.*?)</a>', re.S)


def _cls(block: str, name: str) -> str | None:
    m = re.search(rf'class="view-basic {name}">([^<]*)<', block)
    return htmllib.unescape(m.group(1)).strip() if m else None


def to_number(text: str | None) -> float | None:
    """'116', '54.9', '21,218', '1万' and full-width digits to a number."""
    if not text:
        return None
    t = unicodedata.normalize("NFKC", text).replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*([万萬亿億]?)", t)
    if not m:
        return None
    n = float(m.group(1))
    return n * {"万": 1e4, "萬": 1e4, "亿": 1e8, "億": 1e8}.get(m.group(2), 1)


def parse_local(raw: str | None) -> tuple[float | None, str | None]:
    """'约SGD $22.61' -> (22.61, 'SGD'); '约JPY ¥2980' -> (2980.0, 'JPY')."""
    if not raw:
        return None, None
    m = re.search(r"([A-Z]{3})\s*\D*?([\d,]+(?:\.\d+)?)", raw)
    return (float(m.group(2).replace(",", "")), m.group(1)) if m else (None, None)


def decode_code(code: str) -> str:
    """The item code is base64 inside base64 around 16 opaque bytes.

    'SnA2dmxGcWpIZXRWLzJoZ0tCQjdXQT09' decodes to 'Jp6vlFqjHetV/2hgKBB7WA==',
    which decodes to 16 bytes. It is not the numeric id that item.taobao.com
    uses, so it cannot be joined to item.htm?id=... URLs. Use it as a key.
    """
    try:
        inner = base64.b64decode(code + "=" * (-len(code) % 4))
        return base64.b64decode(inner).hex()
    except ValueError:
        return ""


def parse(html: str, url: str) -> KeywordPage:
    lang = (re.search(r'<html lang="([^"]+)"', html) or [None, None])[1]
    script = "Hant" if lang in ("zh-TW", "zh-HK", "zh-MO") else "Hans"
    title = (re.search(r"<title>([^<]*)</title>", html) or [None, None])[1]
    desc = (re.search(r'<meta name="description" content="([^"]*)"', html) or [None, ""])[1]
    count = re.search(r"有([\d,]+)件", desc)
    crumbs = re.search(r'class="view-basic breadcrumb-items">(.*?)（', html, re.S)

    page = KeywordPage(
        url=url,
        canonical=(re.search(r'<link href="([^"]+)" rel="canonical"', html) or [None, None])[1],
        lang=lang,
        page_title=htmllib.unescape(title).strip() if title else None,
        listed_count=int(count.group(1).replace(",", "")) if count else None,
        category_path=[c for c in (htmllib.unescape(x).strip() for x in re.findall(r">([^<>]+)<", crumbs.group(1) if crumbs else "")) if c and c != ">"],
        alternates=dict(re.findall(r'<link hrefLang="([^"]+)" href="([^"]+)" rel="alternate"', html)),
    )
    for i, (href, code, block) in enumerate(ITEM.findall(html), 1):
        raw_local = _cls(block, "local-price")
        local, cur = parse_local(raw_local)
        tag = _cls(block, "discnt-item") or _cls(block, "comment-tag")
        alt = re.search(r'alt="([^"]*)" class="item-img"', block)
        page.products.append(
            Product(
                position=i,
                item_url=href.split("?")[0],
                item_code=code,
                item_key=decode_code(code),
                title_zh=htmllib.unescape(_cls(block, "item-title") or ""),
                script=script,
                price_cny=to_number(_cls(block, "disc-price")),
                local_price=local,
                local_currency=cur,
                local_price_raw=raw_local,
                rating=to_number(_cls(block, "rate-score")),
                tag_zh=tag,
                tag_en=GLOSSARY.get(tag or ""),
                image_alt_zh=htmllib.unescape(alt.group(1)) if alt else None,
            )
        )
    return page


def keyword_page(keyword: str, region: str | None = None) -> KeywordPage:
    url = keyword_url(keyword, region)
    try:
        html, meta = fetch(url)
        spent = int(meta.get("spb-cost") or 0)
    except SliderCheck:
        # Seen on world.taobao.com from classic IPs on 2026-10-29, while the
        # regional hosts kept answering. One premium retry got through.
        print(f"slider check on {url}, retrying on premium proxies (10 credits)", file=sys.stderr)
        html, meta = fetch(url, premium=True)
        spent = 1 + int(meta.get("spb-cost") or 0)
    page = parse(html, url)
    page.credits = spent
    if len(page.products) < 20:
        print(f"warning: {len(page.products)} products on {url}, expected 20", file=sys.stderr)
    return page


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


def write_jsonl(page: KeywordPage, path: str) -> None:
    """One product per line, ensure_ascii=False so the Chinese stays readable."""
    with open(path, "w", encoding="utf-8") as f:
        for p in page.products:
            row = {"source_url": page.url, "source_lang": page.lang, **asdict(p)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(page: KeywordPage, path: str) -> None:
    # utf-8-sig: Excel on Windows opens a BOM-less UTF-8 CSV as ANSI and
    # turns every Chinese title into mojibake.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        fields = list(asdict(page.products[0])) if page.products else []
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in page.products:
            w.writerow(asdict(p))


def main() -> None:
    ap = argparse.ArgumentParser(description="Taobao world keyword page to JSONL/CSV")
    ap.add_argument("keyword", help="Chinese keyword, e.g. 手机壳")
    ap.add_argument("--region", choices=REGIONS, help="regional host for a local price column")
    ap.add_argument("--json", help="write products as JSON Lines")
    ap.add_argument("--csv", help="write products as CSV (UTF-8 with BOM)")
    a = ap.parse_args()

    try:
        page = keyword_page(a.keyword, a.region)
    except Blocked as e:
        sys.exit(str(e))

    print(f"{page.page_title}\n{page.lang}  listed: {page.listed_count}  path: {' > '.join(page.category_path)}")
    for p in page.products[:5]:
        local = f"  {p.local_currency} {p.local_price}" if p.local_price else ""
        print(f"{p.position:>2}. CNY {p.price_cny}{local}  {p.rating}  {p.title_zh[:40]}")
    print(f"{len(page.products)} products, {page.credits} credit(s)")
    if a.json:
        write_jsonl(page, a.json)
    if a.csv:
        write_csv(page, a.csv)


if __name__ == "__main__":
    main()
