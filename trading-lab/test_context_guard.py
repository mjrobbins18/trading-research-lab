from context_extractor import extract
from context_guard import validate


def test_dropped_and_swapped_table_rows():
    d={'document_id':'t','text':'Quarterly installments of $0.25 per share.\nRecord Dates | Payable Dates\nMarch 1, 2025 | March 15, 2025\nJune 1, 2025 | June 15, 2025'}
    a=extract(d)
    assert validate(a,d)['passed']
    a['events'].pop()
    assert not validate(a,d)['passed']
    a=extract(d);a['events'][0]['pay_date']['value']='2025-03-01'
    assert not validate(a,d)['passed']


def test_cropped_qualifier():
    d={'document_id':'p','text':'Dividend $1.00 per share payable on or after March 15, 2025.'}
    a=extract(d)
    assert validate(a,d)['passed']
    a['events'][0]['pay_date'].update(kind='scheduled',evidence='March 15, 2025')
    assert not validate(a,d)['passed']


def test_false_absence():
    d={'document_id':'e','text':'The ex-dividend date is March 1, 2025.'}
    a=extract(d);a['events'][0]['ex_date'].update(value=None,kind='not_stated',status='absent',cutoff=None,evidence=None)
    assert not validate(a,d)['passed']
