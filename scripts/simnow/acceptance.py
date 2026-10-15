"""One-lot ag2612 SimNow acceptance; defaults to queries only, never real-money fronts."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from threading import Event, RLock
import time
from datetime import datetime, timedelta, timezone
from vnpy_ctp.api import MdApi, TdApi

TZ = timezone(timedelta(hours=8))
SYMBOL = 'ag2612'
TD_FRONT = 'tcp://182.254.243.31:30001'
MD_FRONT = 'tcp://182.254.243.31:30011'
TERMINAL = {'0', '2', '4', '5'}
FIELDS = set('InstrumentID ExchangeID OrderRef FrontID SessionID OrderSysID OrderStatus OrderSubmitStatus Direction CombOffsetFlag OffsetFlag VolumeTotalOriginal VolumeTraded VolumeTotal LimitPrice Price Volume TradeID TradeDate TradeTime InsertDate InsertTime CancelTime TradingDay ActionDay UpdateTime UpdateMillisec LastPrice BidPrice1 AskPrice1 BidVolume1 AskVolume1 UpperLimitPrice LowerLimitPrice PosiDirection PositionDate Position TodayPosition YdPosition LongFrozen ShortFrozen PriceTick VolumeMultiple IsTrading MinLimitOrderVolume MaxLimitOrderVolume'.split())

def now():
    return datetime.now(TZ).isoformat(timespec='milliseconds')

def safe(data):
    return {k: v for k, v in data.items() if k in FIELDS}

def active(row):
    return row.get('OrderStatus') not in TERMINAL

def exposure(rows):
    return sum(abs(int(r.get('Position', 0))) for r in rows)

def require_clean(positions, orders):
    if exposure(positions) or any(active(o) for o in orders):
        raise RuntimeError('account_not_empty_no_orders_sent')

def quote_price(tick, side, price_tick, received):
    if time.monotonic() - received > 3:
        raise RuntimeError('stale_received_quote')
    market = datetime.strptime(tick['ActionDay'] + ' ' + tick['UpdateTime'], '%Y%m%d %H:%M:%S').replace(tzinfo=TZ)
    market += timedelta(milliseconds=int(tick.get('UpdateMillisec', 0)))
    if not -5 <= (datetime.now(TZ) - market).total_seconds() <= 10:
        raise RuntimeError('stale_market_quote')
    bid, ask = float(tick['BidPrice1']), float(tick['AskPrice1'])
    lower, upper = float(tick['LowerLimitPrice']), float(tick['UpperLimitPrice'])
    if not all(math.isfinite(x) and 0 < x < 1e10 for x in (bid, ask, lower, upper, price_tick)):
        raise RuntimeError('invalid_quote')
    if not lower <= bid <= ask <= upper or ask - bid > 20 * price_tick:
        raise RuntimeError('invalid_book_or_spread')
    if int(tick.get('BidVolume1', 0)) < 1 or int(tick.get('AskVolume1', 0)) < 1:
        raise RuntimeError('empty_book')
    price = min(upper, ask + 2 * price_tick) if side == '0' else max(lower, bid - 2 * price_tick)
    return round(round(price / price_tick) * price_tick, 8)

class Journal:
    def __init__(self, output):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.file = (self.output / 'events.jsonl').open('a', encoding='utf-8')
    def event(self, event, **fields):
        with self.lock:
            self.file.write(json.dumps({'at': now(), 'event': event, **fields}, ensure_ascii=False) + '\n')
            self.file.flush()
    def save(self, name, data):
        with self.lock:
            p = self.output / name
            tmp = p.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            tmp.replace(p)

class Trading(TdApi):
    def __init__(self, journal, userid, password):
        super().__init__()
        self.j = journal
        self.userid, self.password = userid, password
        self.lock = RLock()
        self.connected = Event()
        self.pending = {}
        self.reqid = 0
        self.front = self.session = 0
        self.order_ref = 0
        self.orders, self.trades, self.owned = {}, {}, set()
        self.disconnects = 0
        self.last_query = 0.0
        self.created = False
        self.open_attempts = self.close_attempts = 0
    def onFrontConnected(self):
        self.j.event('td_connected')
        self.connected.set()
    def onFrontDisconnected(self, reason):
        self.disconnects += 1
        self.connected.clear()
        self.j.event('td_disconnected', reason=reason)
    def start(self):
        flow = self.j.output / 'td_flow'
        flow.mkdir(exist_ok=True)
        self.createFtdcTraderApi((str(flow) + os.sep).encode('gbk'), True)
        self.created = True
        self.subscribePrivateTopic(0)
        self.subscribePublicTopic(0)
        self.registerFront(TD_FRONT)
        self.init()
    def next_id(self):
        with self.lock:
            self.reqid += 1
            return self.reqid
    def rpc(self, method, request, timeout=20):
        if not self.connected.is_set():
            raise RuntimeError('td_not_connected')
        if method.startswith('reqQry'):
            time.sleep(max(0, 1.1 - (time.monotonic() - self.last_query)))
            self.last_query = time.monotonic()
        rid = self.next_id()
        pending = {'done': Event(), 'rows': [], 'error': 0}
        with self.lock:
            self.pending[rid] = pending
        result = getattr(self, method)(request, rid)
        self.j.event('request', method=method, request_id=rid, return_code=result)
        if result:
            self.pending.pop(rid, None)
            raise RuntimeError(f'{method}_local_{result}')
        if not pending['done'].wait(timeout):
            self.pending.pop(rid, None)
            raise RuntimeError(f'{method}_timeout_incomplete')
        self.pending.pop(rid, None)
        if pending['error']:
            raise RuntimeError(f'{method}_error_{pending["error"]}')
        return pending['rows']
    def response(self, kind, data, error, reqid, last):
        code = error.get('ErrorID', 0)
        clean = safe(data)
        self.j.event(kind, request_id=reqid, error_id=code, last=bool(last), data=clean)
        with self.lock:
            p = self.pending.get(reqid)
            if p is not None:
                if data:
                    p['rows'].append(data.copy())
                if code:
                    p['error'] = code
                if last or code:
                    p['done'].set()
    def onRspAuthenticate(self, d, e, r, last): self.response('authenticated', d, e, r, last)
    def onRspUserLogin(self, d, e, r, last):
        if not e.get('ErrorID'):
            self.front, self.session = d['FrontID'], d['SessionID']
            self.order_ref = max(self.order_ref, int(d.get('MaxOrderRef') or 0))
        self.response('td_login', d, e, r, last)
    def onRspSettlementInfoConfirm(self, d, e, r, last): self.response('settlement_confirmed', d, e, r, last)
    def onRspQryInstrument(self, d, e, r, last): self.response('instrument_query', d, e, r, last)
    def onRspQryInvestorPosition(self, d, e, r, last): self.response('position_query', d, e, r, last)
    def onRspQryOrder(self, d, e, r, last): self.response('order_query', d, e, r, last)
    def onRspQryTrade(self, d, e, r, last): self.response('trade_query', d, e, r, last)
    def onRspError(self, e, r, last): self.response('td_error', {}, e, r, last)
    def onRspOrderInsert(self, d, e, r, last):
        self.j.event('insert_response', request_id=r, error_id=e.get('ErrorID', 0), data=safe(d))
    def onErrRtnOrderInsert(self, d, e):
        self.j.event('insert_error', error_id=e.get('ErrorID', 0), data=safe(d))
    def onRspOrderAction(self, d, e, r, last):
        self.j.event('cancel_response', error_id=e.get('ErrorID', 0), data=safe(d))
    def onErrRtnOrderAction(self, d, e):
        self.j.event('cancel_error', error_id=e.get('ErrorID', 0), data=safe(d))
    def onRtnOrder(self, data):
        key = (data.get('FrontID'), data.get('SessionID'), data.get('OrderRef'))
        with self.lock:
            if key not in self.owned:
                return
            self.orders[key] = data.copy()
        self.j.event('own_order_return', data=safe(data))
    def onRtnTrade(self, data):
        if data.get('InstrumentID') != SYMBOL:
            return
        key = (data.get('ExchangeID'), data.get('TradeID'), data.get('TradingDay'))
        with self.lock:
            self.trades[key] = data.copy()
        self.j.event('symbol_trade_return', data=safe(data))
    def login(self):
        if not self.connected.wait(25):
            raise RuntimeError('td_connection_timeout')
        self.rpc('reqAuthenticate', {'UserID': self.userid, 'BrokerID': '9999', 'AppID': 'simnow_client_test', 'AuthCode': '0000000000000000'})
        self.rpc('reqUserLogin', {'UserID': self.userid, 'Password': self.password, 'BrokerID': '9999'})
        self.rpc('reqSettlementInfoConfirm', {'InvestorID': self.userid, 'BrokerID': '9999'})
    def query(self, method):
        return self.rpc(method, {'BrokerID': '9999', 'InvestorID': self.userid})
    def account_snapshot(self, name):
        positions = self.query('reqQryInvestorPosition')
        orders = self.query('reqQryOrder')
        result = {'at': now(), 'queries_complete': True, 'positions': [safe(p) for p in positions],
                  'orders': [safe(o) for o in orders], 'gross_position': exposure(positions),
                  'active_order_count': sum(active(o) for o in orders)}
        self.j.save(name + '.json', result)
        return result
    def submit(self, side, offset, price, execute):
        if not execute or not self.connected.is_set() or self.disconnects:
            raise RuntimeError('order_gate_closed')
        if side not in {'0', '1'} or offset not in {'0', '3'}:
            raise RuntimeError('invalid_order_intent')
        if (side, offset) == ('0', '0'):
            if self.open_attempts >= 1: raise RuntimeError('open_attempt_limit')
            self.open_attempts += 1
        elif (side, offset) == ('1', '3'):
            if self.close_attempts >= 5: raise RuntimeError('close_attempt_limit')
            self.close_attempts += 1
        else:
            raise RuntimeError('invalid_order_intent')
        self.order_ref += 1
        ref = str(self.order_ref)
        key = (self.front, self.session, ref)
        with self.lock:
            self.owned.add(key)
        req = {'BrokerID': '9999', 'InvestorID': self.userid, 'UserID': self.userid,
               'InstrumentID': SYMBOL, 'ExchangeID': 'SHFE', 'OrderRef': ref,
               'Direction': side, 'CombOffsetFlag': offset, 'CombHedgeFlag': '1',
               'OrderPriceType': '2', 'LimitPrice': price, 'VolumeTotalOriginal': 1,
               'TimeCondition': '1', 'VolumeCondition': '1', 'MinVolume': 1,
               'ContingentCondition': '1', 'ForceCloseReason': '0', 'IsAutoSuspend': 0}
        self.j.event('order_intent', simulation=True, data=safe(req))
        rc = self.reqOrderInsert(req, self.next_id())
        self.j.event('order_sent', order_ref=ref, return_code=rc)
        if rc:
            raise RuntimeError(f'order_local_rejection_{rc}')
        return key
    def wait_order(self, key, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            with self.lock:
                row = self.orders.get(key)
                if row and not active(row):
                    return row.copy()
            time.sleep(.1)
        # Query reconciliation is required before considering an uncertain send retryable.
        rows = self.query('reqQryOrder')
        matches = [r for r in rows if (r.get('FrontID'), r.get('SessionID'), r.get('OrderRef')) == key]
        if matches and not active(matches[-1]):
            return matches[-1]
        for row in matches:
            if active(row):
                req = {'BrokerID': '9999', 'InvestorID': self.userid, 'InstrumentID': SYMBOL,
                       'ExchangeID': 'SHFE', 'FrontID': key[0], 'SessionID': key[1],
                       'OrderRef': key[2], 'ActionFlag': '0'}
                self.j.event('owned_cancel_request', return_code=self.reqOrderAction(req, self.next_id()), order_ref=key[2])
        raise RuntimeError('order_outcome_uncertain_requires_reconciliation')

class Market(MdApi):
    def __init__(self, j, userid, password):
        super().__init__()
        self.j, self.userid, self.password = j, userid, password
        self.ready = Event()
        self.lock = RLock()
        self.tick = {}
        self.received = 0
        self.created = False
        self.count = 0
    def start(self):
        flow = self.j.output / 'md_flow'
        flow.mkdir(exist_ok=True)
        self.createFtdcMdApi((str(flow) + os.sep).encode('gbk'), True)
        self.created = True
        self.registerFront(MD_FRONT)
        self.init()
    def onFrontConnected(self):
        self.j.event('md_connected')
        self.reqUserLogin({'BrokerID': '9999', 'UserID': self.userid, 'Password': self.password}, 1)
    def onRspUserLogin(self, d, e, r, last):
        self.j.event('md_login', error_id=e.get('ErrorID', 0))
        if not e.get('ErrorID'):
            self.subscribeMarketData(SYMBOL)
    def onRspSubMarketData(self, d, e, r, last):
        self.j.event('md_subscription', symbol=d.get('InstrumentID'), error_id=e.get('ErrorID', 0))
    def onFrontDisconnected(self, reason):
        self.ready.clear()
        self.j.event('md_disconnected', reason=reason)
    def onRtnDepthMarketData(self, d):
        if d.get('InstrumentID') != SYMBOL:
            return
        with self.lock:
            self.tick, self.received = d.copy(), time.monotonic()
            self.count += 1
        self.j.event('tick', data=safe(d))
        self.ready.set()
    def price(self, side, tick_size):
        if not self.ready.wait(20):
            raise RuntimeError('no_market_data')
        with self.lock:
            return quote_price(self.tick, side, tick_size, self.received)

    def wait_trigger(self, trigger, timeout):
        if trigger is None: return
        if not math.isfinite(trigger) or trigger <= 0 or timeout <= 0:
            raise RuntimeError('invalid_trigger')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if self.ready.is_set() and time.monotonic() - self.received <= 3 and self.tick.get('LastPrice', 0) >= trigger:
                    self.j.event('breakout_trigger', threshold=trigger, data=safe(self.tick))
                    return
            time.sleep(.1)
        raise RuntimeError('trigger_timeout_no_order_sent')

def close_owned_position(td, md, tick_size, execute):
    """Only invoked after this run started from an empty account and attempted its single open."""
    for attempt in range(5):
        snap = td.account_snapshot(f'close_check_{attempt}')
        if snap['active_order_count']:
            raise RuntimeError('active_orders_block_close')
        nonzero = [p for p in snap['positions'] if p.get('Position', 0)]
        if not nonzero:
            return
        if len(nonzero) != 1 or nonzero[0].get('InstrumentID') != SYMBOL or nonzero[0].get('PosiDirection') != '2' or nonzero[0].get('Position') != 1 or nonzero[0].get('TodayPosition') != 1:
            raise RuntimeError('unexpected_position_requires_manual_review')
        owned_orders = [o for o in snap['orders'] if (o.get('FrontID'), o.get('SessionID'), o.get('OrderRef')) in td.owned]
        owned_net = sum((1 if o.get('CombOffsetFlag') == '0' else -1) * o.get('VolumeTraded', 0) for o in owned_orders)
        if owned_net != 1:
            raise RuntimeError('position_not_reconciled_to_own_fills')
        key = td.submit('1', '3', md.price('1', tick_size), execute)
        td.wait_order(key)
        time.sleep(.5)
    raise RuntimeError('close_retry_limit')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--execute-simnow', action='store_true')
    parser.add_argument('--symbol', choices=[SYMBOL], default=SYMBOL)
    parser.add_argument('--trigger', type=float)
    parser.add_argument('--trigger-timeout', type=float, default=60)
    args = parser.parse_args()
    user, password = os.environ.pop('SIMNOW_USERID'), os.environ.pop('SIMNOW_PASSWORD')
    j = Journal(args.output)
    td, md = Trading(j, user, password), Market(j, user, password)
    result = {'started_at': now(), 'symbol': SYMBOL, 'simulation': True, 'execute': args.execute_simnow,
              'trading_acceptance_passed': False, 'independent_client_crosscheck': 'pending', 'finished': False}
    j.save('manifest.json', {'td_front': TD_FRONT, 'md_front': MD_FRONT, 'symbol': SYMBOL,
           'max_open_lots': 1, 'max_open_attempts': 1, 'max_close_attempts': 5,
           'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'started_at': now()})
    opened_attempted = False
    tick_size = None
    try:
        td.start()
        td.login()
        instruments = td.rpc('reqQryInstrument', {'InstrumentID': SYMBOL})
        contract = next((r for r in instruments if r.get('InstrumentID') == SYMBOL), None)
        if not contract or contract.get('ExchangeID') != 'SHFE' or not contract.get('IsTrading'):
            raise RuntimeError('contract_not_tradable')
        tick_size = float(contract['PriceTick'])
        j.save('contract.json', safe(contract))
        initial = td.account_snapshot('initial')
        require_clean(initial['positions'], initial['orders'])
        result['preflight_passed'] = True
        md.start()
        md.wait_trigger(args.trigger, args.trigger_timeout)
        opening_price = md.price('0', tick_size)
        result['initial_quote_valid'] = True
        if args.execute_simnow:
            opened_attempted = True
            key = td.submit('0', '0', opening_price, True)
            opening = td.wait_order(key)
            result['open_order'] = safe(opening)
            after_open = td.account_snapshot('after_open')
            result['open_position_observed'] = after_open['gross_position'] == 1
            close_owned_position(td, md, tick_size, True)
        final = td.account_snapshot('final')
        time.sleep(2)
        final_repeat = td.account_snapshot('final_repeat')
        trades = td.query('reqQryTrade')
        own_orders = [o for o in final_repeat['orders'] if (o.get('FrontID'), o.get('SessionID'), o.get('OrderRef')) in td.owned]
        sysids = {(o.get('ExchangeID'), o.get('OrderSysID')) for o in own_orders if o.get('OrderSysID')}
        own_trades = [safe(t) for t in trades if (t.get('ExchangeID'), t.get('OrderSysID')) in sysids]
        j.save('own_trades.json', own_trades)
        open_qty = sum(t.get('Volume', 0) for t in own_trades if t.get('OffsetFlag') == '0' and t.get('Direction') == '0')
        close_qty = sum(t.get('Volume', 0) for t in own_trades if t.get('OffsetFlag') == '3' and t.get('Direction') == '1')
        result.update(open_trade_lots=open_qty, close_trade_lots=close_qty, final_gross_position=final_repeat['gross_position'], final_active_orders=final_repeat['active_order_count'], td_disconnects=td.disconnects)
        clean = all(s['gross_position'] == 0 and s['active_order_count'] == 0 for s in (final, final_repeat))
        result['trading_acceptance_passed'] = bool(args.execute_simnow and clean and open_qty == close_qty == 1 and result.get('open_position_observed') and not td.disconnects)
        result['status'] = 'passed' if result['trading_acceptance_passed'] else ('preflight_only' if not args.execute_simnow else 'not_passed')
    except Exception as exc:
        result['status'] = 'failed'
        # Exception messages only originate from our own guards; never serialize API login responses.
        result['failure'] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        j.event('failure', reason=result['failure'])
        if opened_attempted and tick_size is not None:
            try:
                close_owned_position(td, md, tick_size, args.execute_simnow)
                cleanup = td.account_snapshot('cleanup_final')
                result['cleanup_gross_position'] = cleanup['gross_position']
                result['cleanup_active_orders'] = cleanup['active_order_count']
            except Exception as cleanup_error:
                result['cleanup_failure'] = str(cleanup_error) if isinstance(cleanup_error, RuntimeError) else type(cleanup_error).__name__
    finally:
        if md.created: md.exit()
        if td.created: td.exit()
        result.update(finished=True, ended_at=now(), market_ticks=md.count)
        j.save('summary.json', result)
        j.file.close()
    return 0 if result['status'] in {'passed', 'preflight_only'} else 1

if __name__ == '__main__':
    raise SystemExit(main())
