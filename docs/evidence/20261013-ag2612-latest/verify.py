"""Offline verification of this archived SimNow round trip; never connects or trades."""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TERMINAL = {'0', '2', '4', '5'}


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


def verify():
    events = [json.loads(line) for line in (ROOT/'trade/events.jsonl').read_text(encoding='utf-8').splitlines()]
    summary = read('trade/summary.json')
    snapshots = {name: read('trade/'+name+'.json') for name in ('initial', 'after_open', 'final', 'final_repeat')}
    checks = {}
    # Reconstruct each complete query from raw callbacks, including its terminal response.
    queries = {}
    methods = {'reqQryInvestorPosition': 'position_query', 'reqQryOrder': 'order_query', 'reqQryTrade': 'trade_query'}
    for request in (e for e in events if e['event']=='request' and e.get('method') in methods):
        responses = [e for e in events if e['event']==methods[request['method']] and e['request_id']==request['request_id']]
        complete = bool(responses and responses[-1]['last'] and not request['return_code'] and all(e['error_id']==0 for e in responses))
        queries[request['request_id']] = (request, responses, complete)
    checks['all_account_and_trade_queries_complete'] = bool(queries) and all(q[2] for q in queries.values())
    totals = {}
    for name, snap in snapshots.items():
        matches = bool(snap['queries_complete'])
        for field, method in (('positions', 'reqQryInvestorPosition'), ('orders', 'reqQryOrder')):
            candidates = [q for q in queries.values() if q[0]['method']==method and q[0]['at']<=snap['at']]
            q = max(candidates, key=lambda q: q[0]['request_id'])
            matches &= q[2] and q[1][-1]['at']<=snap['at'] and [e['data'] for e in q[1] if e['data']]==snap[field]
        gross = sum(abs(int(r['Position'])) for r in snap['positions'])
        active = sum(r['OrderStatus'] not in TERMINAL for r in snap['orders'])
        checks[name+'_matches_raw_queries'] = bool(matches and gross==snap['gross_position'] and active==snap['active_order_count'])
        totals[name] = {'at': snap['at'], 'gross_position': gross, 'active_orders': active}
    checks['initial_and_both_final_zero'] = all(totals[n]['gross_position']==totals[n]['active_orders']==0 for n in ('initial','final','final_repeat'))
    checks['open_long_today_one'] = totals['after_open']['gross_position']==1 and any(r['InstrumentID']=='ag2612' and r['PosiDirection']=='2' and r['Position']==r['TodayPosition']==1 for r in snapshots['after_open']['positions'])
    checks['second_final_query_later'] = datetime.fromisoformat(snapshots['final_repeat']['at'])-datetime.fromisoformat(snapshots['final']['at']) >= timedelta(seconds=2)
    sessions = [e['data'] for e in events if e['event']=='td_login' and e['error_id']==0]
    intents = [e['data'] for e in events if e['event']=='order_intent']
    checks['one_trading_session'] = len(sessions)==1
    session = sessions[0]
    keys = {(session['FrontID'],session['SessionID'],r['OrderRef']) for r in intents}
    orders = [r for r in snapshots['final_repeat']['orders'] if (r['FrontID'],r['SessionID'],r['OrderRef']) in keys]
    checks['exactly_two_owned_filled_orders'] = len(orders)==len(intents)==2 and all(r['InstrumentID']=='ag2612' and r['OrderStatus']=='0' and r['VolumeTraded']==1 and r['VolumeTotal']==0 for r in orders)
    ids = {(r['ExchangeID'],r['OrderSysID']) for r in orders}
    trades = {(e['data']['ExchangeID'],e['data']['TradeID'],e['data']['TradingDay']):e['data'] for e in events if e['event']=='trade_query' and e['data'].get('TradeID') and (e['data']['ExchangeID'],e['data']['OrderSysID']) in ids}
    trades = list(trades.values())
    checks['buy_open_one_sell_close_today_one'] = len(trades)==2 and sum(r['Volume'] for r in trades if r['Direction']=='0' and r['OffsetFlag']=='0')==1 and sum(r['Volume'] for r in trades if r['Direction']=='1' and r['OffsetFlag']=='3')==1 and all(r['InstrumentID']=='ag2612' for r in trades)
    checks['saved_trades_equal_server_query'] = trades==read('trade/own_trades.json')
    ticks = [e for e in events if e['event']=='tick']
    freshness = []
    for tick in ticks:
        d = tick['data']; received = datetime.fromisoformat(tick['at'])
        market = datetime.strptime(d['ActionDay']+' '+d['UpdateTime'], '%Y%m%d %H:%M:%S').replace(tzinfo=received.tzinfo)+timedelta(milliseconds=d['UpdateMillisec'])
        freshness.append((received-market).total_seconds())
    checks['fresh_advancing_market_ticks'] = len(ticks)==summary['market_ticks'] and len(ticks)>1 and all(-5<=age<=10 for age in freshness) and ticks[-1]['data']['Volume']>ticks[0]['data']['Volume']
    checks['no_disconnect_or_failure'] = not any(e['event'] in {'td_disconnected','md_disconnected','failure'} or e.get('error_id',0) for e in events)
    checks['finished_passed_simulation'] = summary['finished'] and summary['simulation'] and summary['execute'] and summary['status']=='passed' and summary['trading_acceptance_passed']
    checks['processes_exited'] = all(p['process_exited'] for p in read('trade/process_exit_check.json'))
    sha = hashlib.sha256((ROOT/'source/acceptance.py').read_bytes()).hexdigest()
    checks['source_bound_to_run_and_tests'] = sha==read('trade/manifest.json')['source_sha256']==read('provenance.json')['acceptance_sha256']==read('source/local_checks_before_run.json')['source_sha256']['scripts/simnow/acceptance.py']
    checks['archive_hashes_match'] = all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected for name,expected in read('SHA256SUMS.json').items())
    return {'passed': all(checks.values()), 'checks': checks, 'snapshots': totals, 'trades': trades, 'market_ticks': len(ticks), 'max_market_age_seconds': max(freshness), 'scope': 'This run: position round trip only; independent-client comparison was not repeated.'}


if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
