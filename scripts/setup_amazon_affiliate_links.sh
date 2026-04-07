#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [ "${#}" -lt 1 ]; then
  echo "Usage: $0 <AMAZON_ASSOCIATE_TAG> [production|preview]"
  echo "Example: $0 yourtag-22 production"
  exit 1
fi

AMAZON_TAG="${1}"
TARGET_ENV="${2:-production}"
JSON_PATH="${ROOT_DIR}/config/affiliate_links.json"

python3 - <<'PY' "${JSON_PATH}" "${AMAZON_TAG}"
import json
import sys
import urllib.parse
from pathlib import Path

path = Path(sys.argv[1])
tag = sys.argv[2].strip()

if not tag:
    raise SystemExit("AMAZON_ASSOCIATE_TAG is empty")
if "-" not in tag:
    raise SystemExit("AMAZON_ASSOCIATE_TAG format looks wrong. Example: yourtag-22")

items = [
    {
        "title": "USB-C ドッキングステーション",
        "keyword": "USB-C ドッキングステーション 4K",
        "description": "ノートPCの拡張性を一気に上げる定番。外部ディスプレイや有線LAN運用に便利。",
        "badge": "作業効率",
    },
    {
        "title": "静音メカニカルキーボード",
        "keyword": "静音 メカニカルキーボード 日本語配列",
        "description": "長時間タイピング向け。AI活用の入力作業を快適にしたい人におすすめ。",
        "badge": "入力快適化",
    },
    {
        "title": "4K Webカメラ（マイク付き）",
        "keyword": "4K Webカメラ マイク付き",
        "description": "AIミーティングや録画解説の品質を上げたい人向け。",
        "badge": "配信/会議",
    },
]

links = []
for row in items:
    query = urllib.parse.quote_plus(row["keyword"])
    url = f"https://www.amazon.co.jp/s?k={query}&tag={tag}"
    links.append(
        {
            "title": row["title"],
            "url": url,
            "description": row["description"],
            "badge": row["badge"],
            "image_url": "",
            "image_alt": f'{row["title"]} の商品画像',
            "is_active": True,
        }
    )

payload = {
    "disclosure": "当サイトはAmazonのアソシエイトとして、適格販売により収入を得ています。あわせて一部ページにはアフィリエイトリンクが含まれます。",
    "links": links,
}

path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"updated: {path}")
print(f"links: {len(links)}")
PY

"${ROOT_DIR}/scripts/set_affiliate_env_vercel.sh" "${JSON_PATH}" "${TARGET_ENV}"

echo "Done. Next step:"
echo "  cd ${ROOT_DIR}"
echo "  vercel deploy --prod --yes"
