# Country Codes — 中英文映射

> 2026 世界杯 48 队 + 常见国家队。来源：FIFA + ESPN + 维基百科。维护：手动编辑，可被任何体育预测 skill 复用。

## 为什么独立成 reference

- **体积大**：130+ 队映射，单文件 4KB
- **可复用**：足球/篮球/橄榄球等所有体育预测 skill 都需要
- **不动算法**：仅是数据查找表，与 predict_wc.py 算法逻辑解耦
- **LLM 不需要每次都吃这表**：predict_wc.py 用 `to_cn()` 在 Python 层转换后输出，无需 LLM 查表

## 当前映射（130+ 队）

### 欧洲 (UEFA)

| 英文 | 中文 |
|------|------|
| Albania | 阿尔巴尼亚 |
| Austria | 奥地利 |
| Belgium | 比利时 |
| Bosnia-Herzegovina | 波黑 |
| Bosnia and Herzegovina | 波黑 |
| Bulgaria | 保加利亚 |
| Croatia | 克罗地亚 |
| Cyprus | 塞浦路斯 |
| Czechia | 捷克 |
| Czech Republic | 捷克 |
| Denmark | 丹麦 |
| England | 英格兰 |
| Estonia | 爱沙尼亚 |
| Finland | 芬兰 |
| France | 法国 |
| Georgia | 格鲁吉亚 |
| Germany | 德国 |
| Gibraltar | 直布罗陀 |
| Greece | 希腊 |
| Hungary | 匈牙利 |
| Iceland | 冰岛 |
| Ireland | 爱尔兰 |
| Italy | 意大利 |
| Kosovo | 科索沃 |
| Latvia | 拉脱维亚 |
| Liechtenstein | 列支敦士登 |
| Lithuania | 立陶宛 |
| Luxembourg | 卢森堡 |
| North Macedonia | 北马其顿 |
| Malta | 马耳他 |
| Moldova | 摩尔多瓦 |
| Monaco | 摩纳哥 |
| Montenegro | 黑山 |
| Netherlands | 荷兰 |
| Norway | 挪威 |
| Poland | 波兰 |
| Portugal | 葡萄牙 |
| Romania | 罗马尼亚 |
| Russia | 俄罗斯 |
| Scotland | 苏格兰 |
| Serbia | 塞尔维亚 |
| Slovakia | 斯洛伐克 |
| Slovenia | 斯洛文尼亚 |
| Spain | 西班牙 |
| Sweden | 瑞典 |
| Switzerland | 瑞士 |
| Türkiye | 土耳其 |
| Turkey | 土耳其 |
| Ukraine | 乌克兰 |
| Wales | 威尔士 |

### 美洲 (CONMEBOL + CONCACAF)

| 英文 | 中文 |
|------|------|
| Argentina | 阿根廷 |
| Bolivia | 玻利维亚 |
| Brazil | 巴西 |
| Canada | 加拿大 |
| Chile | 智利 |
| Colombia | 哥伦比亚 |
| Costa Rica | 哥斯达黎加 |
| Cuba | 古巴 |
| Curaçao | 库拉索 |
| Curacao | 库拉索 |
| Dominican Republic | 多米尼加 |
| Ecuador | 厄瓜多尔 |
| El Salvador | 萨尔瓦多 |
| Grenada | 格林纳达 |
| Guatemala | 危地马拉 |
| Guyana | 圭亚那 |
| Haiti | 海地 |
| Honduras | 洪都拉斯 |
| Jamaica | 牙买加 |
| Mexico | 墨西哥 |
| Nicaragua | 尼加拉瓜 |
| Panama | 巴拿马 |
| Paraguay | 巴拉圭 |
| Peru | 秘鲁 |
| Suriname | 苏里南 |
| Trinidad and Tobago | 特立尼达和多巴哥 |
| United States | 美国 |
| USA | 美国 |
| Uruguay | 乌拉圭 |
| Venezuela | 委内瑞拉 |

### 亚洲 (AFC)

| 英文 | 中文 |
|------|------|
| Afghanistan | 阿富汗 |
| Australia | 澳大利亚 |
| Bahrain | 巴林 |
| Bangladesh | 孟加拉国 |
| China | 中国 |
| China PR | 中国 |
| Chinese Taipei | 中国台北 |
| Hong Kong | 中国香港 |
| Macao | 中国澳门 |
| Taiwan | 中国台北 |
| India | 印度 |
| Indonesia | 印度尼西亚 |
| Iran | 伊朗 |
| Iraq | 伊拉克 |
| Israel | 以色列 |
| Japan | 日本 |
| Jordan | 约旦 |
| Kazakhstan | 哈萨克斯坦 |
| Korea DPR | 朝鲜 |
| North Korea | 朝鲜 |
| Korea Republic | 韩国 |
| South Korea | 韩国 |
| Kuwait | 科威特 |
| Kyrgyzstan | 吉尔吉斯斯坦 |
| Laos | 老挝 |
| Lebanon | 黎巴嫩 |
| Malaysia | 马来西亚 |
| Maldives | 马尔代夫 |
| Myanmar | 缅甸 |
| Nepal | 尼泊尔 |
| Oman | 阿曼 |
| Pakistan | 巴基斯坦 |
| Palestine | 巴勒斯坦 |
| Philippines | 菲律宾 |
| Qatar | 卡塔尔 |
| Saudi Arabia | 沙特 |
| Singapore | 新加坡 |
| Sri Lanka | 斯里兰卡 |
| Syria | 叙利亚 |
| Tajikistan | 塔吉克斯坦 |
| Thailand | 泰国 |
| Turkmenistan | 土库曼斯坦 |
| United Arab Emirates | 阿联酋 |
| Uzbekistan | 乌兹别克斯坦 |
| Vietnam | 越南 |
| Yemen | 也门 |

