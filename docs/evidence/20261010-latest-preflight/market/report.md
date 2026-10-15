# SimNow market-data observation: ag2612

Live stream not established by this record

| Check | Result |
| --- | --- |
| status | no_ticks_observed |
| login_confirmed | False |
| subscription_confirmed | False |
| tick_count | 0 |
| summary_count_matches_csv | True |
| fresh_tick_count | 0 |
| valid_last_price_count | 0 |
| missing_or_invalid_best_book_count | 0 |
| crossed_best_book_count | 0 |
| distinct_market_times | 0 |
| market_time_regressions | 0 |
| disconnect_count | 0 |
| first_received_at | None |
| last_received_at | None |
| first_market_time | None |
| last_market_time | None |
| observed_span_seconds | 0 |
| max_receive_gap_seconds | None |
| median_clock_difference_seconds | None |
| trading_days | [] |
| action_days | [] |
| terminal_crosscheck | not_performed |
| sends_orders | False |

## Scope

- Source: the configured SimNow market-data front. No trading API or order submission.
- Freshness means ActionDay + exchange time differs from local UTC+8 receive time by -5..60 seconds.
- Clock differences are observations, not independently verified network latency.
- No independent client comparison, trade execution, position reconciliation or strategy-performance validation is included.
- Raw files and SHA-256 values are listed in validation.json.

## Files

[Events](events.jsonl) | [Ticks](ticks.csv) | [Summary](summary.json) | [Validation](validation.json)
