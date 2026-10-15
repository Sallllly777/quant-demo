"""Offline guards and callback/race tests; no API initialized, credentials or network used."""
import time
import unittest
from datetime import datetime
from threading import Event, RLock
from unittest.mock import Mock, patch
import sys
from types import ModuleType
fake_api = ModuleType('vnpy_ctp.api')
fake_api.MdApi = type('MdApi', (), {})
fake_api.TdApi = type('TdApi', (), {})
with patch.dict(sys.modules, {'vnpy_ctp.api': fake_api}):
    import acceptance as a

class AcceptanceTests(unittest.TestCase):
    def test_opposite_positions_do_not_net_to_zero(self):
        with self.assertRaisesRegex(RuntimeError, 'not_empty'):
            a.require_clean([{'Position': 1, 'PosiDirection': '2'}, {'Position': 1, 'PosiDirection': '3'}], [])
    def test_unknown_order_is_active(self):
        with self.assertRaises(RuntimeError): a.require_clean([], [{'OrderStatus': 'a'}])
        for status in ('0', '2', '4', '5'): self.assertFalse(a.active({'OrderStatus': status}))
    def test_nonzero_other_contract_blocks(self):
        with self.assertRaises(RuntimeError): a.require_clean([{'InstrumentID': 'rb2701', 'Position': 1}], [])
    def test_price_is_bounded_and_fresh(self):
        current = datetime.now(a.TZ)
        tick = dict(ActionDay=current.strftime('%Y%m%d'), UpdateTime=current.strftime('%H:%M:%S'), BidPrice1=100, AskPrice1=101, LowerLimitPrice=80, UpperLimitPrice=102, BidVolume1=1, AskVolume1=1)
        self.assertEqual(a.quote_price(tick, '0', 1, time.monotonic()), 102)
        self.assertEqual(a.quote_price(tick, '1', 1, time.monotonic()), 98)
        with self.assertRaisesRegex(RuntimeError, 'stale'): a.quote_price(tick, '0', 1, time.monotonic()-4)
        tick['ActionDay'] = '20200101'
        with self.assertRaisesRegex(RuntimeError, 'stale'): a.quote_price(tick, '0', 1, time.monotonic())
    def test_redaction(self):
        self.assertEqual(a.safe({'InvestorID':'secret', 'Password':'secret', 'AccountID':'secret', 'InstrumentID':'ag2612'}), {'InstrumentID':'ag2612'})
    def stub(self):
        obj = Mock()
        obj.j = Mock(); obj.lock = RLock(); obj.pending = {}; obj.orders = {}; obj.owned = {(7, 8, '9')}
        return obj
    def test_query_requires_last_and_retains_first_row(self):
        obj = self.stub(); p = {'done':Event(), 'rows':[], 'error':0}; obj.pending[3] = p
        a.Trading.response(obj, 'query', {'Position':1}, {}, 3, False)
        self.assertFalse(p['done'].is_set())
        a.Trading.response(obj, 'query', {}, {}, 3, True)
        self.assertTrue(p['done'].is_set()); self.assertEqual(p['rows'], [{'Position':1}])
    def test_query_error_cannot_be_empty_success(self):
        obj = self.stub(); p = {'done':Event(), 'rows':[], 'error':0}; obj.pending[3] = p
        a.Trading.response(obj, 'query', {}, {'ErrorID':23}, 3, True)
        self.assertEqual(p['error'], 23)
    def test_foreign_order_return_ignored(self):
        obj = self.stub()
        a.Trading.onRtnOrder(obj, {'FrontID':1, 'SessionID':2, 'OrderRef':'9', 'OrderStatus':'0'})
        self.assertFalse(obj.orders)
        a.Trading.onRtnOrder(obj, {'FrontID':7, 'SessionID':8, 'OrderRef':'9', 'OrderStatus':'0'})
        self.assertEqual(len(obj.orders), 1)
    def test_order_disabled_without_explicit_switch(self):
        obj = self.stub()
        with self.assertRaisesRegex(RuntimeError, 'gate_closed'): a.Trading.submit(obj, '0', '0', 100, False)
        obj.reqOrderInsert.assert_not_called()
    def test_at_most_one_open(self):
        obj = self.stub(); obj.connected = Event(); obj.connected.set(); obj.disconnects = 0; obj.open_attempts = 1
        with self.assertRaisesRegex(RuntimeError, 'open_attempt_limit'): a.Trading.submit(obj, '0', '0', 100, True)
    def test_at_most_five_close_attempts_across_cleanup(self):
        obj=self.stub(); obj.connected=Event(); obj.connected.set(); obj.disconnects=0; obj.close_attempts=5
        with self.assertRaisesRegex(RuntimeError,'close_attempt_limit'): a.Trading.submit(obj,'1','3',100,True)
        obj.reqOrderInsert.assert_not_called()
    def test_disconnect_blocks_further_orders(self):
        obj=self.stub(); obj.connected=Event(); obj.connected.set(); obj.disconnects=1
        with self.assertRaisesRegex(RuntimeError,'gate_closed'): a.Trading.submit(obj,'0','0',100,True)
    def test_local_query_error_does_not_look_like_empty(self):
        obj=self.stub(); obj.connected=Event(); obj.connected.set(); obj.last_query=0
        obj.next_id.return_value=1; obj.reqQryOrder.return_value=-2
        with patch.object(a.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'local_-2'): a.Trading.rpc(obj,'reqQryOrder',{},timeout=.001)
    def test_duplicate_trade_callback_is_idempotent(self):
        obj=self.stub(); obj.trades={}
        row={'InstrumentID':a.SYMBOL,'ExchangeID':'SHFE','TradeID':'1','TradingDay':'20261009'}
        a.Trading.onRtnTrade(obj,row); a.Trading.onRtnTrade(obj,row)
        self.assertEqual(len(obj.trades),1)
    def test_trigger_timeout_sends_nothing(self):
        obj=self.stub(); obj.ready=Event(); obj.received=0; obj.tick={}
        with self.assertRaisesRegex(RuntimeError,'trigger_timeout'): a.Market.wait_trigger(obj,100,.001)
        obj.reqOrderInsert.assert_not_called()
    def test_invalid_and_empty_books_rejected(self):
        current=datetime.now(a.TZ)
        tick=dict(ActionDay=current.strftime('%Y%m%d'),UpdateTime=current.strftime('%H:%M:%S'),BidPrice1=100,AskPrice1=101,LowerLimitPrice=80,UpperLimitPrice=120,BidVolume1=1,AskVolume1=1)
        for changes,reason in [({'AskPrice1':float('inf')},'invalid_quote'),({'BidPrice1':102},'invalid_book'),({'AskVolume1':0},'empty_book')]:
            with self.assertRaisesRegex(RuntimeError,reason): a.quote_price({**tick,**changes},'0',1,time.monotonic())
    def test_unknown_position_never_closed(self):
        td = self.stub(); md = Mock()
        td.account_snapshot.return_value = {'active_order_count':0, 'positions':[{'InstrumentID':a.SYMBOL,'PosiDirection':'2','Position':1,'TodayPosition':1}], 'orders':[]}
        with self.assertRaisesRegex(RuntimeError, 'not_reconciled'): a.close_owned_position(td, md, 1, True)
        td.submit.assert_not_called()
    def test_query_timeout_does_not_look_like_zero(self):
        obj = self.stub(); obj.connected = Event(); obj.connected.set(); obj.last_query = 0
        obj.next_id.return_value = 1; obj.reqQryOrder.return_value = 0
        with patch.object(a.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'timeout_incomplete'):
                a.Trading.rpc(obj, 'reqQryOrder', {}, timeout=.001)
    def test_ioc_zero_fill_terminal_is_not_reported_as_fill(self):
        obj=self.stub(); key=(7,8,'9')
        obj.orders[key]={'OrderStatus':'5','VolumeTraded':0}
        self.assertEqual(a.Trading.wait_order(obj,key,.1)['VolumeTraded'],0)
        obj.reqOrderInsert.assert_not_called()
    def test_missing_return_reconciles_from_query(self):
        obj=self.stub(); key=(7,8,'9')
        row={'FrontID':7,'SessionID':8,'OrderRef':'9','OrderStatus':'0','VolumeTraded':1}
        obj.query.return_value=[row]
        self.assertEqual(a.Trading.wait_order(obj,key,0),row)
        obj.reqOrderInsert.assert_not_called()
    def test_uncertain_order_does_not_retry_or_cancel_foreign_session(self):
        obj=self.stub(); key=(7,8,'9')
        obj.query.return_value=[{'FrontID':7,'SessionID':99,'OrderRef':'9','OrderStatus':'3'}]
        with self.assertRaisesRegex(RuntimeError,'uncertain'): a.Trading.wait_order(obj,key,0)
        obj.reqOrderInsert.assert_not_called(); obj.reqOrderAction.assert_not_called()
    def test_only_own_still_working_order_cancelled_after_timeout(self):
        obj=self.stub(); key=(7,8,'9'); obj.userid='test'; obj.next_id.return_value=1
        obj.query.return_value=[{'FrontID':7,'SessionID':8,'OrderRef':'9','OrderStatus':'3'},
                                {'FrontID':7,'SessionID':99,'OrderRef':'9','OrderStatus':'3'}]
        with self.assertRaisesRegex(RuntimeError,'uncertain'): a.Trading.wait_order(obj,key,0)
        self.assertEqual(obj.reqOrderAction.call_count,1)
        self.assertEqual(obj.reqOrderAction.call_args.args[0]['SessionID'],8)
        obj.reqOrderInsert.assert_not_called()
    def test_active_order_blocks_close(self):
        td=self.stub(); td.account_snapshot.return_value={'active_order_count':1}
        with self.assertRaisesRegex(RuntimeError,'active_orders'): a.close_owned_position(td,Mock(),1,True)
        td.submit.assert_not_called()
    def test_second_api_initialization_argument(self):
        obj = self.stub(); obj.j.output = Mock(); obj.j.output.__truediv__ = Mock(return_value=Mock())
        a.Trading.start(obj)
        self.assertTrue(obj.createFtdcTraderApi.call_args.args[1])

if __name__ == '__main__': unittest.main()
