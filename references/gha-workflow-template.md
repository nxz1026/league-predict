# GitHub Actions Workflow Template

当需要将世界杯预测从 Hermes cron 迁移到 GitHub Actions 时，使用此模板。

## 完整 Workflow

```yaml
name: World Cup Predict

on:
  schedule:
    - cron: '4 8 * * *'  # 16:04 BJT (08:04 UTC)，比原 cron 稍早避免高峰
  workflow_dispatch:

jobs:
  predict:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Run prediction
        run: python scripts/predict_wc.py 2>&1 | tee /tmp/predict_output.txt

      - name: Format email
        id: format
        shell: bash
        run: |
          python3 << 'PYEOF'
          import json, sys, os
          from datetime import datetime, timezone, timedelta

          output = open('/tmp/predict_output.txt').read().strip()
          if not output:
              print("ERROR: No output")
              sys.exit(1)

          json_start = output.find('{')
          if json_start == -1:
              print("ERROR: No JSON found")
              sys.exit(1)

          decoder = json.JSONDecoder()
          data, _ = decoder.raw_decode(output[json_start:])

          bjt = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
          lines_out = []
          lines_out.append(f"⚽ 世界杯预测 | {bjt}")
          lines_out.append("=" * 30)
          lines_out.append("")

          cal = data.get('calibration', {})
          if cal.get('total_matches', 0) > 0:
              lines_out.append(f"📊 校准：{cal['total_matches']}场 | 主胜 {cal.get('home_win_rate',0)*100:.0f}% 平 {cal.get('draw_rate',0)*100:.0f}% 客胜 {cal.get('away_win_rate',0)*100:.0f}%")
              if cal.get('odds_accuracy', 0) > 0:
                  lines_out.append(f"   热门正确率：{cal['odds_accuracy']*100:.0f}%")
              lines_out.append("")

          preds = data.get('predictions', [])
          if not preds:
              lines_out.append("📌 未来 24h 无待预测比赛")
          else:
              lines_out.append(f"🔥 待预测：{len(preds)} 场")
              lines_out.append("")
              for p in preds:
                  poisson_str = " / ".join(f"{t['score']}({t['prob']:.0%})" for t in p.get('poisson_top3', [])[:3])
                  lines_out.append(f"🏟 {p['match']}")
                  lines_out.append(f"   方向：{p['direction']} {p['stars']}")
                  lines_out.append(f"   比分：{poisson_str}")
                  lines_out.append(f"   λ：{p.get('lambda_home',0)}/{p.get('lambda_away',0)} | {p.get('over_under','')} | BTTS {p.get('btts','')}")
                  lines_out.append("")

          email_body = "\n".join(lines_out)
          with open('/tmp/email_body.txt', 'w') as f:
              f.write(email_body)
          print(email_body)
          PYEOF
          echo "subject=⚽ 世界杯预测 $(TZ=Asia/Shanghai date +%m/%d)" >> "$GITHUB_OUTPUT"
          echo "body<<EOF" >> "$GITHUB_OUTPUT"
          cat /tmp/email_body.txt >> "$GITHUB_OUTPUT"
          echo "" >> "$GITHUB_OUTPUT"
          echo "EOF" >> "$GITHUB_OUTPUT"

      - name: Send email
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: ${{ secrets.SMTP_HOST }}
          server_port: ${{ secrets.SMTP_PORT }}
          username: ${{ secrets.SMTP_USER }}
          password: ${{ secrets.SMTP_PASSWORD }}
          subject: "⚽ 世界杯预测 ${{ steps.format.outputs.subject }}"
          to: ${{ secrets.EMAIL_TO }}
          from: ${{ secrets.SMTP_USER }}
          html_body: |
            <pre style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            ${{ steps.format.outputs.body }}
            </pre>
```

## 关键设计点

1. **JSON 解析**：`predict_wc.py` 的 stderr 有 log 行（`[predict] ...`），stdout 最后才是 JSON。必须按 `{` 开头找 JSON 起始行，不能直接 `json.loads(sys.stdin.read())`。**最稳健做法**：找到 `{` 开头的行后，用 `json.JSONDecoder().raw_decode('\n'.join(lines[i:]))` 只解析第一个 JSON 对象，忽略尾部可能残留的日志数据。
2. **邮件正文**：用 `<pre>` 标签保留等宽字体排版，避免 HTML 渲染破坏格式。
3. **Secrets**：5 个 secret 全部在 GitHub 仓库 Settings → Secrets → Actions 中配置，不要硬编码。
4. **时区**：GitHub Actions runner 是 UTC，所有时间显示需手动 +8 小时格式化。
5. **零依赖**：`predict_wc.py` 只用 stdlib（`urllib.request` + `json` + `gzip` + `math`），无需 `pip install requests`，也无需 `requirements.txt`。
