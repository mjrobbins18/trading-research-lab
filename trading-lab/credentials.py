"""Local-only credential storage. Never include this file's data in archives."""
import getpass
import os
import stat
from pathlib import Path


TOKEN_FILE = Path(__file__).resolve().parent / '.local' / 'secrets' / 'tiingo-token'


def load_token(path=TOKEN_FILE):
    token = os.environ.get('TIINGO_API_TOKEN')
    if token:
        return token.strip()
    if not path.exists():
        raise SystemExit('Run credentials.py locally to save the Tiingo token.')
    if path.is_symlink():
        raise SystemExit('Credential file must not be a symbolic link.')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise SystemExit('Credential file must be owned by you and readable only by you (chmod 600).')
    token = path.read_text().strip()
    if not token or any(c.isspace() for c in token):
        raise SystemExit('Credential file is empty or contains whitespace inside the token.')
    return token


def save_token():
    if TOKEN_FILE.parent.is_symlink() or TOKEN_FILE.is_symlink():
        raise SystemExit('Credential location must not be a symbolic link.')
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    TOKEN_FILE.parent.chmod(0o700)
    token = getpass.getpass('Tiingo API token (hidden): ').strip()
    if not token or any(c.isspace() for c in token):
        raise SystemExit('Token was empty or contained whitespace; nothing saved.')
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(token + '\n')
    print('Saved locally with owner-only permissions. The downloader can now read it automatically.')


if __name__ == '__main__':
    save_token()
