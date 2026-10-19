"""Score the frozen conflict experiment; never invokes a candidate or broker."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time
from distribution_intake import route

FIELDS = ('amount_per_share','ex_date','record_date','pay_date','currency','security_classes','components')


def normalize(field, value):
    if value is None:
        return None
    if field == 'amount_per_share':
        return Decimal(str(value))
    if field == 'security_classes':
        return tuple(sorted(value))
    if field == 'components':
        return tuple(sorted((v['kind'], Decimal(str(v['amount']))) for v in value))
    return value


def score(reference, answers):
    wanted = {r['case_id'] for r in reference}
    ids = [a['case_id'] for a in answers]
    if len(ids) != len(set(ids)) or set(ids) != wanted:
        raise ValueError('Missing, duplicate or unexpected case IDs')
    indexed = {a['case_id']:a for a in answers}
    rows = []
    for expected in reference:
        actual = indexed[expected['case_id']]
        correct = []; wrong = []; unsupported = []
        for field in FIELDS:
            value = actual.get('resolved',{}).get(field)
            if field in actual.get('resolved',{}) and normalize(field,value) == normalize(field,expected['resolved'][field]):
                correct.append(field)
            else:
                wrong.append(field)
                if value not in (None,[]): unsupported.append(field)
        missed = sorted(set(expected['issue_codes'])-set(actual['issue_codes']))
        extra = sorted(set(actual['issue_codes'])-set(expected['issue_codes']))
        decision_match = actual['decision'] == expected['decision']
        citation_match = set(actual['evidence_ids']) == set(expected['evidence_ids'])
        review_match = actual['needs_human_review'] is True
        rows.append(dict(case_id=expected['case_id'], correct_fields=correct, wrong_fields=wrong,
                         incorrect_populated_fields=unsupported, missed_issues=missed, extra_issues=extra,
                         issue_true_positives=len(set(expected['issue_codes'])&set(actual['issue_codes'])),
                         decision_match=decision_match, citation_ids_match=citation_match, retains_review=review_match,
                         exact_match=not(wrong or missed or extra) and decision_match and citation_match and review_match))
    return dict(cases=rows, exact_matches=sum(r['exact_match'] for r in rows),
                correct_fields=sum(len(r['correct_fields']) for r in rows), total_fields=len(FIELDS)*len(rows),
                missed_issues=sum(len(r['missed_issues']) for r in rows),
                extra_issues=sum(len(r['extra_issues']) for r in rows),
                issue_true_positives=sum(r['issue_true_positives'] for r in rows),
                incorrect_populated_fields=sum(len(r['incorrect_populated_fields']) for r in rows),
                human_review_cases=sum(r['retains_review'] for r in rows),
                human_review_seconds=None, exact_api_cost=None)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/conflict-specialist-02/results.json'))
    args = parser.parse_args()
    root=Path('outputs/conflict-specialist-02')
    manifest=json.loads((root/'frozen-manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen evaluation input changed')
    start=time.perf_counter()
    baseline=route(json.loads((root/'baseline-input.json').read_text()))
    elapsed=time.perf_counter()-start
    result=score(json.loads((root/'reference.json').read_text()),json.loads((root/'candidate-response.json').read_text()))
    result['baseline']=dict(records=baseline, elapsed_seconds=elapsed,
        review_cases=sum(r['route']=='specialist_review' for r in baseline),
        automated_field_corrections=0,
        scope='Structured triage only; no prose access or corrective extraction. Not a like-for-like language benchmark.')
    result['candidate_sha256']=hashlib.sha256((root/'candidate-response.json').read_bytes()).hexdigest()
    with args.output.open('x') as stream: json.dump(result,stream,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','baseline')},indent=2))


if __name__=='__main__': main()
