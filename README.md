# World AI Curation Platform

海外AI情報を主軸にしたキュレーション基盤です。
`X` と `note` は補助シグナルとして扱い、一次情報や信頼メディアを優先します。

## What This Build Includes
- 実ソース収集（RSS）
- 重複除去 + スコアリング + `raw / vibe / builder` 加工
- カードごとの `Builder Playbook`（30分試作手順 + 次の24hアクション）
- 非エンジニア向け導線（難易度、15分スタート、ノーコード手順、コピペ用Vibeプロンプト）
- Web API + 一覧UI（Audience切替、Main/Signals切替）
- 難易度フィルタ（初級/中級/上級寄り）でカードを絞り込み
- お気に入りフィルタ保存（保存/適用/削除/URLコピー）
- 定期自動更新（デフォルト60分ごと）
- 永続化（`DATABASE_URL` があればPostgres、なければJSON）

## Product Positioning
- Main focus: Global primary/trusted sources (Tier A/B)
- Secondary signals: X and note (Tier C)
- Tier C only stories are placed in `signals` unless corroborated

## Directory Layout
- `config/` source policy and source list
- `docs/` architecture and editorial docs（超初心者向け公開手順: `BEGINNER_RELEASE_CHECKLIST_JA.md`）
- `src/` app, connectors, curation pipeline, web assets
- `sql/` PostgreSQL schema (production design)
- `scripts/` local operation scripts (`db_up.sh`, `run_app.sh`, `run_app_prod.sh`, `install_launch_agent.sh`, `health_check.sh`, `backup_now.sh`, `public_readiness_check.sh`, `install_tunnel_launch_agent.sh`)
- `tests/` unit tests
- `data/cards_cache.json` runtime snapshot cache

## Quick Start
1. Install dependencies
```bash
cd /Users/naoya/world-ai-curation
python3 -m pip install -r requirements.txt
```

2. Run API + Web UI
```bash
cd /Users/naoya/world-ai-curation
python3 -m uvicorn src.app:app --reload
```

