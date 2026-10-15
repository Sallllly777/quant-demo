"""Build a reproducible validation report from a finished market-data run."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics


def price_ok(value: str) -> bool:
    try:
        value = float(value)
        return math.isfinite(value) and 0 < value < 1e100
    except (TypeError, ValueError):
        return False


def analyze(directory: Path) -> dict:
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8-sig'))
    if not summary.get('finished'):
        raise ValueError('The run is still active; wait for its final summary.')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8-sig'))
    with (directory / 'ticks.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    local_times = [datetime.fromisoformat(row['received_at']) for row in rows]
    intervals = [(right - left).total_seconds() for left, right in zip(local_times, local_times[1:])]
    ages = []
    market_times = []
    fresh_count = 0
    for row, received in zip(rows, local_times):
        try:
            market = datetime.strptime(row['ActionDay'] + ' ' + row['UpdateTime'], '%Y%m%d %H:%M:%S').replace(tzinfo=timezone(timedelta(hours=8)))
            market += timedelta(milliseconds=int(row['UpdateMillisec'] or 0))
            market_times.append(market)
            age = (received - market).total_seconds()
            ages.append(age)
            fresh_count += int(-5 <= age <= 60)
        except (KeyError, TypeError, ValueError):
            pass
    valid_prices = sum(price_ok(row['LastPrice']) for row in rows)
    valid_books = [row for row in rows if price_ok(row['BidPrice1']) and price_ok(row['AskPrice1'])]
    crossed_books = sum(float(row['BidPrice1']) > float(row['AskPrice1']) for row in valid_books)
    symbol_matches = all(row['InstrumentID'] == summary['symbol'] for row in rows)
    live_observed = bool(summary['login_confirmed'] and summary['subscription_confirmed']
                         and fresh_count >= 2 and len(set(market_times)) >= 2 and valid_prices >= 2
                         and symbol_matches)
    result = {
        'run': directory.name, 'symbol': summary['symbol'], 'front': summary['front'],
        'status': summary['status'], 'finished': True,
        'login_confirmed': summary['login_confirmed'],
        'subscription_confirmed': summary['subscription_confirmed'],
        'tick_count': len(rows), 'summary_count_matches_csv': len(rows) == summary['tick_count'],
        'symbol_matches': symbol_matches, 'fresh_tick_count': fresh_count,
        'valid_last_price_count': valid_prices, 'missing_or_invalid_best_book_count': len(rows) - len(valid_books),
        'crossed_best_book_count': crossed_books,
        'distinct_market_times': len(set(market_times)),
        'market_time_regressions': sum(b < a for a, b in zip(market_times, market_times[1:])),
        'disconnect_count': summary['disconnect_count'],
        'first_received_at': local_times[0].isoformat() if rows else None,
        'last_received_at': local_times[-1].isoformat() if rows else None,
        'first_market_time': market_times[0].isoformat() if market_times else None,
        'last_market_time': market_times[-1].isoformat() if market_times else None,
        'observed_span_seconds': (local_times[-1] - local_times[0]).total_seconds() if rows else 0,
        'max_receive_gap_seconds': max(intervals) if intervals else None,
        'median_receive_gap_seconds': statistics.median(intervals) if intervals else None,
        'median_clock_difference_seconds': statistics.median(ages) if ages else None,
        'min_clock_difference_seconds': min(ages) if ages else None,
        'max_clock_difference_seconds': max(ages) if ages else None,
        'trading_days': sorted({row['TradingDay'] for row in rows}),
        'action_days': sorted({row['ActionDay'] for row in rows}),
        'live_stream_observed': live_observed,
        'terminal_crosscheck': summary['terminal_crosscheck'], 'sends_orders': False,
        'manifest': manifest,
        'file_sha256': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                        for name in ['manifest.json', 'events.jsonl', 'ticks.csv', 'summary.json']},
    }
    (directory / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    outcome = 'Observed advancing, recent market ticks' if live_observed else 'Live stream not established by this record'
    report = [f'# SimNow market-data observation: {summary["symbol"]}', '', outcome, '',
              '| Check | Result |', '| --- | --- |']
    for key in ['status', 'login_confirmed', 'subscription_confirmed', 'tick_count',
                'summary_count_matches_csv', 'fresh_tick_count', 'valid_last_price_count',
                'missing_or_invalid_best_book_count', 'crossed_best_book_count',
                'distinct_market_times', 'market_time_regressions', 'disconnect_count',
                'first_received_at', 'last_received_at', 'first_market_time', 'last_market_time',
                'observed_span_seconds', 'max_receive_gap_seconds', 'median_clock_difference_seconds',
                'trading_days', 'action_days', 'terminal_crosscheck', 'sends_orders']:
        report.append(f'| {key} | {result[key]} |')
    report += ['', '## Scope', '',
               '- Source: the configured SimNow market-data front. No trading API or order submission.',
               '- Freshness means ActionDay + exchange time differs from local UTC+8 receive time by -5..60 seconds.',
               '- Clock differences are observations, not independently verified network latency.',
               '- No independent client comparison, trade execution, position reconciliation or strategy-performance validation is included.',
               '- Raw files and SHA-256 values are listed in validation.json.', '',
               '## Files', '', '[Events](events.jsonl) | [Ticks](ticks.csv) | [Summary](summary.json) | [Validation](validation.json)', '']
    (directory / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.run_dir.resolve())
    print(json.dumps({key: result[key] for key in ['run', 'symbol', 'status', 'tick_count', 'fresh_tick_count',
                                                  'live_stream_observed', 'summary_count_matches_csv']}, ensure_ascii=True))
