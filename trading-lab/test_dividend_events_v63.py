"""Latest implementation checks reuse prior regressions plus partial identity cases."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_dividend_events_v62 as prior_tests
import dividend_events_v63 as m

class Revision63Regression(prior_tests.V61Tests):
    def setUp(self):
        self.binding=patch.object(prior_tests,'m',m);self.binding.start()
        self.addCleanup(self.binding.stop)

class PartialIdentityTests(unittest.TestCase):
    def doc(self):
        return {'document_id':'partial-identity','text':'The board declared a quarterly dividend of USD 1.00 per share for outstanding Class A and Class B shares. Payment is scheduled for July 10, 2026. The record date is June 26, 2026.'}
    def test_named_classes_survive_unknown_type(self):
        d=self.doc();a=m.extract(d)
        self.assertEqual({tuple(e['security'].values()) for e in a['events']},{('unknown','A'),('unknown','B')})
        self.assertEqual(m.validate(a,d)['status'],'review_required')
        self.assertFalse(m.validate(a,d)['trading_authorized'])
    def test_invented_common_type_rejected(self):
        d=self.doc();a=m.extract(d);a['events'][0]['security']['type']='common'
        self.assertEqual(m.validate(a,d)['status'],'rejected')
    def test_class_loss_rejected(self):
        d=self.doc();a=m.extract(d);a['events'].pop()
        self.assertEqual(m.validate(a,d)['status'],'rejected')
    def test_missing_class_evidence_rejected(self):
        d=self.doc();a=m.extract(d);a['events'][0]['evidence']['security']=None
        self.assertEqual(m.validate(a,d)['status'],'rejected')
    def test_single_known_class_unknown_type(self):
        d=self.doc();d['text']=d['text'].replace('Class A and Class B','Class C');a=m.extract(d)
        self.assertEqual(a['events'][0]['security'],{'type':'unknown','class':'C'})
        self.assertEqual(m.validate(a,d)['status'],'review_required')
    def test_consumed_ups_diagnostic(self):
        docs=json.loads((Path(__file__).resolve().parent/'fixtures/dividend-v62/fresh-evaluation/documents.json').read_text())
        d=next(d for d in docs if d['document_id']=='fresh-v61-ups');a=m.extract(d)
        self.assertEqual({e['security']['class'] for e in a['events']},{'A','B'})
        self.assertTrue(all(e['security']['type']=='unknown' for e in a['events']))
        self.assertEqual(m.validate(a,d)['status'],'review_required')

def test_later_annual_label_regression():
    d={'document_id':'period-audit','text':'The board declared a quarterly dividend of USD 1.00 per common share, equivalent to USD 4.00 annualized. Payment is scheduled for July 10, 2026. The record date is June 26, 2026.'}
    a=m.extract(d)
    assert a['events'][0]['amount']['period']=='quarterly'
    bad=copy.deepcopy(a);bad['events'][0]['amount']['period']='annual'
    assert m.validate(bad,d)['status']=='rejected'