3. Open
- [http://127.0.0.1:8000](http://127.0.0.1:8000)

4. (Optional) Configure environment
```bash
cp .env.example .env
```

超初心者向けの一本道手順:
- `docs/BEGINNER_RELEASE_CHECKLIST_JA.md`

## Postgres Setup (Recommended)
`DATABASE_URL` を使う場合の最短手順です。

Docker Desktop がない場合:
```bash
brew install colima docker docker-compose
mkdir -p ~/.docker
cat > ~/.docker/config.json <<'JSON'
{
  "cliPluginsExtraDirs": [
    "/opt/homebrew/lib/docker/cli-plugins"
  ]
}
JSON
colima start
```

1. Postgres起動（Docker）
```bash
cd /Users/naoya/world-ai-curation
./scripts/db_up.sh
```

2. `.env` 作成
```bash
cd /Users/naoya/world-ai-curation
cp .env.example .env
```

3. アプリ起動（`.env` 読み込み込み）
```bash
cd /Users/naoya/world-ai-curation
./scripts/run_app.sh
```

4. 停止するとき
```bash
cd /Users/naoya/world-ai-curation
./scripts/db_down.sh
```

Cloud DB（Neon/Supabase/RDS）を使う場合は、`.env` の `DATABASE_URL` をその接続文字列に置き換えるだけでOKです。

## Secret Rotation (Recommended)
Slack Webhook / Notion Token を一度公開場所に貼った場合は、必ず再発行してください。

1. Slack webhook を再発行し、`.env` の `SLACK_WEBHOOK_URL` を更新
2. Notion integration token を再発行し、`.env` の `NOTION_API_TOKEN` を更新
3. ページ共有はそのまま維持し、`NOTION_PAGE_ID` は既存値を継続利用
4. 投稿テストを実行

```bash
cd /Users/naoya/world-ai-curation
./scripts/run_app_prod.sh
# 別ターミナルで
curl -sS -u admin:admin -X POST "http://127.0.0.1:8000/api/admin/audit/weekly-report/publish?days=7&top_limit=5&save=true&archive=true"
```

### Rotate Admin Password
管理画面ログインの `ADMIN_PASSWORD` も定期的に更新してください。

```bash
cd /Users/naoya/world-ai-curation
python3 - <<'PY'
from pathlib import Path
import re, secrets, string, os
env_path = Path('.env')
text = env_path.read_text(encoding='utf-8')
alphabet = string.ascii_letters + string.digits + '-_'
pw = ''.join(secrets.choice(alphabet) for _ in range(28))
text = re.sub(r'^ADMIN_PASSWORD=.*$', f'ADMIN_PASSWORD={pw}', text, flags=re.M)
env_path.write_text(text, encoding='utf-8')
Path('.admin_password.txt').write_text(pw + '\\n', encoding='utf-8')
os.chmod('.admin_password.txt', 0o600)
print('updated .env and .admin_password.txt')
PY
./scripts/install_launch_agent.sh
```

## Auto Start on macOS (launchd)
再起動後も自動で起動する設定です。

1. インストール（自動起動ON）
```bash
cd /Users/naoya/world-ai-curation
./scripts/install_launch_agent.sh
```

2. 状態確認
```bash
curl -sS http://127.0.0.1:8000/api/status
```

3. ログ確認
```bash
tail -f /tmp/world-ai-curation.out.log
tail -f /tmp/world-ai-curation.err.log
```

4. アンインストール（自動起動OFF）
```bash
cd /Users/naoya/world-ai-curation
./scripts/uninstall_launch_agent.sh
```

## Hourly Health Check (launchd)
毎時のヘルスチェックと、異常時Slack通知（任意）を有効化できます。

1. 手動チェック
```bash
cd /Users/naoya/world-ai-curation
./scripts/health_check.sh
```

2. 自動チェックON（毎時）
```bash
cd /Users/naoya/world-ai-curation
./scripts/install_healthcheck_launch_agent.sh
```

3. ログ確認
```bash
tail -f /tmp/world-ai-curation-healthcheck.out.log
tail -f /tmp/world-ai-curation-healthcheck.err.log
```

4. 自動チェックOFF
```bash
cd /Users/naoya/world-ai-curation
./scripts/uninstall_healthcheck_launch_agent.sh
```

## Daily Backup (launchd)
`data/` と Postgres ダンプを日次バックアップします。

1. 手動バックアップ
```bash
cd /Users/naoya/world-ai-curation
./scripts/backup_now.sh
```

2. 自動バックアップON（デフォルト毎日 03:15）
```bash
cd /Users/naoya/world-ai-curation
./scripts/install_backup_launch_agent.sh
```

3. ログ確認
```bash
tail -f /tmp/world-ai-curation-backup.out.log
tail -f /tmp/world-ai-curation-backup.err.log
```

4. 自動バックアップOFF
```bash
cd /Users/naoya/world-ai-curation
./scripts/uninstall_backup_launch_agent.sh
```

5. 復元の基本
```bash
# 例: Postgres復元（対象DBを空にしてから）
pg_restore --dbname="$DATABASE_URL" --clean --if-exists /path/to/postgres_YYYYmmdd_HHMMSSZ.dump

# data/ 復元
tar -C /Users/naoya/world-ai-curation -xzf /path/to/data_backup_YYYYmmdd_HHMMSSZ.tar.gz
```

## X Token Check
Xを有効化する前に、Bearer tokenの疎通確認ができます。

```bash
cd /Users/naoya/world-ai-curation
./scripts/check_x_token.sh
```

## Public Release / SEO
一般公開時は `PUBLIC_BASE_URL` を本番URLに設定してください。

```bash
PUBLIC_BASE_URL=https://your-domain.example
```

実装済み:
- `canonical / Open Graph / Twitter Card`
- `robots.txt`（`/admin` と `/api/admin/` はクロール除外）
- `sitemap.xml`
- `feed.xml / rss.xml`
- FAQ構造化データ（JSON-LD）
- 法務ページ（`/privacy`, `/terms`, `/affiliate-disclosure`）

アフィリエイト表示は `config/affiliate_links.json` で編集できます。
`is_active: true` の項目だけ表示されます。
Vercel運用では `AFFILIATE_LINKS_JSON`（環境変数）を設定すると、ファイルより優先して反映されます。

```json
{
  "disclosure": "本ページにはアフィリエイトリンクが含まれる場合があります。",
  "links": [
    {
      "title": "あなたの案件名",
      "url": "https://example.com/your-affiliate-link",
      "description": "読者向けの説明文",
      "badge": "初心者向け",
      "image_url": "https://m.media-amazon.com/images/I/....jpg",
      "image_alt": "商品画像の説明",
      "is_active": true
    }
  ]
}
```

画像付きカードについて（規約配慮）:
- `image_url` は Amazon提供ドメインの `https` URL のみ表示されます。
- 例: `m.media-amazon.com` / `images-na.ssl-images-amazon.com` / `ws-fe.amazon-adsystem.com`
- 画像URLは Amazonアソシエイトの SiteStripe / 公式提供手段で取得したものを使ってください。

VercelにCLIで反映する例:
```bash
cd /Users/naoya/world-ai-curation-standalone
python3 - <<'PY'
import json, pathlib
path = pathlib.Path("config/affiliate_links.json")
print(json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False))
PY
```
上の1行JSON出力をコピーして、Vercelの `Settings -> Environment Variables` で  
`AFFILIATE_LINKS_JSON` に貼り付けてください（Environmentは `Production`）。

Amazonアフィリエイトを3件まとめて設定する（推奨）:
```bash
cd /Users/naoya/world-ai-curation-standalone
./scripts/setup_amazon_affiliate_links.sh YOUR_AMAZON_TAG-22 production
vercel deploy --prod --yes
```

`YOUR_AMAZON_TAG-22` は AmazonアソシエイトのトラッキングIDに置き換えてください。

公開前チェック:
```bash
cd /Users/naoya/world-ai-curation
./scripts/public_readiness_check.sh
```

このチェックは、設定ファイルの存在確認に加えて、公開URLへの到達確認（`/`, `/robots.txt`, `/sitemap.xml`, `/feed.xml` など）も行います。

### Cloudflare Tunnel で公開（推奨）
1. `cloudflared` をインストール
```bash
brew install cloudflared
```

2. Cloudflareにログイン
```bash
cloudflared tunnel login
```

3. トンネル作成
```bash
cloudflared tunnel create world-ai-curation
```

4. DNSルートを作成（例: `ai.your-domain.com`）
```bash
cloudflared tunnel route dns world-ai-curation ai.your-domain.com
```

5. 設定ファイル `~/.cloudflared/config.yml` を作成
```yaml
tunnel: world-ai-curation
credentials-file: /Users/naoya/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: ai.your-domain.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

6. `.env` の公開URLを更新してアプリ再起動
```bash
PUBLIC_BASE_URL=https://ai.your-domain.com
```

7. トンネル起動
```bash
cloudflared tunnel run world-ai-curation
```

8. 自動起動化（任意）
```bash
cd /Users/naoya/world-ai-curation
./scripts/install_tunnel_launch_agent.sh
```

停止する場合:
```bash
cd /Users/naoya/world-ai-curation
./scripts/uninstall_tunnel_launch_agent.sh
```

## Environment Variables
- `AUTO_REFRESH_ON_START` (`1` or `0`, default `1`)
- `REFRESH_INTERVAL_MINUTES` (default `60`)
- `AUTO_WRITE_WEEKLY_BRIEF` (`1` or `0`, default `0`)
- `AUTO_WRITE_WEEKLY_BRIEF_ARCHIVE` (`1` or `0`, default `1`)
- `AUTO_POST_WEEKLY_BRIEF` (`1` or `0`, default `0`)
- `WEEKLY_BRIEF_DAYS` (default `7`)
- `WEEKLY_BRIEF_TOP_LIMIT` (default `5`)
- `WEEKLY_BRIEF_JSON_PATH` (default `data/weekly_brief_latest.json`)
- `WEEKLY_BRIEF_MD_PATH` (default `data/weekly_brief_latest.md`)
- `WEEKLY_BRIEF_ARCHIVE_DIR` (default `data/weekly_briefs`)
- `WEEKLY_BRIEF_HISTORY_PATH` (default `data/weekly_brief_history.json`)
- `WEEKLY_BRIEF_HISTORY_MAX_ENTRIES` (default `200`)
- `SLACK_WEBHOOK_URL` (optional, incoming webhook for weekly brief)
- `NOTION_API_TOKEN` (optional, integration token for weekly brief posting)
- `NOTION_PAGE_ID` (optional, target page block ID for weekly brief posting)
- `DATABASE_URL` (optional, Postgres connection URL)
- `ADMIN_USERNAME` (default `admin`)
- `ADMIN_PASSWORD` (default `admin`)
- `PUBLIC_BASE_URL` (公開URL。SEOのcanonical/OG/sitemap生成に使用)
- `AFFILIATE_LINKS_PATH` (アフィリエイトリンクJSONのパス)
- `AFFILIATE_LINKS_JSON` (optional, JSON string。Vercel運用で推奨)
- `CLOUDFLARED_TUNNEL_TOKEN` (Cloudflare tunnel token)
- `CLOUDFLARED_BIN` (optional, cloudflared binary path)
- `X_BEARER_TOKEN` (optional, for X API ingestion)
- `X_SEARCH_QUERIES` (optional, `||` separated query list)
- `TIER_C_SOURCE_LIMIT` (optional, default `4`; X/noteなどTier Cの1ソースあたり取得上限)
- `RSS_HTTP_TIMEOUT_SECONDS` (optional, default `20`)
- `LLM_PROVIDER` (`none` or `openai`, default `none`)
- `OPENAI_API_KEY` (required when `LLM_PROVIDER=openai`)
- `OPENAI_MODEL` (optional, default `gpt-5-mini`)
- `OPENAI_BASE_URL` (optional, default `https://api.openai.com`)
- `APP_PYTHON` (optional, launchdで使うPythonを明示したい場合)
- `APP_STATUS_URL` (health check target, default `http://127.0.0.1:8000/api/status`)
- `HEALTH_MAX_STALE_MINUTES` (health check stale threshold, default `180`)
- `HEALTH_MIN_CARD_COUNT` (health check minimum card count, default `1`)
- `HEALTH_ALERT_SLACK` (`1` to notify Slack on health failure, default `1`)
- `BACKUP_DIR` (backup output directory)
- `BACKUP_RETENTION_DAYS` (old backup cleanup threshold, default `14`)
- `BACKUP_INCLUDE_DATA_DIR` (`1` or `0`, include `data/`)
- `BACKUP_INCLUDE_PG` (`1` or `0`, include Postgres dump)
- `BACKUP_PG_DOCKER_CONTAINER` (docker pg_dump fallback container name)
- `BACKUP_PG_DB_USER` (docker pg_dump fallback db user)
- `BACKUP_PG_DB_NAME` (docker pg_dump fallback db name)
- `BACKUP_DAILY_HOUR` (launchd backup hour, default `3`)
- `BACKUP_DAILY_MINUTE` (launchd backup minute, default `15`)

Example:
```bash
AUTO_REFRESH_ON_START=1 REFRESH_INTERVAL_MINUTES=30 python3 -m uvicorn src.app:app --reload
```

X and LLM enabled example:
```bash
X_BEARER_TOKEN=xxxxx \
LLM_PROVIDER=openai \
OPENAI_API_KEY=xxxxx \
OPENAI_MODEL=gpt-5-mini \
python3 -m uvicorn src.app:app --reload
```

## API
- `GET /api/status`
- `GET /api/affiliate-links`
- `GET /api/cards?audience=vibe&section=all&status=published&limit=30&topic=&difficulty=`
- `POST /api/refresh`
- `GET /api/admin/cards?audience=vibe&section=all&status=all&limit=200`
- `POST /api/admin/cards/{card_id}/status`
- `POST /api/admin/cards/{card_id}/pin`
- `GET /api/admin/audit?limit=100&offset=0&action=&card_id=&actor=&from_ts=&to_ts=`
- `GET /api/admin/audit/stats?days=7&action=&card_id=&actor=&from_ts=&to_ts=`
- `GET /api/admin/audit.csv?limit=500&action=&card_id=&actor=&from_ts=&to_ts=`
- `GET /api/admin/audit/trend.csv?days=7&action=&card_id=&actor=&from_ts=&to_ts=`
- `GET /api/admin/audit/weekly-report?days=7&top_limit=5&action=&card_id=&actor=&from_ts=&to_ts=`
- `GET /api/admin/audit/weekly-report/history?limit=20&offset=0&sort=desc&q=&from_ts=&to_ts=`
- `GET /api/admin/audit/weekly-report/history.csv?limit=200&offset=0&sort=desc&q=&from_ts=&to_ts=`
- `DELETE /api/admin/audit/weekly-report/history?confirm=true&keep_latest=0&q=&from_ts=&to_ts=`
- `POST /api/admin/audit/weekly-report/history/cleanup?confirm=true&keep_latest=200`
- `GET /api/admin/audit/weekly-report.md?days=7&top_limit=5&action=&card_id=&actor=&from_ts=&to_ts=`
- `POST /api/admin/audit/weekly-report/write?days=7&top_limit=5&archive=true&publish=false&action=&card_id=&actor=&from_ts=&to_ts=`
- `POST /api/admin/audit/weekly-report/publish?days=7&top_limit=5&save=false&archive=true&action=&card_id=&actor=&from_ts=&to_ts=`

`/api/status` includes `storage.backend` so you can verify whether `postgres` or `file` is active.

公開向け補助:
- `GET /robots.txt`
- `GET /sitemap.xml`
- `GET /feed.xml`
- `GET /rss.xml`
- `GET /privacy`
- `GET /terms`
- `GET /affiliate-disclosure`

## Admin UI
- Feed: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Admin: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)

