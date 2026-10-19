import json
from types import SimpleNamespace
from scheduled_observer_probe import run


def test_probe_runs_once_and_preserves_result(tmp_path):
    calls=[]
    def execute(*args, **kwargs):
        calls.append(args)
        assert kwargs['timeout']==180
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(status='observed', orders_submitted=0)), stderr='')
    assert run(tmp_path,tmp_path/'probe',execute)['status']=='observed'
    assert run(tmp_path,tmp_path/'probe',execute)['status']=='already_attempted'
    assert len(calls)==1


def test_crashed_attempt_cannot_repeat(tmp_path):
    path=tmp_path/'probe';path.mkdir();(path/'started.json').write_text('{}')
    def execute(*args,**kwargs): raise AssertionError('Must not run')
    assert run(tmp_path,path,execute)==dict(status='already_attempted',result_exists=False)


def test_failed_start_redacts_raw_output(tmp_path):
    def execute(*args,**kwargs):
        return SimpleNamespace(returncode=1, stdout='SECRET', stderr='SECRET')
    result=run(tmp_path,tmp_path/'probe',execute)
    assert result['status']=='failed' and 'SECRET' not in json.dumps(result)
