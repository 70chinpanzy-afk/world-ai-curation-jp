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
        "title": "生成AIの入門書（まず1冊）",
        "keyword": "生成AI 入門",
        "description": "AIの全体像をつかみたい初心者向け。",
        "badge": "初心者向け",
    },
    {
        "title": "ChatGPTプロンプト実践本",
        "keyword": "ChatGPT プロンプト 実践",
        "description": "日々の業務にすぐ使えるプロンプト例を学びたい人向け。",
        "badge": "実践重視",
    },
    {
        "title": "Python入門（AI活用の土台）",
        "keyword": "Python 入門",
        "description": "将来的にAI自動化にも挑戦したい人向け。",
        "badge": "スキルアップ",
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
