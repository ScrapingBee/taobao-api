#!/usr/bin/env bash
# Which Taobao URLs answer a logged-out visitor, and which bounce to login?
#
#   SCRAPINGBEE_API_KEY=... bash taobao_access_check.sh
#
# Classic proxy, no JavaScript: 1 credit per URL. For each URL it prints the
# status Taobao returned (spb-initial-status-code), the final URL
# (spb-resolved-url), the body size and a verdict read from the body.
set -euo pipefail

: "${SCRAPINGBEE_API_KEY:?Set SCRAPINGBEE_API_KEY first}"

urls=(
  "https://world.taobao.com/product/%E6%89%8B%E6%9C%BA%E5%A3%B3.htm"
  "https://sg.world.taobao.com/product/%E6%89%8B%E6%9C%BA%E5%A3%B3.htm"
  "https://www.taobao.com/list/product/%E6%89%8B%E6%9C%BA%E5%A3%B3.htm"
  "https://s.taobao.com/search?q=%E6%89%8B%E6%9C%BA"
  "https://item.taobao.com/item.htm?id=730344766230"
  "https://world.taobao.com/item/SnA2dmxGcWpIZXRWLzJoZ0tCQjdXQT09.htm"
)

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

printf "%-6s %-5s %-8s %-14s %s\n" "status" "cost" "bytes" "verdict" "url"
for u in "${urls[@]}"; do
  curl -s -G "https://app.scrapingbee.com/api/v1/" \
    -H "Authorization: Bearer ${SCRAPINGBEE_API_KEY}" \
    --data-urlencode "url=${u}" \
    --data-urlencode "render_js=false" \
    -D "$tmp/h" -o "$tmp/b"

  status=$(grep -i '^spb-initial-status-code:' "$tmp/h" | tr -d '\r' | awk '{print $2}')
  cost=$(grep -i '^spb-cost:' "$tmp/h" | tr -d '\r' | awk '{print $2}')
  bytes=$(wc -c < "$tmp/b" | tr -d ' ')

  if grep -q 'login_jump' "$tmp/b"; then
    verdict="login-wall"
  elif grep -q '_____tmd_____/punish' "$tmp/b"; then
    verdict="slider-check"
  elif grep -q 'class="view-basic item-title"' "$tmp/b"; then
    verdict="products:$(grep -o 'class="view-basic item-title"' "$tmp/b" | wc -l | tr -d ' ')"
  else
    verdict="js-shell"
  fi
  printf "%-6s %-5s %-8s %-14s %s\n" "${status:-?}" "${cost:-?}" "$bytes" "$verdict" "$u"
done
