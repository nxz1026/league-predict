# Real ESPN API Response — 2026-06-18 Test Run

Captured during cron test on 2026-06-18 02:04 UTC. Documents what the API actually
returns for line movement analysis.

## Test Setup

```bash
curl -s "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260616-20260618&limit=50" -o /tmp/espn_wc.json
python3 /root/.hermes/skills/productivity/world-cup-predict/scripts/parse_espn.py
```

## Completed Matches (Backfill)

| Match | Score | Notes |
|-------|-------|-------|
| Austria vs Jordan | 3-1 | Home win |
| Portugal vs Congo DR | 1-1 | Draw |
| England vs Croatia | 4-2 | Home win |
| Ghana vs Panama | 1-0 | Home win |

Calibration: 75% home win, 25% draw, 0% away win (small sample).

## DraftKings Odds Structure (Real)

### Czechia vs South Africa
- Details: `CZE -125`
- Draw ML: `265`
- Spread home: open=`-110` close=`-125` (line -0.5) → **movement: -15, moderate strength**
- Spread away: open=`-125` close=`+100` (line +0.5)
- Total over: open=`+130` close=`+110` (line o2.5)
- Total under: open=`-165` close=`-135` (line u2.5)

### Switzerland vs Bosnia-Herzegovina
- Details: `SUI -180`
- Draw ML: `310`
- Spread home: open=`+135` close=`-185` (line changed -1.5→-0.5) → **MAJOR movement: -320!**
- Total over: open=`+100` close=`+100` (no movement)
- Total under: open=`-125` close=`-125` (no movement)

### Canada vs Qatar
- Details: `CAN -360`
- Draw ML: `475`
- Spread home: open=`+125` close=`-125` (line -1.5) → **movement: -250, very strong**
- Total over: open=`+110` close=`-145` → flipped from over-favorable to over-unfavorable
- Total under: open=`-140` close=`+120` → flipped

### Mexico vs South Korea
- Details: `MEX +105`
- Draw ML: `230`
- Spread home: open=`-135` close=`-105` (line -0.5) → **movement: +30, weakening**
- Spread away: open=`+100` close=`-125` → flipped to favor Korea
- Total over: open=`+120` close=`+140` (weak over interest)
- Total under: open=`-150` close=`-170` (under getting heavier)

## Key Patterns Observed

1. **Line movement can be dramatic**: SUI -1.5→-0.5 changed from +135 to -185 in spread odds
2. **Total flipping**: Canada-Qatar total over/under both flipped sign (+110→-145, -140→+120)
3. **Low-draw odds matches** (Canada -360, SUI -180) imply low draw probability despite historical 50% draw rate
4. **Moneyline `details` field** only shows close line, not open
5. **OverUnder line** is sometimes just a float (2.5) - paired with `total.under/over` odds
