"""Store paper-account credentials locally; never print credential values."""
import getpass
import json
import os
import stat
from pathlib import Path

PAPER_ENDPOINT = 'https://paper-api.alpaca.markets'
CREDENTIAL_FILE = Path(__file__).resolve().parent / '.local' / 'secrets' / 'alpaca-paper.json'


def validate(values):
    if values.get('endpoint') != PAPER_ENDPOINT:
        raise ValueError('Only the paper trading endpoint is supported.')
    for name in ('key_id', 'secret_key'):
        value = values.get(name)
        if not isinstance(value, str) or not value or any(c.isspace() for c in value):
            raise ValueError('Both credentials must be nonempty and contain no whitespace.')
    return values


def load_credentials(path=CREDENTIAL_FILE):
    if path.is_symlink():
        raise ValueError('Credential file must not be a symbolic link.')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('Credential file requires owner-only permissions (chmod 600).')
    try:
        values = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise ValueError('Invalid credential file; run setup again.') from None
    if not isinstance(values, dict):
        raise ValueError('Invalid credential file; run setup again.')
    return validate(values)


def save_credentials(values, path=CREDENTIAL_FILE):
    validate(values)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Credential location must not be a symbolic link.')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(values, stream)
        stream.write('\n')


if __name__ == '__main__':
    values = {'endpoint': PAPER_ENDPOINT,
              'key_id': getpass.getpass('Alpaca paper Key (hidden): ').strip(),
              'secret_key': getpass.getpass('Alpaca paper Secret Key (hidden): ').strip()}
    save_credentials(values)
    print('Paper credentials saved locally with owner-only permissions. No API requests or orders sent.')
