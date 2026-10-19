"""Provisional comparison against independently authored, unreviewed labels."""
from collections import Counter
import json
from pathlib import Path
import sys
import dividend_events_v63 as implementation
from dividend_shadow import build, digest, index, write_new
from evaluate_dividend_v6 import semantics


def claims(events):
    # Security identity keys the event. A wrong identity can therefore create
    # several unmatched fields; these are not counts of independent mistakes.
    result = Counter()
    for event in semantics(events):
        identity = json.dumps(event['security'], sort_keys=True)
        def visit(value, path):
            if isinstance(value, dict):
                for key, item in value.items():
                    visit(item, path + '.' + key)
            else:
                result[(identity, path, json.dumps(value, sort_keys=True))] += 1
        visit(event, 'event')
    return result


def compare(proposal, reference, doc):
    actual, expected = claims(proposal['events']), claims(reference['events'])
    missing, extra = expected - actual, actual - expected
    def rows(counter):
        return [{'security': json.loads(sec), 'field': path,
                 'value': json.loads(value), 'count': count}
                for (sec, path, value), count in sorted(counter.items())]
    return dict(semantic_match=semantics(proposal['events']) == semantics(reference['events']),
                missing_reference_claims=rows(missing), extra_candidate_claims=rows(extra),
                missing_claim_count=sum(missing.values()), extra_claim_count=sum(extra.values()),
                unresolved_presence_match=bool(proposal['unresolved']) == bool(reference['unresolved']),
                validation=implementation.validate(proposal, doc))


def run(directory):
    docs = json.loads((directory / 'documents.json').read_text())
    candidate = json.loads((directory / 'candidate.json').read_text())
    reference = json.loads((directory / 'reference.json').read_text())
    doc_index, ci, ri = index(docs, 'Documents'), index(candidate, 'Candidate'), index(reference, 'Reference')
    if doc_index.keys() != ci.keys() or ci.keys() != ri.keys():
        raise ValueError('Document identities differ')
    for doc in docs:
        for source in (ci, ri):
            if source[doc['document_id']]['source_sha256'] != implementation.source_digest(doc):
                raise ValueError('Source hash mismatch')
    parser = [implementation.extract(doc) for doc in docs]
    pi = index(parser, 'Parser')
    records = [dict(document_id=key, parser=compare(pi[key], ri[key], doc),
                    candidate=compare(ci[key], ri[key], doc)) for key, doc in doc_index.items()]
    summary = {}
    for arm in ('parser', 'candidate'):
        values = [r[arm] for r in records]
        summary[arm] = dict(documents=len(values), semantic_matches=sum(v['semantic_match'] for v in values),
                           missing_reference_claims=sum(v['missing_claim_count'] for v in values),
                           extra_claims_vs_reference=sum(v['extra_claim_count'] for v in values),
                           validator_status_counts=dict(Counter(v['validation']['status'] for v in values)),
                           semantic_disagreements_marked_consistent=sum(not v['semantic_match'] and v['validation']['status']=='consistent_research_record' for v in values),
                           matching_proposals_rejected=sum(v['semantic_match'] and v['validation']['status']=='rejected' for v in values),
                           human_review_queue=len(values), human_review_seconds=None)
    write_new(directory / 'parser.json', parser)
    write_new(directory / 'results.json', dict(summary=summary, records=records,
                reference_human_reviewed=False, exact_model_api_cost=None,
                trading_authorized=False,
                caveat='Unmatched field claims are provisional disagreements, not verified unsupported facts. Identity errors multiply field counts.'))
    write_new(directory / 'candidate-shadow.json', build(docs, candidate))
    write_new(directory / 'parser-shadow.json', build(docs, parser))
    # Counterfactual gate demonstration, not a trading backtest.
    write_new(directory / 'historical-gate-check.json', build(docs, candidate, '2020-01-01T00:00:00Z'))
    write_new(directory / 'evaluation-manifest.json', {
        'input_hashes': {name: digest(json.loads((directory / name).read_text()))
                         for name in ('documents.json', 'candidate.json', 'reference.json')},
        'reference_human_reviewed': False, 'parser_tuned': False})
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    run(Path(sys.argv[1]))
