"""Offline callback tests; the native CTP module is replaced before import."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch


class FakeMdApi:
    def __init__(self):
        self.subscriptions = []
        self.login_requests = 0

    def reqUserLogin(self, request, request_id):
        self.login_requests += 1
        return 0

    def subscribeMarketData(self, symbol):
        self.subscriptions.append(symbol)

    def createFtdcMdApi(self, flow_path, production_mode):
        self.api_creation_args = (flow_path, production_mode)

    def registerFront(self, front):
        self.registered_front = front

    def init(self):
        self.initialized = True


fake_api = ModuleType('vnpy_ctp.api')
fake_api.MdApi = FakeMdApi
fake_package = ModuleType('vnpy_ctp')
fake_package.api = fake_api
spec = importlib.util.spec_from_file_location('simnow_capture_tested', Path(__file__).with_name('capture.py'))
capture = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'vnpy_ctp': fake_package, 'vnpy_ctp.api': fake_api}):
    spec.loader.exec_module(capture)
analysis_spec = importlib.util.spec_from_file_location('simnow_analysis_tested', Path(__file__).with_name('analyze.py'))
analysis = importlib.util.module_from_spec(analysis_spec)
analysis_spec.loader.exec_module(analysis)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parents[2] / 'data' / 'simnow_checks' / 'offline-tests'
        self.test_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=self.test_root)
        self.output = Path(self.directory.name)
        self.recorder = capture.Recorder(self.output, 'rb2701', 'test-account', 'test-password')

    def tearDown(self):
        self.recorder.events.close()
        self.recorder.ticks.close()
        self.assertTrue(self.output.resolve().is_relative_to(self.test_root.resolve()))
        self.directory.cleanup()

    def test_failed_login_stops_without_subscription_and_redacts_errors(self):
        self.recorder.onFrontConnected()
        self.recorder.onRspUserLogin({}, {'ErrorID': 3, 'ErrorMsg': 'test-password test-account'}, 1, True)
        self.assertEqual(self.recorder.login_requests, 1)
        self.assertTrue(self.recorder.stop_event.is_set())
        self.assertEqual(self.recorder.subscriptions, [])
        self.assertEqual(self.recorder.reason, 'login_failed')
        log = (self.output / 'events.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('test-password', log)
        self.assertNotIn('test-account', log)

    def test_login_does_not_claim_subscription_until_confirmation(self):
        self.recorder.onRspUserLogin({}, {'ErrorID': 0}, 1, True)
        self.assertEqual(self.recorder.subscriptions, ['rb2701'])
        self.assertFalse(self.recorder.state['subscription_confirmed'])
        self.recorder.onRspSubMarketData({'InstrumentID': 'rb2701'}, {'ErrorID': 0}, 2, True)
        self.assertTrue(self.recorder.state['subscription_confirmed'])

    def test_real_time_fields_retained_stale_tick_not_counted_fresh(self):
        current = capture.datetime.now(capture.SHANGHAI)
        tick = {'InstrumentID': 'rb2701', 'ActionDay': current.strftime('%Y%m%d'),
                'TradingDay': '20990101', 'UpdateTime': current.strftime('%H:%M:%S'),
                'UpdateMillisec': 0, 'LastPrice': 3100, 'Volume': 2}
        self.recorder.onRtnDepthMarketData(tick)
        self.recorder.onRtnDepthMarketData({**tick, 'ActionDay': '20000101', 'LastPrice': 1.7976931348623157e308})
        self.recorder.onRtnDepthMarketData({**tick, 'InstrumentID': 'wrong'})
        self.recorder.snapshot(finished=True)
        summary = json.loads((self.output / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['tick_count'], 2)
        self.assertEqual(summary['fresh_actionday_tick_count'], 1)
        self.assertEqual(summary['valid_last_price_count'], 1)
        self.assertFalse(summary['sends_orders'])
        with (self.output / 'ticks.csv').open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]['TradingDay'], '20990101')
        self.assertEqual(rows[0]['ActionDay'], current.strftime('%Y%m%d'))

    def test_empty_snapshot_is_not_market_success(self):
        self.recorder.reason = 'no_ticks_observed'
        self.recorder.snapshot(finished=True)
        summary = json.loads((self.output / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['tick_count'], 0)
        self.assertEqual(summary['status'], 'no_ticks_observed')
        self.assertFalse(summary['login_confirmed'])

    def test_start_includes_handshake_mode_required_by_installed_api(self):
        self.recorder.start()
        self.assertTrue(self.recorder.api_created)
        self.assertTrue(self.recorder.api_creation_args[1])
        self.assertEqual(self.recorder.registered_front, capture.FRONT)
        self.assertTrue(self.recorder.initialized)

    def test_report_rejects_unfinished_observation(self):
        self.recorder.snapshot()
        with self.assertRaisesRegex(ValueError, 'still active'):
            analysis.analyze(self.output)

    def test_report_distinguishes_cached_snapshot_and_recent_advancing_stream(self):
        self.recorder.onRspUserLogin({}, {'ErrorID': 0}, 1, True)
        self.recorder.onRspSubMarketData({'InstrumentID': 'rb2701'}, {'ErrorID': 0}, 2, True)
        (self.output / 'manifest.json').write_text('{}', encoding='utf-8')
        self.recorder.onRtnDepthMarketData({'InstrumentID': 'rb2701', 'ActionDay': '20000101',
            'TradingDay': '20000101', 'UpdateTime': '23:00:00', 'UpdateMillisec': 0, 'LastPrice': 3100})
        self.recorder.snapshot(finished=True)
        self.assertFalse(analysis.analyze(self.output)['live_stream_observed'])
        current = capture.datetime.now(capture.SHANGHAI)
        for shift in [0, 500]:
            market = current + capture.timedelta(milliseconds=shift)
            self.recorder.onRtnDepthMarketData({'InstrumentID': 'rb2701',
                'ActionDay': market.strftime('%Y%m%d'), 'TradingDay': market.strftime('%Y%m%d'),
                'UpdateTime': market.strftime('%H:%M:%S'), 'UpdateMillisec': market.microsecond // 1000,
                'LastPrice': 3100, 'BidPrice1': 3099, 'AskPrice1': 3101})
        self.recorder.snapshot(finished=True)
        report = analysis.analyze(self.output)
        self.assertTrue(report['live_stream_observed'])
        self.assertTrue(report['summary_count_matches_csv'])
        self.assertEqual(report['fresh_tick_count'], 2)
        self.assertEqual(report['tick_count'], 3)


if __name__ == '__main__':
    unittest.main()
