"""One keyword, several Taobao regional hosts: what changes and what does not.

For each regional host (sg, jp, my, ...) this fetches the same keyword page
and reports, per host:

  * the <html lang> and the English page title Taobao adds for that market
  * how many products Taobao says it lists for the keyword there
  * the local currency printed under each CNY price, and the CNY to local
    rate those printed prices imply (median of local / CNY over the page)
  * whether the product order matches the first host's order

The implied rate is Taobao's display estimate (the prices are prefixed
with 约, "approximately"), not a market FX rate. Treat it as such.

Usage:
    export SCRAPINGBEE_API_KEY=...
    python taobao_regions.py 手机壳 --regions sg jp my --csv regions.csv

Costs 1 credit per host (classic proxy, no JavaScript).
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys

from taobao_world import REGIONS, Blocked, keyword_page


def summarise(keyword: str, regions: list[str]) -> list[dict]:
    rows, first_order = [], None
    for cc in regions:
        try:
            page = keyword_page(keyword, cc)
        except Blocked as e:
            rows.append({"region": cc, "error": str(e)})
            continue
        order = [p.item_key for p in page.products]
        first_order = first_order or order
        ratios = [p.local_price / p.price_cny for p in page.products if p.local_price and p.price_cny]
        currencies = {p.local_currency for p in page.products if p.local_currency}
        rows.append(
            {
                "region": cc,
                "lang": page.lang,
                "title_en": page.page_title.split("|")[0].strip() if page.page_title else None,
                "listed": page.listed_count,
                "products": len(page.products),
                "currency": ",".join(sorted(currencies)) or None,
                "implied_cny_rate": round(statistics.median(ratios), 4) if ratios else None,
                "same_order_as_first": order == first_order,
                "credits": page.credits,
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare a Taobao keyword page across regional hosts")
    ap.add_argument("keyword")
    ap.add_argument("--regions", nargs="+", default=["sg", "jp", "my"], choices=REGIONS)
    ap.add_argument("--csv")
    a = ap.parse_args()

    rows = summarise(a.keyword, a.regions)
    for r in rows:
        if "error" in r:
            print(f"{r['region']}: {r['error']}")
            continue
        print(
            f"{r['region']}  {r['lang']}  listed={r['listed']:<6} {r['currency']}  "
            f"1 CNY ~ {r['implied_cny_rate']}  same order={r['same_order_as_first']}  {r['title_en']}"
        )
    print(f"{sum(r.get('credits', 0) for r in rows)} credit(s)", file=sys.stderr)
    if a.csv and rows:
        fields = sorted({k for r in rows for k in r})
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
