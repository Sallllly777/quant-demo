import json
import unittest
from unittest.mock import Mock
import verify_acceptance as v

class ComparisonTests(unittest.TestCase):
    def test_same_order_ref_different_session_is_not_ours(self):
        events=[{'event':'td_login','error_id':0,'data':{'FrontID':1,'SessionID':2}},
                {'event':'order_intent','data':{'OrderRef':'3'}}]
        ours={'FrontID':1,'SessionID':2,'OrderRef':'3','InstrumentID':'ag2612'}
        other={**ours,'SessionID':4}
        self.assertEqual(v.own_orders(events,[other,ours]),[ours])
    def reference(self, **changes):
        row = dict(symbol='ag2612', market_at='2026-10-08T23:00:00.000+08:00', last=100,bid=99,ask=101,volume=50,bid_volume=2,ask_volume=3)
        row.update(changes)
        p=Mock(); p.read_text.return_value=json.dumps(row)
        return p
    def test_all_fields_equal(self):
        r=v.compare_reference(self.reference(), [('2026-10-08T23:00:00.000+08:00',(100,99,101,50,2,3))])
        self.assertEqual(r['equal_six_fields'],1)
    def test_equal_price_but_volume_difference_fails(self):
        r=v.compare_reference(self.reference(), [('2026-10-08T23:00:00.000+08:00',(100,99,101,51,2,3))])
        self.assertEqual(r['differences'],1)
    def test_missing_timestamp_not_matched_by_price(self):
        r=v.compare_reference(self.reference(), [('2026-10-08T23:00:01.000+08:00',(100,99,101,50,2,3))])
        self.assertEqual(r['unmatched'],1)
    def test_wrong_contract_rejected(self):
        with self.assertRaises(ValueError): v.compare_reference(self.reference(symbol='ag0'),[])

if __name__=='__main__': unittest.main()
