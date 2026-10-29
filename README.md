# Taobao API

<p align="center">
  <a href="https://www.scrapingbee.com/">
    <img src="REPLACE_WITH_SCREENSHOT_URL" alt="taobao-api" />
  </a>
</p>

[![checks](https://github.com/ScrapingBee/taobao-api/workflows/checks/badge.svg)](https://github.com/ScrapingBee/taobao-api/actions)
[![license](https://img.shields.io/github/license/ScrapingBee/taobao-api.svg)](LICENSE)

A [taobao scraper api](https://www.scrapingbee.com/scrapers/taobao-api/) has two problems before it has a parsing problem. Most of Taobao refuses a visitor who is not signed in, and what remains is written in two Chinese scripts, priced in yuan with a full-width currency sign, and localised per market by hostname rather than by IP. This repo deals with both. It maps which Taobao pages answered a logged-out request on 2026-10-29, reads the one public page type that carries product data, and writes records that keep the Chinese text intact and leave an empty slot for your translation step. Requests go through [ScrapingBee](https://www.scrapingbee.com/) at 1 credit each.

## Taobao scraping without an account: what answered

Each URL was requested through ScrapingBee with no cookies and no login. "Verdict" is read from the body, because Taobao answers almost everything with HTTP 200.

| URL | Tier, credits | Verdict |
|---|---|---|
| `https://www.taobao.com/` | classic, 1 | home page, 93 KB, links to `item.taobao.com` and `detail.tmall.com` items |
| `https://world.taobao.com/` | classic, 1 | overseas home page, JSON-LD `SearchAction` (quoted below) |
| `https://world.taobao.com/product/<keyword>.htm` | classic, 1 | **20 products** on most runs, slider check on some |
| `https://sg.world.taobao.com/product/<keyword>.htm` | classic, 1 | **20 products** with a local price, on every published keyword we tried |
| `https://www.taobao.com/list/product/<keyword>.htm` | classic, 1 | slider check page (`_____tmd_____/punish`, `x5secdata`) |
| `https://s.taobao.com/search?q=手机` | classic, 1 | 34 KB JavaScript shell, no products |
| `https://m.intl.taobao.com/` | classic, 1 | 12 KB shell |
| `https://item.taobao.com/item.htm?id=730344766230` | classic, 1 | 5 KB page that sends the browser to `login.taobao.com` |
| same item, premium proxy + JavaScript | premium, 25 | `spb-initial-status-code: 302`, resolved URL `https://login.taobao.com/havanaone/login/login.htm?...`, title `登录` (log in) |
| `https://detail.tmall.com/item.htm?id=666640816810` | classic, 1 | same login redirect |
| `https://world.taobao.com/item/<code>.htm` | classic, 1 | same login redirect |

So item pages, and therefore per-SKU reviews, seller blocks and full image galleries, are behind a login for a logged-out visitor. This repo stops there; scraping with login credentials is against ScrapingBee's terms, and nothing here signs in, stores cookies from a session, or replays one. Shop pages were not tested: no shop URL appeared on any page we could load without an account, and we did not want to guess one.

The redirect is easy to detect. The 5 KB item response is a script that builds the login URL:

```html
<script>
  localStorage.x5referer = window.location.href;
  var host = (isMobile || isHarmony) ? "https://login.m.taobao.com/login.htm?from=sm&ttid=h5@iframe&redirectURL=" : "https://login.taobao.com/member/login.jhtml?redirectURL=";
  var jump = "https%3a%2f%2fitem.taobao.com:443/wow/z/app/tbpc/pc-detail-ssr-2025/home%2F_____tmd_____%2Fpage%2Flogin_jump%3Frand%3D...";
```

`taobao_world.py` raises `LoginWall` on `login_jump` or a `login.taobao.com` resolved URL, and `SliderCheck` on `_____tmd_____/punish`, before any parsing happens.

## The page that works: Taobao's overseas keyword pages

`world.taobao.com` declares its own search URL in JSON-LD:

```json
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "url": "https://world.taobao.com/",
  "potentialAction": {
    "@type": "SearchAction",
    "target": { "@type": "EntryPoint", "urlTemplate": "https://world.taobao.com/product/{keyword}.htm" },
    "query-input": "required name=keyword"
  }
}
```

Those keyword pages are server rendered, indexable (`<meta name="robots" content="index,follow"/>`), and list 20 products each. One product card, with the image placeholder and star icons trimmed:

```html
<a href="https://world.taobao.com/item/SnA2dmxGcWpIZXRWLzJoZ0tCQjdXQT09.htm?spm=a21wu.10013406-sg.taglist-content.1" class="item" target="_blank">
  <div class="view-basic innder-container">
    <div class="view-basic img-container"><img src="https://gw.alicdn.com/imgextra/i4/O1CN01CYtPWu1MUBqQAUK9D_!!6000000001437-2-tps-2-2.png" alt="【新款18勃艮第红色】图拉斯雪雾适用iPhone18ProMax手机壳..." class="item-img"/></div>
    <div class="view-basic item-title">【新款18勃艮第红色】图拉斯雪雾适用iPhone18ProMax手机壳苹果17磁吸外壳16pm高级磨砂15Pro保护套14P全包13</div>
    <div class="view-basic attrs-box" data-spm="ranklist-link"><div class="view-basic discnt-item">优惠价</div></div>
    <div class="view-basic price-box"><div class="view-basic currency">￥</div><div class="view-basic disc-price">116</div></div>
    <div class="view-basic local-price">约SGD $22.61</div>
    <div class="view-basic rate-box"><div class="view-basic star-box">...</div><div class="view-basic rate-score">4.8</div></div>
  </div>
</a>
```

Every field the parser reads is a `view-basic <name>` class: `item-title`, `disc-price`, `local-price`, `rate-score`, and one of `discnt-item` (a stock label) or `comment-tag` (a review snippet such as `强磁吸附AI拍照键抗发黄`). The `<img src>` is the same placeholder file (`...-tps-2-2.png`) on every card, so the server HTML has no product image URL; the scraper keeps the `alt` text instead.

Two limits, both measured. There is no pagination: `?page=2` returned the same 20 products in the same order. And keyword pages exist for keywords Taobao has published, not for anything you type. `外套`, `钱包男` and `手机壳` worked; `蓝牙耳机` (Bluetooth earphones) redirected to login on `sg.world.taobao.com`. The safest keyword source is the page itself, which links to related published keywords such as `针织衫男`, `秋装` and `耐克男鞋`.

## Traditional or Simplified Chinese: the hostname decides

The same keyword lives on several hosts, and the page lists them in `hreflang` alternates:

```html
<link hrefLang="zh-Hans" href="https://www.taobao.com/list/product/手机壳.htm" rel="alternate"/>
<link hrefLang="zh-Hant" href="https://world.taobao.com/product/手機保護殼.htm" rel="alternate"/>
<link hrefLang="x-default" href="https://world.taobao.com/product/手機保護殼.htm" rel="alternate"/>
<link hrefLang="zh-Hans-MY" href="https://my.world.taobao.com/product/手机壳.htm" rel="alternate"/>
<link hrefLang="zh-Hans-SG" href="https://sg.world.taobao.com/product/手机壳.htm" rel="alternate"/>
<link hrefLang="zh-Hans-JP" href="https://jp.world.taobao.com/product/手机壳.htm" rel="alternate"/>
```

Twelve regional hosts in total: `my sg vn mo au kr jp th nz ca ph kh`. What changes between them:

| | `world.taobao.com` | `sg.world.taobao.com` and other regional hosts |
|---|---|---|
| `<html lang>` | `zh-TW` | `zh-CN` |
| Script | Traditional, `手機保護殼` | Simplified, `手机壳` |
| Keyword in the canonical URL | rewritten: we asked for `手机壳` and got canonical `手機保護殼` | kept as `手机壳` |
| `<title>` | `手機保護殼 - Top 1萬件手機保護殼 - 2026年10月更新 - 淘寶Taobao｜天貓Tmall` | `Phone case Latest Top Selling Recommendations \| Taobao Singapore \| ...` followed by Chinese |
| Local price under the CNY price | none | `约SGD $22.61` |
| Listed count in `meta description` | `21,114件` | `21,218件` |

The product titles are the seller's text converted between scripts, so the same item is `图拉斯雪雾` on one host and `圖拉斯雪霧` on the other. If you store titles from both hosts, keep `script` with each record and convert to one script before de-duplicating; a byte comparison will treat them as different products. The regional `<title>` carries an English rendering of the keyword (`Phone case`, `Coat`, `wallet man`), which is Taobao's machine translation and useful as a label, not as a product title.

## Encoding details that break naive parsers

- **UTF-8 bytes, decoded explicitly.** The response header is `text/html;charset=UTF-8` and the page has `<meta charSet="utf-8"/>`. The client decodes `response.content` as UTF-8 itself instead of relying on a guessed encoding.
- **Percent-encoded paths.** The keyword is a path segment, so `手机壳` goes on the wire as `%E6%89%8B%E6%9C%BA%E5%A3%B3`. `keyword_url()` does `quote(keyword, safe='')` so logged URLs can be pasted back in.
- **Two different yen signs.** The CNY price sits in `<div class="view-basic currency">` as `￥`, the full-width yen sign U+FFE5. The Japanese local price is `约JPY ¥2980` with the ordinary U+00A5 sign. Do not detect currency from the symbol: read the ISO code (`SGD`, `JPY`, `MYR`, `AUD`, `KRW`) that Taobao prints in the local price, and treat the separate full-width sign as CNY.
- **`约` means approximately.** Every local price starts with it.
- **Full-width punctuation and 万.** The breadcrumb ends with `（共找到1万件商品）` in full-width parentheses, and the title says `Top 1萬件`. `万` (Traditional `萬`) is ten thousand. `to_number()` applies NFKC normalisation, which turns full-width digits into ASCII, and then multiplies by 万/萬 or 亿/億.
- **CSV for Excel.** Files are written as `utf-8-sig`. Without the byte order mark, Excel on Windows opens UTF-8 CSV as the local ANSI code page and every title turns to mojibake.

## Currency and `country_code`: test before you pay for geolocation

ScrapingBee's classic proxies accept `country_code` for 40+ countries, including `cn`, `sg` and `jp`. On these pages it made no difference. `world.taobao.com` fetched with `country_code=us` returned the same Traditional Chinese page with no local price, and every regional host returned its own currency from whatever IP the request used. The market is chosen by the hostname, so the scripts never set `country_code`.

[`examples/taobao_regions.py`](examples/taobao_regions.py) fetches one keyword from several hosts and derives the CNY rate each host's prices imply. Live run on `手机壳`, 5 credits:

```
sg  zh-CN  listed=22604  SGD  1 CNY ~ 0.1949  same order=True  Phone case Latest Top Selling Recommendations
jp  zh-CN  listed=21085  JPY  1 CNY ~ 25.6908  same order=False  Phone case Latest Best Selling Praise Recommendation
my  zh-CN  listed=22604  MYR  1 CNY ~ 0.6209  same order=True  Phone case Latest Authentic Product Praise Recommendation
au  zh-CN  listed=22608  AUD  1 CNY ~ 0.2168  same order=True  Phone case Latest Best Selling Praise Recommendation
kr  zh-CN  listed=22595  KRW  1 CNY ~ 210.0953  same order=True  Phone case Latest Best Selling Praise Recommendation
```

Three observations from that run. Japan's catalogue is smaller and ordered differently from the other four. The listed counts moved during the day (Singapore showed 21,218 in the morning and 22,604 in the afternoon). And the implied rates are Taobao's display conversion, with rounding on small prices, so use them to sanity check the `local_price` column, not as exchange rates.

## A translation-ready output schema

Each product becomes one JSON Lines record. Chinese fields end in `_zh`, the slot for your translation is present and `null`, and the source language travels with the record so a translation service can be told what it is reading. A real record from the Singapore `外套` (coat) page:

```json
{"source_url": "https://sg.world.taobao.com/product/%E5%A4%96%E5%A5%97.htm", "source_lang": "zh-CN", "position": 1,
 "item_url": "https://world.taobao.com/item/V3dYaDhIZ3pQczhHVEVlaWpnRy9zQT09.htm",
 "item_code": "V3dYaDhIZ3pQczhHVEVlaWpnRy9zQT09", "item_key": "5b05e1f078333ecf064c47a28e01bfb0",
 "title_zh": "蕉下男士飞行员夹克立领气绒服秋冬棉袄轻薄防风棉衣保暖棉服外套", "script": "Hans",
 "price_cny": 479.0, "local_price": 93.36, "local_currency": "SGD", "local_price_raw": "约SGD $93.36",
 "rating": 4.9, "tag_zh": "保暖似羽绒 防风雨抗湿冷", "tag_en": null, "title_en": null,
 "image_alt_zh": "蕉下男士飞行员夹克立领气绒服秋冬棉袄轻薄防风棉衣保暖棉服外套"}
```

| Field | Notes |
|---|---|
| `title_zh`, `script` | Seller title as printed, and `Hant` or `Hans` from `<html lang>` |
| `title_en` | Always `null` on output, for your machine translation or human pass |
| `price_cny` | Number from `disc-price`, the CNY shelf price |
| `local_price`, `local_currency`, `local_price_raw` | Parsed and raw `约SGD $93.36`; empty on `world.taobao.com` |
| `tag_zh`, `tag_en` | The line under the title. `tag_en` is filled only for stock labels in `GLOSSARY` (`优惠价`/`優惠價` = discounted price, `新品促销`/`新品促銷` = new product promotion). Free text snippets stay Chinese only |
| `item_code`, `item_key` | See below |
| `rating` | The `rate-score`, out of 5 |

Keyword pages also give page level fields: `listed_count` from the meta description (`当前有21,218件...在售`), `category_path` from the breadcrumb (`首页 > 3C数码配件市场 > 手机配件 > 保护套/壳 > 手机壳`), the canonical URL and every `hreflang` alternate.

**Item codes are not item ids.** `SnA2dmxGcWpIZXRWLzJoZ0tCQjdXQT09` is base64 of `Jp6vlFqjHetV/2hgKBB7WA==`, which is itself base64 of 16 opaque bytes. They do not contain the numeric id that `item.taobao.com/item.htm?id=` uses, so you cannot join these rows to item URLs from elsewhere. The same product has the same code on every regional host, which makes `item_key` (the hex of those 16 bytes) a usable join key across markets.

## Run it

```bash
export SCRAPINGBEE_API_KEY=your_key
pip install requests
python examples/taobao_world.py 外套 --region sg --json coat.jsonl --csv coat.csv
```

```
Coat Latest Top Selling Recommendations | Taobao Singapore | Tmall Singapore | 外套最新好评热卖推荐 - 2026年10月 | 淘宝 新加坡 | 天猫 新加坡
zh-CN  listed: 96119  path: 首页 > 女装 > 短外套 > 外套
 1. CNY 479.0  SGD 93.36  4.9  蕉下男士飞行员夹克立领气绒服秋冬棉袄轻薄防风棉衣保暖棉服外套
 2. CNY 599.0  SGD 116.75  4.8  【林孝埈同款】安踏火壳2.0丨Polartec大地之壳抓绒衣男外套夹克
 3. CNY 589.0  SGD 114.8  4.8  骆驼运动外套秋冬季男防风防水加绒保暖三防跑步夹克登山服外衣女
20 products, 1 credit(s)
```

The Traditional Chinese host, same keyword:

```
外套 - Top 1萬件外套 - 2026年10月更新 - 淘寶Taobao｜天貓Tmall
zh-TW  listed: 17394  path: 首頁 > 流行男裝 > 棉衣 > 外套
 1. CNY 208.8  4.8  啄木鳥綿羊毛派克服棉衣男冬季中老年爸爸裝外套加絨加厚保暖外套
 2. CNY 378.0  4.7  貴人鳥立領羽絨棉服男士冬季新款加厚防寒棉衣外套保暖冬裝棉襖子
20 products, 1 credit(s)
```

Not the same list: the zh-TW host files `外套` under men's padded jackets (`流行男裝 > 棉衣`) with 17,394 items, while the Singapore host puts it under women's short jackets with 96,119. Treat each host as its own catalogue view.

The script warns when a page is short. `钱包男` on the Australian host returned 18 products, not 20, and said so:

```
warning: 18 products on https://au.world.taobao.com/product/%E9%92%B1%E5%8C%85%E7%94%B7.htm, expected 20
```

## The slider check, and when premium proxies are worth 10 credits

`world.taobao.com` sometimes answers classic proxies with a 2.9 KB slider page instead of products. During our test day the same URL returned products, then the slider, then products again. When `fetch()` sees it, `keyword_page()` retries once with `premium_proxy=true`, still without JavaScript. That premium request returned all 20 products for 10 credits in our test. The regional hosts never showed the slider in our runs, which is one more reason to prefer them.

```python
try:
    html, meta = fetch(url)                  # classic, 1 credit
except SliderCheck:
    html, meta = fetch(url, premium=True)    # premium, no JS, 10 credits
```

JavaScript rendering is never needed: every field is in the server HTML. Auto mode is no shortcut here either, because it accepts any HTTP 200 and the slider page is a 200. Check the body for products whichever tier you use.

## Check access from the shell

[`examples/taobao_access_check.sh`](examples/taobao_access_check.sh) is plain `curl` and prints a verdict per URL. The run at the end of our test day:

```
status cost  bytes    verdict        url
200    1     2987     slider-check   https://world.taobao.com/product/%E6%89%8B%E6%9C%BA%E5%A3%B3.htm
200    1     94802    products:20    https://sg.world.taobao.com/product/%E6%89%8B%E6%9C%BA%E5%A3%B3.htm
200    1     2759     slider-check   https://www.taobao.com/list/product/%E6%89%8B%E6%9C%BA%E5%A3%B3.htm
200    1     34331    js-shell       https://s.taobao.com/search?q=%E6%89%8B%E6%9C%BA
200    1     5044     login-wall     https://item.taobao.com/item.htm?id=730344766230
200    1     4765     login-wall     https://world.taobao.com/item/SnA2dmxGcWpIZXRWLzJoZ0tCQjdXQT09.htm
```

## Related ScrapingBee pages

Other Asian and cross-border marketplace scrapers: [AliExpress API](https://www.scrapingbee.com/scrapers/aliexpress-api/), [Alibaba API](https://www.scrapingbee.com/scrapers/alibaba-api/), [1688 search API](https://www.scrapingbee.com/scrapers/1688-search-api/), [Temu API](https://www.scrapingbee.com/scrapers/temu-api/), [Shopee API](https://www.scrapingbee.com/scrapers/shopee-api/), [Lazada API](https://www.scrapingbee.com/scrapers/lazada-api/), [Rakuten scraper API](https://www.scrapingbee.com/scrapers/rakuten-scraper-api/).

Documentation: [HTML API and credit costs](https://www.scrapingbee.com/documentation/), [classic proxy country codes](https://www.scrapingbee.com/documentation/country_codes_classic/), [CSS extraction rules](https://www.scrapingbee.com/documentation/data-extraction/), [Markdown output for LLM translation](https://www.scrapingbee.com/features/markdown-scraper/), [pricing](https://www.scrapingbee.com/pricing/). New accounts get 1,000 free credits, which is 1,000 keyword pages at the classic rate.

## Scope

Public keyword pages only. Item detail, reviews, seller storefronts, carts and anything else that Taobao routes through `login.taobao.com` are out of scope, by design and by ScrapingBee's terms, which do not permit scraping behind a login. Product titles are seller text; if you republish translated titles, the seller and Taobao's terms still govern the content.

## FAQ

**Is this an official Taobao API?**
No. It does not use any Taobao developer access and makes no claims about what official programmes cover. It reads public pages through ScrapingBee.

**Why does my Taobao scraper get a login page for every product?**
Item URLs on `item.taobao.com`, `detail.tmall.com` and `world.taobao.com/item/` all redirected a logged-out request to `login.taobao.com` in our tests, with and without JavaScript. Use the keyword pages instead.

**Do I need `country_code` to get prices in my currency?**
No. Use the regional host (`sg.`, `jp.`, `au.` and so on). The IP country did not change the currency in our tests.

**Which Chinese should I scrape, Traditional or Simplified?**
Simplified, from a regional host, if you plan to machine translate or match against mainland data. The regional hosts also showed fewer slider checks. Keep `world.taobao.com` for Traditional Chinese markets, and convert scripts before matching titles across hosts.

**How much does Taobao scraping cost with ScrapingBee?**
1 credit per keyword page on classic proxies without JavaScript, 10 when a premium retry is needed for the slider page. See [pricing](https://www.scrapingbee.com/pricing/) for plans.

## License

MIT. See [LICENSE](LICENSE).
