# 超初心者向け 公開チェックリスト（そのまま実行版）

このファイルは「順番どおりやれば公開まで行ける」用です。  
専門用語をなるべく使わずに書いています。

## 0. 最初に知っておくこと
- あなたが設定する重要項目はこの3つです:
  - `PUBLIC_BASE_URL`（公開URL）
  - `CLOUDFLARED_TUNNEL_TOKEN`（公開トンネル用）
  - `config/affiliate_links.json`（アフィリエイト表示内容）
- `X_BEARER_TOKEN` は任意です。課金したくない間は空でOKです。

## 1. ターミナルを開く
```bash
cd /Users/naoya/world-ai-curation
```

## 2. `.env` を用意する
まだ作っていない場合:
```bash
cp .env.example .env
```

## 3. `.env` の重要項目を入れる
`.env` を開いて次を確認:
- `PUBLIC_BASE_URL=https://あなたの公開ドメイン`
- `CLOUDFLARED_TUNNEL_TOKEN=Cloudflareで取得したトークン`

例:
```env
PUBLIC_BASE_URL=https://ai.example.com
CLOUDFLARED_TUNNEL_TOKEN=xxxxxxxxxxxxxxxx
```

## 4. アフィリエイト内容を編集
ファイル:
`/Users/naoya/world-ai-curation/config/affiliate_links.json`

最低限ここだけ変えればOK:
- `title`
- `url`
- `description`
- `is_active`（表示するなら `true`）

## 5. アプリを常駐起動
```bash
cd /Users/naoya/world-ai-curation
./scripts/install_launch_agent.sh
```

## 6. 公開チェック（自動）
```bash
cd /Users/naoya/world-ai-curation
./scripts/public_readiness_check.sh
```

このチェックで確認されるもの:
- `PUBLIC_BASE_URL` がローカルのままではないか
- アフィリエイトJSONが読めるか
- トンネルトークンが入っているか
- `/robots.txt` などSEO用URLがHTTP 200で返るか

## 7. トンネル常駐起動（公開）
```bash
cd /Users/naoya/world-ai-curation
./scripts/install_tunnel_launch_agent.sh
```

## 8. 公開URLをブラウザで確認
以下を開いてエラーが出ないか確認:
- `https://あなたのドメイン/`
- `https://あなたのドメイン/robots.txt`
- `https://あなたのドメイン/sitemap.xml`
- `https://あなたのドメイン/feed.xml`

## 9. よくある詰まりポイント
- `command not found: cloudflared`
  - `brew install cloudflared`
- `CLOUDFLARED_TUNNEL_TOKEN is not set`
  - `.env` に token を貼る
- `/feed.xml` が404
  - アプリ再起動: `./scripts/install_launch_agent.sh`
  - その後 `./scripts/public_readiness_check.sh` 再実行

## 10. 公開後の毎日運用（1分）
```bash
cd /Users/naoya/world-ai-curation
./scripts/health_check.sh
```

異常時はログを見る:
```bash
tail -n 80 /tmp/world-ai-curation.err.log
tail -n 80 /tmp/world-ai-curation.out.log
```