Admin UI allows:
- Status update: `draft / published / archived`
- Pinning and pin order (`pin_rank`)
- Access control: HTTP Basic auth (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)
- Audit logs: who changed which card and when
- Audit filters: `action / card_id / actor`
- Date range filters: `from_ts / to_ts` (ISO 8601)
- Date presets: `Last 24 hours / Today / Last 7 days / This month / Last month`
- Audit pagination: `limit / offset` + Prev/Next controls
- Audit visual cues: color highlight by action (`status_update` / `pin_update`)
- Audit action summary: count by action on current page or filtered-all scope
- Audit trend: last `7/14/30` days daily counts (Status/Pin), scope switchable (`Current Page` / `Filtered All`)
- Audit trend export: trend CSV download for currently selected filter + day window
- Weekly brief: compact weekly JSON report with highlights + non-engineer-friendly playbook
- Weekly brief export: Markdown download + JSON/Markdown file write API
- Weekly brief publish: Slack / Notion へ投稿（任意で同時保存）
- Weekly brief history: save履歴をAPIで一覧表示
- Weekly brief history ops: 履歴の検索 / CSV出力 / 条件削除
- Audit filter persistence: remembers filter state in browser local storage
- Audit share helper: copy current filter URL (URL params can restore filters on open)
- Audit export: CSV download

## Source Policy
Source definitions are managed in:
- `/Users/naoya/world-ai-curation/config/sources.yaml`

Default weighting:
- Tier A: highest trust
- Tier B: medium trust
- Tier C: low trust (signals-first)

## Test
```bash
cd /Users/naoya/world-ai-curation
python3 -m unittest discover -s tests
```

## Next Build Milestones
1. Add connector-level rate limiting and retry/backoff strategy
2. Add stronger dedup with embeddings
3. Add user personalization and weekly digest
4. Add automated translation quality checks for JP summaries
