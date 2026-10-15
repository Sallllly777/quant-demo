"""Recompute acceptance from completed server-query and independent-client evidence."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
TERMINAL = {'0', '2', '4', '5'}
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def signature(last, bid, ask, volume, bid_volume, ask_volume):
    return tuple(float(v) for v in (last, bid, ask, volume, bid_volume, ask_volume))
def market_key(day, clock, ms):
    dt = datetime.strptime(day + ' ' + clock, '%Y%m%d %H:%M:%S').replace(tzinfo=TZ)
    return (dt + timedelta(milliseconds=int(ms))).isoformat(timespec='milliseconds')
def own_orders(events, queried):
    sessions=[e['data'] for e in events if e['event']=='td_login' and not e.get('error_id') and e['data'].get('SessionID') is not None]
    if len(sessions)!=1: raise ValueError('Require exactly one successful trading session')
    session=sessions[0]
    refs={e['data']['OrderRef'] for e in events if e['event']=='order_intent'}
    keys={(session['FrontID'],session['SessionID'],ref) for ref in refs}
    return [r for r in queried if (r.get('FrontID'),r.get('SessionID'),r.get('OrderRef')) in keys and r.get('InstrumentID')=='ag2612']
def compare_reference(reference_path, observations):
    reference = {}
    for line in reference_path.read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if r['symbol'] != 'ag2612': raise ValueError('Unexpected reference symbol')
        reference.setdefault(r['market_at'], set()).add(signature(r['last'], r['bid'], r['ask'], r['volume'], r['bid_volume'], r['ask_volume']))
    pairs = []
    for key, sig in observations:
        exists = key in reference
        pairs.append({'market_at': key, 'observed': sig, 'reference': sorted(reference.get(key, [])),
                      'timestamp_matched': exists, 'six_fields_equal': exists and sig in reference[key]})
    return {'observations': len(pairs), 'timestamp_matches': sum(p['timestamp_matched'] for p in pairs),
            'equal_six_fields': sum(p['six_fields_equal'] for p in pairs),
            'differences': sum(p['timestamp_matched'] and not p['six_fields_equal'] for p in pairs),
            'unmatched': sum(not p['timestamp_matched'] for p in pairs), 'pairs': pairs}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--trade', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--capture', type=Path, action='append', default=[])
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reference_summary = read(args.reference/'reference_summary.json')
    if not reference_summary.get('finished'):
        finalized = json.loads((args.reference/'finalization.json').read_text(encoding='utf-8-sig'))
        if not finalized.get('process_exited'): raise ValueError('Reference client still running')
    summary = read(args.trade/'summary.json')
    if not summary['finished']: raise ValueError('Trade run unfinished')
    initial, after_open, final, repeat = [read(args.trade/(n+'.json')) for n in ('initial','after_open','final','final_repeat')]
    if not all(s['queries_complete'] for s in (initial,after_open,final,repeat)): raise ValueError('Queries incomplete')
    def gross(s): return sum(abs(int(r.get('Position', 0))) for r in s['positions'])
    def live(s): return sum(r.get('OrderStatus') not in TERMINAL for r in s['orders'])
    events = [json.loads(l) for l in (args.trade/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    intents = [e['data'] for e in events if e['event']=='order_intent']
    orders = own_orders(events, repeat['orders'])
    ids = {(r['ExchangeID'],r['OrderSysID']) for r in orders}
    trade_query = [e['data'] for e in events if e['event']=='trade_query' and e['data'].get('TradeID')]
    dedup = {(r['ExchangeID'],r['TradeID'],r['TradingDay']):r for r in trade_query if (r['ExchangeID'],r['OrderSysID']) in ids}
    trades = list(dedup.values())
    buy = sum(r['Volume'] for r in trades if r['Direction']=='0' and r['OffsetFlag']=='0')
    close = sum(r['Volume'] for r in trades if r['Direction']=='1' and r['OffsetFlag']=='3')
    checks = {'td_no_disconnect':not any(e['event']=='td_disconnected' for e in events),
              'initial_zero': gross(initial)==0 and live(initial)==0,
              'open_long_one': gross(after_open)==1 and any(r.get('InstrumentID')=='ag2612' and r.get('PosiDirection')=='2' and r.get('TodayPosition')==1 for r in after_open['positions']),
              'buy_open_one_filled': buy==1, 'sell_close_today_one_filled':close==1,
              'final_zero': gross(final)==0 and live(final)==0,
              'repeat_zero':gross(repeat)==0 and live(repeat)==0,
              'own_orders_terminal':len(orders)==len(intents) and all(r['OrderStatus'] in TERMINAL for r in orders)}
    comparison = []
    for capture in args.capture:
        s = read(capture/'summary.json')
        if not s['finished']: raise ValueError('Capture unfinished')
        observations = []
        with (capture/'ticks.csv').open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                if r['InstrumentID']!='ag2612': raise ValueError('Unexpected capture symbol')
                observations.append((market_key(r['ActionDay'],r['UpdateTime'],r['UpdateMillisec']), signature(r['LastPrice'],r['BidPrice1'],r['AskPrice1'],r['Volume'],r['BidVolume1'],r['AskVolume1'])))
        result = compare_reference(args.reference/'reference_ticks.jsonl', observations)
        result['capture_directory'] = capture.name
        comparison.append(result)
    checks['reference_client_compared'] = bool(comparison and all(r['timestamp_matches']>=2 and r['differences']==0 and r['unmatched']==0 for r in comparison))
    checks['reference_screenshot_present'] = (args.reference/'client.png').is_file()
    result = {'generated_at':datetime.now(TZ).isoformat(), 'symbol':'ag2612', 'simulation':True,
              'checks':checks, 'passed':all(checks.values()), 'trades':trades, 'comparisons':comparison,
              'reference_scope':'Separate installed VeighNa client process/connection, shared SimNow upstream; not an independent data vendor.',
              'screenshot_scope':'Market-data-only client; its empty order/position panels are NOT trading proof.',
              'artifacts':{}}
    paths = [args.trade/n for n in ('manifest.json','events.jsonl','summary.json','initial.json','after_open.json','final.json','final_repeat.json','own_trades.json')]
    paths += [args.reference/n for n in ('reference_ticks.jsonl','reference_summary.json','client.png','client_accessibility.txt')]
    if (args.reference/'finalization.json').exists(): paths.append(args.reference/'finalization.json')
    paths += [c/'ticks.csv' for c in args.capture]
    for path in paths:
        result['artifacts'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    (args.output/'validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'checks':checks,'comparisons':[{k:v for k,v in c.items() if k!='pairs'} for c in comparison]},ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
