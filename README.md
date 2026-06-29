# World Cup Predict — GitHub Action 版

2026 世界杯预测 + 自动回填 + 复盘一体化。每日 16:35 BJT 跑一次（cron `35 8 * * *` UTC）。

## 与原 cron 版的区别

| 项目 | 原 cron (Hermes) | GHA 版 |
|------|-----------------|--------|
| 执行引擎 | Hermes agent + Python | 纯 Python |
| 模型依赖 | LongCat-2.0-Preview | 无（纯计算） |
| 推送渠道 | 飞书 | 邮件（可改） |
| 触发方式 | Hermes cron | GitHub Actions schedule |
| 依赖 | Hermes 环境 + sidecar | 仅 requests |

## 本地测试

```bash
pip install requests
python scripts/predict_wc.py
```

## GitHub Secrets 配置

在仓库 Settings → Secrets → Actions 中添加：

| Secret | 说明 |
|--------|------|
| `SMTP_HOST` | SMTP 服务器地址（如 `smtp.qq.com`） |
| `SMTP_PORT` | SMTP 端口（如 `587`） |
| `SMTP_USER` | 发件邮箱 |
| `SMTP_PASSWORD` | 授权码/密码 |
| `EMAIL_TO` | 收件邮箱 |

## 手动触发

GitHub 仓库页面 → Actions → World Cup Predict → Run workflow
