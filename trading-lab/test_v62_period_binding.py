from copy import deepcopy
import dividend_events_v62 as m

def test_later_annualized_label_does_not_relabel_quarterly_amount():
    d={'document_id':'period-audit','text':'The board declared a quarterly dividend of USD 1.00 per common share, equivalent to USD 4.00 annualized. Payment is scheduled for July 10, 2026. The record date is June 26, 2026.'}
    p=m.extract(d)
    assert p['events'][0]['amount']['period']=='quarterly'
    assert m.validate(p,d)['status']=='consistent_research_record'
    bad=deepcopy(p);bad['events'][0]['amount']['period']='annual'
    assert m.validate(bad,d)['status']=='rejected'

def test_annualized_amount_with_own_unit_does_not_replace_quarterly():
    d={'document_id':'period-pair','text':'The board declared a quarterly dividend of USD 1.00 per common share, equivalent to an annualized USD 4.00 per share. Payment is scheduled for July 10, 2026. The record date is June 26, 2026.'}
    p=m.extract(d)
    assert len(p['events'])==1
    assert p['events'][0]['amount']['value']=='1.00'
    assert p['events'][0]['amount']['period']=='quarterly'
    bad=deepcopy(p);bad['events'][0]['amount']['value']='4.00';bad['events'][0]['evidence']['amount']=[0,len(d['text'])]
    assert m.validate(bad,d)['status']=='rejected'
