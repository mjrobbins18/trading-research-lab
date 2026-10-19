from copy import deepcopy
import json
import pytest
import dividend_shadow as shadow
import dividend_events_v63 as impl


def sample():
    doc = dict(document_id='synthetic', url='https://example.invalid/source',
               publication_date='2020-01-01', retrieved_at='2026-10-19T14:00:00Z',
               text='The quarterly dividend is USD 1.00 per common share. Payment is scheduled for July 10, 2026. The record date is June 26, 2026.')
    return [doc], [impl.extract(doc)]


def test_no_automatic_admission_even_when_consistent():
    docs, proposals = sample()
    result = shadow.build(docs, proposals, '2026-10-19T15:00:00Z')
    row = result['records'][0]
    assert row['historical_availability'] == 'observed_by_cutoff'
    assert row['queue_status'] == 'pending_human_review'
    assert not row['strategy_input_authorized'] and not row['trading_authorized']
    assert result['human_review_seconds'] is None


def test_publication_date_cannot_backdate_retrieval():
    docs, proposals = sample()
    assert shadow.build(docs, proposals, '2020-02-01T00:00:00Z')['records'][0]['historical_availability'] == 'after_cutoff'


@pytest.mark.parametrize('bad', [None, '2020-01-01', 'bad'])
def test_unknown_availability_blocks(bad):
    docs, _ = sample()
    docs[0]['retrieved_at'] = bad
    proposals = [impl.extract(docs[0])]
    row = shadow.build(docs, proposals, '2026-10-19T15:00:00Z')['records'][0]
    assert row['historical_availability'] == 'unknown'
    assert 'historical_availability_blocked' in row['reasons']


def test_source_mutation_rejected():
    docs, proposals = sample()
    docs[0]['text'] += ' Revised.'
    with pytest.raises(ValueError, match='binding'):
        shadow.build(docs, proposals)


@pytest.mark.parametrize('which', ['documents', 'proposals'])
def test_duplicate_identity_rejected(which):
    docs, proposals = sample()
    (docs if which == 'documents' else proposals).append(deepcopy((docs if which == 'documents' else proposals)[0]))
    with pytest.raises(ValueError, match='duplicate'):
        shadow.build(docs, proposals)


def test_empty_extraction_does_not_clear():
    docs, proposals = sample()
    proposals[0]['events'] = []
    row = shadow.build(docs, proposals)['records'][0]
    assert 'empty_extraction_requires_review' in row['reasons']
    assert row['queue_status'] == 'pending_human_review'


def test_no_input_mutation_or_output_alias():
    docs, proposals = sample()
    before = deepcopy((docs, proposals))
    result = shadow.build(docs, proposals)
    result['records'][0]['proposal']['events'].clear()
    assert (docs, proposals) == before


def test_output_refuses_overwrite(tmp_path):
    target = tmp_path / 'result.json'
    shadow.write_new(target, {'original': True})
    with pytest.raises(FileExistsError):
        shadow.write_new(target, {'original': False})
    assert json.loads(target.read_text()) == {'original': True}


def test_timezone_equivalence():
    docs, proposals = sample()
    assert shadow.build(docs, proposals, '2026-10-19T10:00:00-04:00')['records'][0]['historical_availability'] == 'observed_by_cutoff'
