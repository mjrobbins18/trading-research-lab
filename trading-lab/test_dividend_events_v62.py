"""Reviewed-source regression and mutation tests, not new qualification evidence."""
import copy
import json
from pathlib import Path
import unittest
import dividend_events_v62 as m

DOCS=json.loads((Path(__file__).resolve().parent/'fixtures/resolved-independent-evaluation/documents.json').read_text())

FRESH_ROOT=Path(__file__).resolve().parent/'fixtures/dividend-v6/fresh-evaluation'
FRESH_DOCS=json.loads((FRESH_ROOT/'documents.json').read_text())
FRESH_CANDIDATES=json.loads((FRESH_ROOT/'candidate.json').read_text())

class V61Tests(unittest.TestCase):
    def fresh(self,index):return copy.deepcopy(FRESH_DOCS[index]),copy.deepcopy(FRESH_CANDIDATES[index])
    def test_consumed_holdout_candidates_no_false_rejection(self):
        for d,p in zip(FRESH_DOCS,FRESH_CANDIDATES):
            result=m.validate(p,d);self.assertEqual(result['errors'],[]);self.assertEqual(result['status'],'review_required')
    def test_consumed_holdout_parser_facts(self):
        count=0
        for d,candidate in zip(FRESH_DOCS,FRESH_CANDIDATES):
            p=m.extract(d);count+=len(p['events'])
            def semantics(e):return {k:e[k] for k in ('security','amount','dates','split_basis')}
            self.assertCountEqual([semantics(e) for e in p['events']],[semantics(e) for e in candidate['events']])
        self.assertEqual(count,7)
    def test_new_cutoff_corruption(self):
        for i in range(6):
            d,p=self.fresh(i);p['events'][0]['dates']['record']['cutoff']='start_of_business';self.rejected(d,p)
    def test_new_excluded_class(self):
        d,p=self.fresh(0);p['events'][0]['security']['class']='C';self.rejected(d,p)
    def test_new_missing_class(self):
        d,p=self.fresh(0);p['events'].pop();self.rejected(d,p)
    def test_new_source_currency_guessed(self):
        d,p=self.fresh(4);p['events'][0]['amount']['currency']='USD';self.rejected(d,p)
    def test_new_role_swap_broad_span(self):
        d,p=self.fresh(0);e=p['events'][0];e['dates']['record']['value'],e['dates']['payment']['value']=e['dates']['payment']['value'],e['dates']['record']['value']
        for role in ('record','payment'):e['evidence']['dates'][role]=[0,len(d['text'])]
        self.rejected(d,p)
    def test_historical_equal_value_wrong_evidence(self):
        d,p=self.fresh(5);start=d['text'].index('$0.41 per common');p['events'][0]['evidence']['amount']=[start,len(d['text'])];self.rejected(d,p)
    def test_historical_different_value_not_current(self):
        d,p=self.fresh(5);d['text']=d['text'].replace('$0.41 per common','$0.39 per common');p=m.extract(d)
        self.assertEqual(p['events'][0]['amount']['value'],'0.41')
        p['events'][0]['amount']['value']='0.39';p['events'][0]['evidence']['amount']=[0,len(d['text'])];self.rejected(d,p)
    def test_annual_equivalent_not_current(self):
        d,p=self.fresh(2);p['events'][0]['amount']['value']='7.44';p['events'][0]['evidence']['amount']=[0,len(d['text'])];self.rejected(d,p)

    def proposal(self,index):
        doc=copy.deepcopy(DOCS[index]);return doc,m.extract(doc)
    def rejected(self,doc,p):self.assertEqual(m.validate(p,doc)['status'],'rejected')
    def test_reviewed_facts(self):
        expected=[('0.91','2025-12-11','2025-11-20'),('1.30','2025-06-10','2025-05-27'),('0.670','2025-12-01','2025-11-12'),('0.76','2025-08-08','2025-07-09'),('1.30','2025-08-15','2025-08-01'),('0.23','2026-07-10','2026-06-26')]
        for d,(amount,pay,rec) in zip(DOCS,expected):
            p=m.extract(d)
            for event in p['events']:
                self.assertEqual(event['amount']['value'],amount)
                self.assertEqual(event['amount']['period'],'quarterly')
                self.assertEqual(event['dates']['payment']['value'],pay)
                self.assertEqual(event['dates']['payment']['qualification'],'scheduled')
                self.assertEqual(event['dates']['record']['value'],rec)
            self.assertEqual(m.validate(p,d)['errors'],[])
    def simple(self,text=None):
        return dict(document_id='synthetic-audit',issuer='Example',text=text or 'The board declared a quarterly dividend of USD 1.00 per share on common stock. Payment is scheduled for July 10, 2026. The record date is June 26, 2026.',currency_context=None)
    def test_currency_metadata_supplied_assertion(self):
        d=self.simple();d['text']=d['text'].replace('USD 1.00','$1.00');d['currency_context']='USD';p=m.extract(d)
        self.assertEqual(p['events'][0]['amount']['currency'],'USD');self.assertEqual(m.validate(p,d)['status'],'consistent_research_record')
    def test_currency_metadata_conflict(self):
        d=self.simple();d['currency_context']='SEK';p=m.extract(d)
        self.assertIsNone(p['events'][0]['amount']['currency']);self.assertIn('conflicting_currency_evidence',m.validate(p,d)['review_reasons'])
    def test_eps_currency_distractor(self):
        d=self.simple();d['text']='Earnings were USD 3 per share. '+d['text'].replace('USD 1.00','$1.00');p=m.extract(d)
        self.assertIsNone(m.currency(d));self.assertNotEqual(m.validate(p,d)['status'],'consistent_research_record')
    def test_eps_same_sentence_currency_distractor(self):
        d=self.simple();d['text']=d['text'].replace('The board','Earnings were USD 3 per share, and the board').replace('USD 1.00','$1.00');p=m.extract(d)
        self.assertIsNone(m.currency(d));self.assertNotEqual(m.validate(p,d)['status'],'consistent_research_record')
    def test_unrelated_preferred_stock_requires_review(self):
        d=self.simple();d['text']+=' Preferred stock is outstanding.';p=m.extract(d)
        self.assertIn('mixed_security_types_require_recipient_binding',m.validate(p,d)['review_reasons'])
    def test_unrelated_second_class_requires_review(self):
        d=self.simple();d['text']=d['text'].replace('common stock','Class A common stock')+' Class B common shares are outstanding.';p=m.extract(d)
        self.assertIn('multiple_classes_require_recipient_binding',m.validate(p,d)['review_reasons'])
    def test_audit_excluded_security(self):
        d=self.simple();d['text']+=' Preferred stock is outstanding but receives no dividend.';p=m.extract(d)
        self.assertEqual(len(p['events']),1);self.assertEqual(m.validate(p,d)['status'],'review_required')
    def test_audit_revenue_currency_not_dividend_currency(self):
        d=self.simple();d['text']='The company reports revenue in USD. '+d['text'].replace('USD 1.00','$1.00');p=m.extract(d)
        self.assertIsNone(p['events'][0]['amount']['currency']);self.assertEqual(m.validate(p,d)['status'],'review_required')
    def test_audit_reversed_class_syntax(self):
        d=self.simple();d['text']=d['text'].replace('common stock','common stock Class B');p=m.extract(d)
        self.assertEqual(p['events'][0]['security'],{'type':'common','class':'B'})
        self.assertEqual(m.validate(p,d)['errors'],[])
    def test_audit_expected_earnings_does_not_qualify_payment(self):
        d=self.simple();d['text']=d['text'].replace('Payment is','Management expected strong earnings, and payment is');p=m.extract(d)
        self.assertEqual(p['events'][0]['dates']['payment']['qualification'],'scheduled')
    def test_audit_or_later(self):
        d=self.simple();d['text']=d['text'].replace('July 10, 2026.','July 10, 2026, or later.');p=m.extract(d)
        self.assertEqual(p['events'][0]['dates']['payment']['qualification'],'earliest')
        p['events'][0]['dates']['payment']['qualification']='scheduled';self.rejected(d,p)
    def test_audit_supplier_invoice_not_dividend_payment(self):
        d=self.simple();d['text']=d['text'].replace('Payment is','Payment of supplier invoices is');p=m.extract(d)
        self.assertIsNone(p['events'][0]['dates']['payment']['value']);self.assertEqual(m.validate(p,d)['status'],'review_required')
    def test_malformed_security_does_not_crash(self):
        for bad in [[],{},1]:
            d,p=self.proposal(5);p['events'][0]['security']['class']=bad;self.rejected(d,p)
    def test_zero_is_not_false(self):
        d,p=self.proposal(5);p['cash_available_confirmed']=0;self.rejected(d,p)
    def test_malformed_date_rejected(self):
        for key,val in [('value','2026-02-30'),('status','invented'),('qualification','maybe'),('cutoff','close_of_business')]:
            d,p=self.proposal(5);p['events'][0]['dates']['payment'][key]=val;self.rejected(d,p)
    def test_repeated_class_is_one_event(self):
        d=copy.deepcopy(DOCS[2]);d['text']+=' These class A common shares trade publicly.';p=m.extract(d)
        self.assertEqual(len(p['events']),1);self.assertEqual(m.validate(p,d)['errors'],[])
    def test_unbound_other_security_review(self):
        d=copy.deepcopy(DOCS[3]);d['text']+=' Preferred shares are also outstanding.';d['currency_context']='USD';p=m.extract(d)
        self.assertEqual(m.validate(p,d)['status'],'review_required')
    def test_unknown_security_not_common(self):
        for i in [0,1]:
            d,p=self.proposal(i);self.assertEqual(p['events'][0]['security'],{'type':'unknown','class':None})
            p['events'][0]['security']['type']='common';self.rejected(d,p)
    def test_unknown_currency_cannot_be_guessed(self):
        d,p=self.proposal(0);p['events'][0]['amount']['currency']='USD';self.rejected(d,p)
    def test_subclasses(self):
        d,p=self.proposal(3)
        self.assertEqual([e['security']['class'] for e in p['events']],['A','B'])
        p['events'].pop();self.rejected(d,p)
    def test_subclass_collapse_rejected(self):
        d,p=self.proposal(3);p['events'][0]['security']['class']=None;self.rejected(d,p)
    def test_visa_no_nominal_other_share_amount(self):
        d,p=self.proposal(2);self.assertEqual(len(p['events']),1)
        self.assertIn('other_securities_as_converted_amounts_unresolved',m.validate(p,d)['review_reasons'])
        p['events'].append(copy.deepcopy(p['events'][0]));p['events'][-1]['security']={'type':'preferred','class':None};self.rejected(d,p)
    def test_wrong_annual_rate(self):
        d,p=self.proposal(1);p['events'][0]['amount']['value']='5.20';p['events'][0]['evidence']['amount']=[0,len(d['text'])];self.rejected(d,p)
    def test_wrong_period(self):
        d,p=self.proposal(5);p['events'][0]['amount']['period']='annual';self.rejected(d,p)
    def test_date_swap(self):
        d,p=self.proposal(5);e=p['events'][0];e['dates']['record']['value'],e['dates']['payment']['value']=e['dates']['payment']['value'],e['dates']['record']['value'];self.rejected(d,p)
    def test_meeting_record_not_dividend_record(self):
        d,p=self.proposal(0);e=p['events'][0];e['dates']['record']['value']='2025-09-30';e['evidence']['dates']['record']=[0,len(d['text'])];self.rejected(d,p)
    def test_meeting_ex_date_distinct(self):
        d,p=self.proposal(0);self.assertEqual(p['events'][0]['dates']['ex_dividend']['value'],'2025-11-20')
    def test_cutoff_preserved(self):
        d,p=self.proposal(4);self.assertEqual(p['events'][0]['dates']['record']['cutoff'],'close_of_business')
        p['events'][0]['dates']['record']['cutoff']=None;self.rejected(d,p)
    def test_alternative_enclosing_evidence_and_numeric_format(self):
        d,p=self.proposal(5);e=p['events'][0];e['amount']['value']='0.2300'
        e['evidence']['amount']=[0,len(d['text'])];e['evidence']['security']=[0,len(d['text'])]
        for role in ('payment','record'):e['evidence']['dates'][role]=[0,len(d['text'])]
        self.assertEqual(m.validate(p,d)['status'],'consistent_research_record')
    def test_wrong_evidence_span(self):
        d,p=self.proposal(5);p['events'][0]['evidence']['amount']=[0,10];self.rejected(d,p)
    def test_source_mutation(self):
        d,p=self.proposal(5);d['text']+=' extra';self.rejected(d,p)
    def test_removed_review_reasons_still_review(self):
        d,p=self.proposal(2);p['unresolved']=[];self.assertEqual(m.validate(p,d)['status'],'review_required')
    def test_no_payment_confirmation(self):
        d,p=self.proposal(5);p['cash_available_confirmed']=True;self.rejected(d,p)
    def test_invalid_schema(self):
        d,p=self.proposal(5);p['events'][0]['dates']['payment']='tomorrow';self.rejected(d,p)
    def test_qualifiers(self):
        for wording,qual in [('on or after','earliest'),('expected on','expected'),('due','scheduled'),('anticipated on','expected')]:
            d=copy.deepcopy(DOCS[5]);d['text']=d['text'].replace('scheduled for',wording);p=m.extract(d)
            self.assertEqual(p['events'][0]['dates']['payment']['qualification'],qual)
            p['events'][0]['dates']['payment']['qualification']='earliest' if qual!='earliest' else 'scheduled';self.rejected(d,p)
    def test_absent_exdate(self):
        d,p=self.proposal(5);self.assertEqual(p['events'][0]['dates']['ex_dividend'],m.empty_date())
    def test_unsupported_relationship_review(self):
        d=copy.deepcopy(DOCS[5]);d['text']=d['text'].replace('Payment is scheduled for July 10, 2026','The distribution reaches owners July 10, 2026');p=m.extract(d)
        self.assertEqual(m.validate(p,d)['status'],'review_required')
        p['events'][0]['dates']['payment']={'value':'2026-07-10','status':'explicit','qualification':'scheduled','cutoff':None}
        p['events'][0]['evidence']['dates']['payment']=[0,len(d['text'])]
        self.assertEqual(m.validate(p,d)['status'],'review_required')
    def test_split_remains_review(self):
        d=copy.deepcopy(DOCS[5]);d['text']+=' A stock split also occurred.'
        p=m.extract(d);self.assertEqual(m.validate(p,d)['status'],'review_required')
        p['events'][0]['split_basis']='post_split';self.rejected(d,p)
    def test_duplicate_event(self):
        d,p=self.proposal(5);p['events'].append(copy.deepcopy(p['events'][0]));self.rejected(d,p)
    def test_omitted_event(self):
        d,p=self.proposal(5);p['events']=[];self.rejected(d,p)
    def test_missing_year_not_imputed(self):
        d=copy.deepcopy(DOCS[5]);d['text']=d['text'].replace('July 10, 2026','July 10');p=m.extract(d)
        self.assertIsNone(p['events'][0]['dates']['payment']['value']);self.assertEqual(m.validate(p,d)['status'],'review_required')

if __name__=='__main__':unittest.main()
