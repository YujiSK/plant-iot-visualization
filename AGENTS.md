# AGENTS.md

## プロジェクト概要

このプロジェクトは、2台のRaspberry Piと複数センサー、Supabase、GitHub Pagesを使った、室内水耕栽培環境の分散計測・可視化システムです。

`raspi`はDHT11、DS18B20、水位センサー、CdSセル、LEDを担当します。`raspberrypi2`はBH1750、DS18B20、フロートスイッチを担当します。両機は同じリポジトリを使用し、機体別の送信ファイルとsystemd serviceで同じSupabaseへ送信します。

## 恒久ルール

- 回答・報告は日本語で行う。
- 変更前に必ず `git status --short` を確認する。
- `.env`、`data.db`、秘密鍵、API キーを不用意に表示・変更・コミットしない。
- `docs/config.js` は GitHub Pages で公開されるファイルであるため、公開してよい内容か注意して扱う。
- DB スキーマを変更する前には、影響範囲と移行方針を説明する。
- systemd service を変更・再起動した場合は、`systemctl status` と `journalctl` を確認する。
- GitHub Pages の公開元は `docs/` である。
- 変更後は構文チェック・動作確認・差分確認を行う。
- 勝手にコミットしない。コミットする場合はユーザーの指示を待つ。
- 既存の未コミット変更を勝手に戻さない。自分の作業範囲外の差分は保護する。

## 通常作業の流れ

1. 現状確認
2. 変更方針の説明
3. 最小差分で実装
4. 構文チェック
5. 動作確認
6. `git diff` 確認
7. 日本語で報告
8. ユーザー指示があればコミット

## 新しいセッション開始時の確認

新しい Codex セッションを開始した場合、最初に以下を読み取り専用で確認する。

- `AGENTS.md`
- `docs/PROJECT_LOG.md`
- `docs/NEXT_ACTIONS.md`
- `git status --short`
- `git log --oneline -n 5`

この時点ではファイル変更を行わず、現在の状態、完了済み、未完了、次に着手すべき作業、注意点を日本語で整理して報告する。

## セッション終了前の整理

作業を終える前、またはセッションが長くなった場合は、以下を実施する。

1. `git status --short` を確認
2. `git diff` を確認
3. 今日完了したことを `docs/PROJECT_LOG.md` に追記
4. 次にやることを `docs/NEXT_ACTIONS.md` に反映
5. 恒久ルールに変更が必要な場合のみ `AGENTS.md` を更新
6. 変更内容を日本語で要約
7. 勝手にコミットはしない

## 確認コマンド

```bash
python -m py_compile main.py send_sensor.py vitality.py
curl http://localhost:8000/latest
systemctl status plant-api.service --no-pager -l
systemctl status plant-sensor.service --no-pager -l
journalctl -u plant-api.service -n 50 --no-pager -l
journalctl -u plant-sensor.service -n 80 --no-pager -l
git status --short
git diff
```
