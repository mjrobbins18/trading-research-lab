"""Summarize observed open/closed/open coverage without inventing missed sessions."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def summarize(rows):
    ordered=sorted(rows,key=lambda r:r['checked_at'])
    opens=[];closed=[];witness=None
    for row in ordered:
        if row['status']!='observed':continue
        states=[row['market'][s]['market_open'] for s in ('SPY','BIL')]
        local=datetime.fromisoformat(row['checked_at']).astimezone(ZoneInfo('America/New_York'))
        if all(s is True for s in states):
            for first in opens:
                if first['date']!=local.date().isoformat():
                    between=[c for c in closed if first['time']<c<row['checked_at']]
                    if between and witness is None:witness={'first_open':first['time'],'closed':between[0],'later_open':row['checked_at']}
            opens.append({'date':local.date().isoformat(),'time':row['checked_at']})
        elif all(s is False for s in states):closed.append(row['checked_at'])
    return {'coverage_complete':witness is not None,'witness':witness,
            'open_session_dates':sorted({o['date'] for o in opens}),'closed_observations':len(closed),
            'successful_observations':sum(r['status']=='observed' for r in ordered),
            'halted_observations':sum(r['status']=='halted' for r in ordered),
            'latest_status':ordered[-1]['status'] if ordered else 'no_observations',
            'interpretation':'Coverage only. Historical halts and quote eligibility require separate review; this does not authorize trading.'}

if __name__=='__main__':
    source=Path('outputs/supervised-runner-observations.jsonl')
    result=summarize([json.loads(line) for line in source.read_text().splitlines() if line.strip()])
    Path('outputs/market-session-coverage.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
