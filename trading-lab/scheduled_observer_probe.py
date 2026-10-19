"""Run one observer probe at most once; preserve evidence across scheduler retries."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / 'work/observer-service/scheduled-probe-01'


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run(root=ROOT, probe=PROBE, execute=subprocess.run):
    probe.mkdir(parents=True, exist_ok=True)
    try:
        with (probe/'started.json').open('x') as stream:
            json.dump({'started_at': datetime.now(timezone.utc).isoformat()}, stream)
            stream.flush(); os.fsync(stream.fileno())
    except FileExistsError:
        return {'status': 'already_attempted', 'result_exists': (probe/'result.json').exists()}
    sync_directory(probe)
    # The marker is retained even after process death. Never auto-repeat an ambiguous run.
    result = {'status': 'failed', 'orders_submitted': 0}
    try:
        completed = execute([str(root/'work/venv/bin/python'),
                             str(root/'outputs/trading-lab/observer_service.py')],
                            cwd=root, capture_output=True, text=True, timeout=180)
        result['exit_code'] = completed.returncode
        try:
            observation = json.loads(completed.stdout)
            if not isinstance(observation, dict): raise ValueError()
            result['observation'] = observation
            result['status'] = 'observed' if completed.returncode == 0 and observation.get('status') == 'observed' else 'halted'
        except (ValueError, TypeError):
            result['error_type'] = 'NoStructuredObserverResult'
        # Do not retain arbitrary stderr, which can contain request details.
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    state = root/'work/observer-service/state.sqlite'
    if state.exists():
        try:
            with sqlite3.connect(f'file:{state}?mode=ro', uri=True) as db:
                result['pending_alerts'] = [dict(id=row[0], payload=json.loads(row[1]), attempts=row[2])
                    for row in db.execute('SELECT id,payload,attempts FROM alerts WHERE delivered=0 ORDER BY id')]
        except Exception as exc:
            result['alert_read_error_type'] = type(exc).__name__
    result['completed_at'] = datetime.now(timezone.utc).isoformat()
    temporary = probe/'result.tmp'
    with temporary.open('w') as stream:
        json.dump(result, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, probe/'result.json')
    sync_directory(probe)
    return result


if __name__ == '__main__':
    print(json.dumps(run()))
