"""Offline dividend research queue. No orders or automatic strategy admission."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import dividend_events_v63 as implementation


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp must be an ISO string with timezone')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp requires timezone')
    return result.astimezone(timezone.utc)


def index(items, label):
    if not isinstance(items, list):
        raise ValueError(label + ' must be a list')
    result = {}
    for item in items:
        key = item.get('document_id') if isinstance(item, dict) else None
        if not isinstance(key, str) or not key or key in result:
            raise ValueError(label + ' has invalid or duplicate document identity')
        result[key] = item
    return result


def build(documents, proposals, cutoff=None):
    docs = index(documents, 'Documents')
    proposed = index(proposals, 'Proposals')
    if docs.keys() != proposed.keys():
        raise ValueError('Proposal identities must match documents exactly')
    limit = timestamp(cutoff) if cutoff else None
    records = []
    for key, doc in docs.items():
        proposal = proposed[key]
        if not isinstance(doc.get('text'), str) or not doc['text'].strip():
            raise ValueError('Document text is missing')
        if proposal.get('source_sha256') != implementation.source_digest(doc):
            raise ValueError('Source binding mismatch: ' + key)
        validation = implementation.validate(proposal, doc)
        # Retrieval is a conservative observed availability bound. A publication
        # date is never substituted, and this does not authenticate metadata.
        observed = doc.get('retrieved_at')
        try:
            available = timestamp(observed)
        except (ValueError, TypeError):
            available = None
        availability = ('not_requested' if limit is None else
                        'unknown' if available is None else
                        'observed_by_cutoff' if available <= limit else 'after_cutoff')
        reasons = ['human_source_and_completeness_review_required']
        if not proposal.get('events'):
            reasons.append('empty_extraction_requires_review')
        if availability in ('unknown', 'after_cutoff'):
            reasons.append('historical_availability_blocked')
        reasons += validation['errors'] + validation['review_reasons']
        records.append(dict(document_id=key, source_sha256=implementation.source_digest(doc),
                            proposal_sha256=digest(proposal), source_url=doc.get('url'),
                            retrieved_at=observed, publication_date=doc.get('publication_date'),
                            historical_availability=availability,
                            proposal=deepcopy(proposal), validation=validation,
                            queue_status='pending_human_review', reasons=sorted(set(reasons)),
                            human_review_seconds=None, strategy_input_authorized=False,
                            trading_authorized=False, cash_available_confirmed=False))
    return dict(schema_version=1, implementation_revision='6.3',
                documents_sha256=digest(documents), proposals_sha256=digest(proposals),
                historical_cutoff=cutoff, records=records, trading_authorized=False,
                strategy_input_authorized=False, human_review_seconds=None,
                exact_model_api_cost=None)


def write_new(path, result):
    with Path(path).open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--documents', type=Path, required=True)
    parser.add_argument('--proposals', type=Path, required=True)
    parser.add_argument('--cutoff')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.documents.read_text()),
                   json.loads(args.proposals.read_text()), args.cutoff)
    write_new(args.output, result)
    print(json.dumps({'queued': len(result['records']), 'trading_authorized': False}))
