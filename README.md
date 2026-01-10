# Horse App (Render対応 / PDFなし)

## 概要
- netkeiba 成績URL（任意）を BeautifulSoup で参照し、実績を評価に反映（無ければ無視）
- STEP1: keiba.go.jp 年度統計CSV → 競馬場水準(level)を自動更新（URLのみ）
- STEP2: nankankeiba CSV → 脚質×距離補正を自動作成（URLのみ）
- STEP3: 繁殖牝馬 取引CSV → 市場価値（中央値）に校正（URL or Upload）

PDF出力は **完全に削除** しています。

## 使い方（ローカル）
```bash
pip install -r requirements.txt
export FLASK_SECRET="dev"
python -m horse_app.app
```

## Render
- Start Command: `gunicorn horse_app.app:app --bind 0.0.0.0:$PORT`
- Environment:
  - `FLASK_SECRET`（任意）
  - `ADMIN_TOKEN`（任意：/admin/refresh-data を保護）

## 重要
- netkeiba 取得は、利用規約に従って自己責任で使用してください（個人用途前提）。
- keiba.go.jp / nankankeiba のCSVは、あなたが入力したURLを **保存して参照** します（転載目的ではありません）。

## データ更新（常時表示リンク）
- `/admin/refresh-data` : 設定済みURLからCSVを再取得し data/ を更新
- `/status` : 現在のデータ状態（JSON）

## CSVフォーマット（目安）
### STEP1 keiba.go.jp 年度統計CSV
必要な列のいずれか（同義ならOK）:
- 競馬場 / 主催者
- 総賞金
- 出走頭数

### STEP2 nankankeiba CSV（脚質×距離補正）
推奨列:
- 競馬場（例: 大井/川崎/船橋/浦和）
- 距離（例: 1200, 1400, 1600）
- 脚質（逃げ/先行/差し/追込）
- 勝率 または 複勝率 または 連対率
- サンプル数（任意）

### STEP3 繁殖牝馬取引CSV（市場価値校正）
推奨列:
- 価格（万円）/ 取引価格 / 落札価格 / price_man
- 牝馬名（任意）
