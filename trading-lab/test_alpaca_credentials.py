import pytest
from alpaca_credentials import PAPER_ENDPOINT, load_credentials, save_credentials


def test_private_round_trip(tmp_path):
    path = tmp_path / 'private' / 'credentials.json'
    values = dict(endpoint=PAPER_ENDPOINT, key_id='placeholder-key', secret_key='placeholder-secret')
    save_credentials(values, path)
    assert load_credentials(path) == values
    assert path.stat().st_mode & 0o777 == 0o600
    path.chmod(0o644)
    with pytest.raises(ValueError, match='owner-only'):
        load_credentials(path)


def test_reject_live_endpoint_before_writing(tmp_path):
    path = tmp_path / 'credentials.json'
    with pytest.raises(ValueError, match='paper'):
        save_credentials(dict(endpoint='https://api.alpaca.markets', key_id='fake', secret_key='fake'), path)
    assert not path.exists()
