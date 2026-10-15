"""Bounded, market-data-only SimNow observation. No trading API is imported."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import sys
from threading import Event, RLock
import time
from datetime import datetime, timedelta, timezone

from vnpy_ctp.api import MdApi

SHANGHAI = timezone(timedelta(hours=8))
FRONT = 'tcp://182.254.243.31:30011'
FIELDS = ['received_at', 'InstrumentID', 'TradingDay', 'ActionDay', 'UpdateTime',
          'UpdateMillisec', 'LastPrice', 'Volume', 'Turnover', 'OpenInterest',
          'BidPrice1', 'BidVolume1', 'AskPrice1', 'AskVolume1']


def now() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec='milliseconds')


def valid_price(value: object) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and 0 < number < 1e100
    except (TypeError, ValueError):
        return False


class Recorder(MdApi):
    def __init__(self, output: Path, symbol: str, userid: str, password: str):
        super().__init__()
        self.output, self.symbol = output, symbol
        self.userid, self.password = userid, password
        self.lock = RLock()
        self.stop_event = Event()
        self.logged_in = False
        self.request_id = 0
        self.api_created = False
        self.reason = 'running'
        self.events = (output / 'events.jsonl').open('w', encoding='utf-8')
        self.ticks = (output / 'ticks.csv').open('w', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.ticks, fieldnames=FIELDS)
        self.writer.writeheader()
        self.market_times: set[tuple] = set()
        self.state = {'started_at': now(), 'symbol': symbol, 'front': FRONT,
                      'login_confirmed': False, 'subscription_confirmed': False,
                      'tick_count': 0, 'fresh_actionday_tick_count': 0,
                      'valid_last_price_count': 0, 'disconnect_count': 0,
                      'first_tick_at': None, 'last_tick_at': None,
                      'sends_orders': False, 'terminal_crosscheck': 'not_performed'}

    def record(self, event: str, **details):
        with self.lock:
            row = {'received_at': now(), 'event': event, **details}
            self.events.write(json.dumps(row, ensure_ascii=False) + '\n')
            self.events.flush()

    def snapshot(self, finished: bool = False):
        with self.lock:
            result = {**self.state, 'status': self.reason, 'updated_at': now(),
                      'distinct_market_times': len(self.market_times),
                      'finished': finished}
            temporary = self.output / 'summary.tmp'
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.output / 'summary.json')

    def onFrontConnected(self):
        self.record('connected')
        self.request_id += 1
        result = self.reqUserLogin({'UserID': self.userid, 'Password': self.password, 'BrokerID': '9999'}, self.request_id)
        self.record('login_requested', return_code=result)
        if result:
            self.reason = 'login_request_rejected'
            self.stop_event.set()

    def onFrontDisconnected(self, reason):
        self.logged_in = False
        with self.lock:
            self.state['disconnect_count'] += 1
        self.record('disconnected', reason_code=reason)

    def onRspUserLogin(self, data, error, reqid, last):
        error_id = error.get('ErrorID', -1)
        self.record('login_response', request_id=reqid, error_id=error_id)
        if error_id:
            self.reason = 'login_failed'
            self.stop_event.set()
            return
        self.logged_in = True
        self.state['login_confirmed'] = True
        self.subscribeMarketData(self.symbol)
        self.record('subscription_requested', symbol=self.symbol)

    def onRspSubMarketData(self, data, error, reqid, last):
        error_id = error.get('ErrorID', -1)
        self.record('subscription_response', error_id=error_id, symbol=data.get('InstrumentID'))
        if error_id:
            self.reason = 'subscription_failed'
            self.stop_event.set()
        elif data.get('InstrumentID') == self.symbol:
            self.state['subscription_confirmed'] = True

    def onRspError(self, error, reqid, last):
        self.record('api_error', request_id=reqid, error_id=error.get('ErrorID'))

    def onRtnDepthMarketData(self, data):
        if data.get('InstrumentID') != self.symbol:
            self.record('unexpected_symbol')
            return
        received = datetime.now(SHANGHAI)
        row = {field: data.get(field) for field in FIELDS}
        row['received_at'] = received.isoformat(timespec='milliseconds')
        with self.lock:
            self.writer.writerow(row)
            self.ticks.flush()
            self.state['tick_count'] += 1
            self.state['first_tick_at'] = self.state['first_tick_at'] or row['received_at']
            self.state['last_tick_at'] = row['received_at']
            self.state['valid_last_price_count'] += int(valid_price(data.get('LastPrice')))
            self.market_times.add((data.get('ActionDay'), data.get('UpdateTime'), data.get('UpdateMillisec')))
            try:
                market = datetime.strptime(str(data['ActionDay']) + ' ' + str(data['UpdateTime']), '%Y%m%d %H:%M:%S').replace(tzinfo=SHANGHAI)
                market += timedelta(milliseconds=int(data.get('UpdateMillisec') or 0))
                age = (received - market).total_seconds()
                self.state['fresh_actionday_tick_count'] += int(-5 <= age <= 60)
            except (KeyError, TypeError, ValueError):
                pass

    def start(self):
        flow = self.output / '.ctp_flow'
        flow.mkdir()
        # The installed 6.7.11 binding requires both arguments. True selects
        # the API's production handshake keys, also used by this SimNow front;
        # it does not change the destination into a funded trading account.
        self.record('creating_api', production_handshake=True)
        self.createFtdcMdApi((str(flow) + os.sep).encode('gbk'), True)
        self.api_created = True
        self.record('api_created')
        self.registerFront(FRONT)
        self.init()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--duration', type=int, default=600)
    args = parser.parse_args()
    if not 30 <= args.duration <= 1800:
        parser.error('duration must be 30..1800 seconds')
    userid = os.environ.pop('SIMNOW_USERID', '')
    password = os.environ.pop('SIMNOW_PASSWORD', '')
    if not userid or not password:
        print('Missing local SimNow configuration.', file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'python': sys.version.split()[0], 'vnpy_ctp': importlib.metadata.version('vnpy_ctp'),
                'capture_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'duration_seconds': args.duration, 'symbol': args.symbol, 'front': FRONT,
                'mode': 'market_data_only', 'started_at': now(),
                'freshness_rule': 'ActionDay plus UpdateTime; local UTC+8 difference -5..60 seconds; not a latency guarantee'}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    recorder = Recorder(args.output, args.symbol, userid, password)
    userid = password = ''
    signal.signal(signal.SIGINT, lambda *_: recorder.stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: recorder.stop_event.set())
    started = time.monotonic()
    next_snapshot = 5.0
    exit_code = 0
    try:
        recorder.record('started', symbol=args.symbol, duration_seconds=args.duration)
        recorder.snapshot()
        recorder.start()
        while not recorder.stop_event.wait(0.25):
            elapsed = time.monotonic() - started
            if (args.output / 'STOP').exists():
                recorder.reason = 'stop_requested'
                break
            if elapsed >= 45 and not recorder.state['login_confirmed']:
                recorder.reason = 'login_timeout'
                exit_code = 1
                break
            if elapsed >= min(90, args.duration) and not recorder.state['tick_count']:
                recorder.reason = 'no_ticks_observed'
                exit_code = 1
                break
            if elapsed >= args.duration:
                recorder.reason = 'observation_finished'
                break
            if elapsed >= next_snapshot:
                recorder.snapshot()
                next_snapshot = elapsed + 5
        if recorder.reason == 'running':
            recorder.reason = 'interrupted'
        if recorder.reason in {'login_failed', 'login_request_rejected', 'subscription_failed'}:
            exit_code = 1
    except Exception as exc:
        recorder.reason = 'runtime_error'
        recorder.record('runtime_error', error_type=type(exc).__name__)
        exit_code = 1
    finally:
        try:
            if recorder.api_created:
                recorder.exit()
        except Exception as exc:
            recorder.reason = 'shutdown_error'
            recorder.record('shutdown_error', error_type=type(exc).__name__)
            exit_code = 1
        finally:
            recorder.record('finished', status=recorder.reason)
            recorder.snapshot(finished=True)
            recorder.events.close()
            recorder.ticks.close()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
