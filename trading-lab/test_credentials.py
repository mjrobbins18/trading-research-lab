import pytest

from credentials import load_token


def test_private_file_and_environment_override(tmp_path, monkeypatch):
    monkeypatch.delenv('TIINGO_API_TOKEN', raising=False)
    p = tmp_path / 'token'
    p.write_text('test-placeholder\n')
    p.chmod(0o600)
    assert load_token(p) == 'test-placeholder'
    monkeypatch.setenv('TIINGO_API_TOKEN', 'environment-placeholder')
    assert load_token(p) == 'environment-placeholder'


def test_insecure_file_rejected_without_exposing_contents(tmp_path, monkeypatch):
    monkeypatch.delenv('TIINGO_API_TOKEN', raising=False)
    p = tmp_path / 'token'
    p.write_text('test-placeholder')
    p.chmod(0o644)
    with pytest.raises(SystemExit) as error:
        load_token(p)
    assert 'test-placeholder' not in str(error.value)
    p.chmod(0o600)
    link = tmp_path / 'link'
    link.symlink_to(p)
    with pytest.raises(SystemExit):
        load_token(link)
