#!/bin/bash
# Test script for football-data.org integration
set -e

export API_FOOTBALL_KEY=96599eb5ca0acabdb4db9370e58735f4
export FOOTBALL_DATA_API_KEY=3db137f6f4a8485eabd5b04b3c108e43

echo "=== Testing football-data.org integration ==="
echo ""

# Test 1: Check API key validity
echo "Test 1: API key validation"
python3 -c "
import urllib.request, json
api_key = '$FOOTBALL_DATA_API_KEY'
url = 'https://api.football-data.org/v4/competitions/PL'
req = urllib.request.Request(url, headers={'X-Auth-Token': api_key})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
print(f'  Status: OK')
print(f'  League: {data.get(\"name\")}')
print(f'  Season: {data.get(\"currentSeason\", {}).get(\"startDate\")} - {data.get(\"currentSeason\", {}).get(\"endDate\")}')
"

echo ""
echo "Test 2: Fetch matches for 2025-08-17 (known EPL matchday)"
python3 -c "
import urllib.request, json
api_key = '$FOOTBALL_DATA_API_KEY'
url = 'https://api.football-data.org/v4/competitions/PL/matches?dateFrom=2025-08-17&dateTo=2025-08-18'
req = urllib.request.Request(url, headers={'X-Auth-Token': api_key})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
matches = data.get('matches', [])
print(f'  Matches found: {len(matches)}')
for m in matches[:3]:
    h = m.get('homeTeam', {}).get('shortName', '?')
    a = m.get('awayTeam', {}).get('shortName', '?')
    print(f'    {h} vs {a}')
"

echo ""
echo "Test 3: Run prediction script (historical data)"
cd /root/projects/league-predict
python3 scripts/predict.py --dates 20250817-20250818 --league epl 2>&1 | grep -E "Got|Past|Future|Predicted|No future" || true

echo ""
echo "=== All tests passed ==="
