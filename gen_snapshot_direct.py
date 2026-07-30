# -*- coding: utf-8 -*-
import json, os
from datetime import datetime, timezone, timedelta

# Prices from westock
prices = {
    '600585.SH': 18.58, '09926.HK': 93.70, '06855.HK': 34.34,
    'LEGN.US': 18.85, 'SMMT.US': 12.80, '00696.HK': 8.69,
    'PDD.US': 88.32, 'SY.US': 1.94, '06049.HK': 28.32,
    '02669.HK': 3.47, '87001.HK': 0.38, '03613.HK': 6.90
}

positions_data = [
    {'market':'CN','currency':'CNY','name':'海螺水泥','code':'600585.SH','cost_price':19.7,'qty':46200,'invested':912000,'fx':1.0},
    {'market':'HK','currency':'HKD','name':'康方生物','code':'09926.HK','cost_price':96.4,'qty':7000,'invested':582000,'fx':0.86},
    {'market':'HK','currency':'HKD','name':'亚盛医药','code':'06855.HK','cost_price':36.2,'qty':10000,'invested':312000,'fx':0.86},
    {'market':'US','currency':'USD','name':'传奇生物','code':'LEGN.US','cost_price':20.2,'qty':800,'invested':109000,'fx':6.78},
    {'market':'US','currency':'USD','name':'SMMT','code':'SMMT.US','cost_price':14.6,'qty':600,'invested':59000,'fx':6.78},
    {'market':'US','currency':'USD','name':'SMMT Call 270115','code':None,'cost_price':None,'qty':0,'invested':14000,'fx':6.78},
    {'market':'HK','currency':'HKD','name':'中国民航','code':'00696.HK','cost_price':10.0,'qty':14000,'invested':121000,'fx':0.86},
    {'market':'US','currency':'USD','name':'PDD','code':'PDD.US','cost_price':78.0,'qty':150,'invested':79000,'fx':6.78},
    {'market':'US','currency':'USD','name':'新氧','code':'SY.US','cost_price':1.8,'qty':5000,'invested':61000,'fx':6.78},
    {'market':'HK','currency':'HKD','name':'保利物业','code':'06049.HK','cost_price':40.8,'qty':1600,'invested':56000,'fx':0.86},
    {'market':'HK','currency':'HKD','name':'中海物业','code':'02669.HK','cost_price':4.5,'qty':15000,'invested':59000,'fx':0.86},
    {'market':'HK','currency':'HKD','name':'汇贤产业信托','code':'87001.HK','cost_price':0.42,'qty':120000,'invested':43000,'fx':0.86},
    {'market':'HK','currency':'HKD','name':'同仁堂国药','code':'03613.HK','cost_price':10.3,'qty':2000,'invested':18000,'fx':0.86},
]

holdings = []
total_inv = 0
total_cur = 0

for p in positions_data:
    code = p['code']
    qty = p['qty']
    inv = p['invested']
    fx = p['fx']
    live_price = prices.get(code) if code else None

    if live_price and qty:
        cur = round(qty * live_price * fx, 2)
    else:
        cur = inv

    pnl_val = round(cur - inv, 2)
    roi_val = round(pnl_val / inv * 100, 4) if inv else None

    cost_raw = None
    if p['cost_price']:
        if p['market'] == 'CN':
            cost_raw = f"¥{p['cost_price']}"
        elif p['market'] == 'HK':
            cost_raw = f"HK${p['cost_price']}"
        else:
            cost_raw = f"${p['cost_price']}"

    holdings.append({
        'market': p['market'],
        'currency': p['currency'],
        'name': p['name'],
        'code': code,
        'cost_price_raw': cost_raw,
        'current_price_raw': str(live_price) if live_price else None,
        'cost_price': p['cost_price'],
        'current_price': live_price,
        'quantity': qty,
        'invested': inv,
        'current': cur,
        'pnl': pnl_val,
        'roi': roi_val,
        'dividends': None,
        'pos_cost_pct': None,
        'pos_curr_pct': None,
    })
    total_inv += inv
    total_cur += cur

for h in holdings:
    h['pos_cost_pct'] = round(h['invested']/total_inv*100, 4) if total_inv else None
    h['pos_curr_pct'] = round(h['current']/total_cur*100, 4) if total_cur else None

pnl = round(total_cur - total_inv, 2)
roi = round(pnl / total_inv * 100, 4) if total_inv else None

cn_inv = sum(h['invested'] for h in holdings if h['market']=='CN')
cn_cur = sum(h['current'] for h in holdings if h['market']=='CN')
ov_inv = sum(h['invested'] for h in holdings if h['market'] in ('HK','US'))
ov_cur = sum(h['current'] for h in holdings if h['market'] in ('HK','US'))

tz = timezone(timedelta(hours=8))
now = datetime.now(tz)

snapshot = {
    'date': now.strftime('%Y-%m-%d'),
    'snapshot_time': now.strftime('%Y-%m-%d %H:%M:%S +08:00'),
    'source': 'westock-mcp 实时行情',
    'file_id': 'fGemVXqsvRGM',
    'doc_date': '2026-07-30',
    'exchange_rates': {'US': 6.78, 'HK': 0.86},
    'summary': {
        'holdings_pos_cost_pct': 100.0,
        'holdings_pos_curr_pct': 100.0,
        'holdings_roi': roi,
        'holdings_invested': total_inv,
        'holdings_current': total_cur,
        'holdings_pnl': pnl,
        'holdings_dividends': None,
        'year_start': None,
        'salary_surplus': None,
        'base': None,
        'total_pnl': None,
        'total_roi': None,
        'regions': {
            '整体': {'invested': total_inv, 'current': total_cur, 'pnl': pnl},
            '国内': {'invested': cn_inv, 'current': cn_cur, 'pnl': round(cn_cur-cn_inv, 2)},
            '境外': {'invested': ov_inv, 'current': ov_cur, 'pnl': round(ov_cur-ov_inv, 2)},
        }
    },
    'holdings': holdings,
}

script_dir = os.path.dirname(os.path.abspath(__file__))
out_dir = os.path.join(script_dir, 'portfolio_snapshots')
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, f'{snapshot["date"]}.json')
with open(out_file, 'w', encoding='utf-8') as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)

s = snapshot['summary']
print(f'[OK] {out_file}')
print(f'     持仓: {len(holdings)}只 | 投入: {s["holdings_invested"]/10000:.1f}万 | 当前: {s["holdings_current"]/10000:.1f}万')
print(f'     收益: {s["holdings_pnl"]/10000:+.1f}万 ({s["holdings_roi"]:+.2f}%)')

# Print individual holdings
for h in holdings:
    if h['code']:
        print(f"  {h['name']:12s} {h['code']:12s} 成本{h['cost_price']} → 现价{h['current_price']} | {h['roi']:+.2f}%")
    else:
        print(f"  {h['name']:12s} {'(期权)':12s} 投入{h['invested']} | {h['roi']:+.2f}%")