### 非洲 (CAF)

| 英文 | 中文 |
|------|------|
| Algeria | 阿尔及利亚 |
| Angola | 安哥拉 |
| Benin | 贝宁 |
| Botswana | 博茨瓦纳 |
| Burkina Faso | 布基纳法索 |
| Burundi | 布隆迪 |
| Cameroon | 喀麦隆 |
| Cape Verde | 佛得角 |
| Chad | 乍得 |
| Comoros | 科摩罗 |
| Congo | 刚果 |
| Congo DR | 刚果(金) |
| DR Congo | 刚果(金) |
| Djibouti | 吉布提 |
| Egypt | 埃及 |
| Eswatini | 斯威士兰 |
| Ethiopia | 埃塞俄比亚 |
| Gabon | 加蓬 |
| Gambia | 冈比亚 |
| Ghana | 加纳 |
| Guinea | 几内亚 |
| Guinea-Bissau | 几内亚比绍 |
| Ivory Coast | 科特迪瓦 |
| Cote d'Ivoire | 科特迪瓦 |
| Kenya | 肯尼亚 |
| Lesotho | 莱索托 |
| Liberia | 利比里亚 |
| Libya | 利比亚 |
| Madagascar | 马达加斯加 |
| Malawi | 马拉维 |
| Mali | 马里 |
| Mauritania | 毛里塔尼亚 |
| Mauritius | 毛里求斯 |
| Morocco | 摩洛哥 |
| Mozambique | 莫桑比克 |
| Namibia | 纳米比亚 |
| Niger | 尼日尔 |
| Nigeria | 尼日利亚 |
| Rwanda | 卢旺达 |
| Senegal | 塞内加尔 |
| Sierra Leone | 塞拉利昂 |
| Somalia | 索马里 |
| South Africa | 南非 |
| South Sudan | 南苏丹 |
| Sudan | 苏丹 |
| Tanzania | 坦桑尼亚 |
| Togo | 多哥 |
| Tunisia | 突尼斯 |
| Uganda | 乌干达 |
| Zambia | 赞比亚 |
| Zimbabwe | 津巴布韦 |

### 大洋洲 (OFC)

| 英文 | 中文 |
|------|------|
| Faroe Islands | 法罗群岛 |
| Fiji | 斐济 |
| New Caledonia | 新喀里多尼亚 |
| New Zealand | 新西兰 |
| Solomon Islands | 所罗门群岛 |
| Tahiti | 塔希提 |

## 在 Python 中使用（predict_wc.py 当前用法）

```python
# 字典形式（与 predict_wc.py 同步）
COUNTRY_CN = {
    "Afghanistan": "阿富汗", "Albania": "阿尔巴尼亚", ...
}

def to_cn(name):
    if not name:
        return name
    return COUNTRY_CN.get(name, COUNTRY_CN.get(name.replace("'", ""), name))

# ESPN event 转换: "Away at Home" → "客队 vs 主队"
en_name = "South Africa at Czechia"
away_en, home_en = en_name.split(" at ", 1)
cn_name = f"{to_cn(away_en)} vs {to_cn(home_en)}"
# → "南非 vs 捷克"
```

## 已知坑

- **"Czechia" ≠ "Czech Republic"**：ESPN 现在用 "Czechia"，FIFA 早期用 "Czech Republic"。两者都映射到"捷克"。
- **"Türkiye" vs "Turkey"**：ESPN 2022 起改用带变音符的 "Türkiye"，FIFA 老文件用 "Turkey"。两者都映射到"土耳其"。
- **"United States" vs "USA"**：ESPN 偶尔用全称，FIFA 用缩写。两者都映射到"美国"。
- **"Korea Republic" vs "South Korea"**：ESPN 有时用 FIFA 官方名 "Korea Republic"。两者都映射到"韩国"。

## 维护

- 新增国家：直接在本文件 + predict_wc.py 的 COUNTRY_CN 字典中同步添加
- 重命名（如某队改国号）：两边同步更新
- 删除：从映射移除（但保留 ESPN 兜底逻辑，未识别回退原文）

## 复用此 reference

任何新体育预测 skill（basketball-prediction, nfl-prediction 等）：
1. 复制本文件到新 skill 的 `references/` 下
2. 复制 `to_cn()` 函数或扩展它
3. 在 SKILL.md 引用 `references/country-codes.md`
