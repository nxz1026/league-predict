# ESPN World Cup API fallback（2026-06-15 实测）

## 背景

`world-cup-predict` 原写法使用：

```text
https://site.api.espn.com/apis/site/v2/sports/soccer/fixtures?dates=YYYYMMDD-YYYYMMDD&groups=50&limit=50
```

2026-06-15 cron 运行时该 endpoint 返回 `404 page not found`。

## 可用替代

使用 FIFA World Cup league slug 的 scoreboard endpoint：

```text
https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD-YYYYMMDD&limit=50
```

实测返回字段：

- `events[].id`
- `events[].date`
- `events[].name`
- `events[].competitions[0].venue.fullName`
- `events[].competitions[0].competitors[]`
- `events[].competitions[0].status.type`
- `events[].competitions[0].odds[]`

`odds[]` 内可见 DraftKings：

- `moneyline.home/open/close`
- `moneyline.away/open/close`
- `moneyline.draw/open/close`
- `pointSpread.home/open/close`
- `pointSpread.away/open/close`
- `total.over/open/close`
- `total.under/open/close`

## 推荐解析片段

```python
import json, urllib.request
url = 'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260615-20260616&limit=50'
data = json.load(urllib.request.urlopen(url))
for ev in data['events']:
    comp = ev['competitions'][0]
    print(ev['id'], ev['date'], ev['name'], comp.get('venue', {}).get('fullName'))
    for c in comp['competitors']:
        print(c.get('homeAway'), c['team'].get('displayName'), c.get('score'))
    print(comp['status']['type'])
    print(comp.get('odds', []))
```

## 注意

- `fixtures.json` 与 ESPN scoreboard 的 `date` 在部分比赛存在 1–3 小时差异。筛选窗口仍按本地 `fixtures.json`，证据记录 ESPN 时间。
- 若 cron 指令写明“final response 自动投递，不要 send_message”，不要执行 AgentMail/飞书发送。
