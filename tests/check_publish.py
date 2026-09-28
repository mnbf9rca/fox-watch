"""Exercise the real config-ownership guard without running publish.sh or Cloudflare."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

source = (Path(__file__).resolve().parents[1] / 'vps/publish.sh').read_text()
# Only this self-contained shell guard runs, against a temporary config file.
guard = source.partition('# BEGIN existing-config guard\n')[2].partition('# END existing-config guard')[0]
expected_id = 'f70ff985-a4ef-4643-bbbc-4a0ed4fc8415'
credentials = '/etc/cloudflared/foxwatch.json'
with TemporaryDirectory() as work:
    config = Path(work) / 'config.yml'
    command = guard.replace('/etc/cloudflared/config.yml', str(config))
    for content, accepted in (
        (None, True),
        (f'tunnel: {expected_id}\ncredentials-file: {credentials}\n', True),
        (f'tunnel: 11111111-1111-4111-8111-111111111111\ncredentials-file: {credentials}\n', False),
        (f'tunnel: {expected_id}\ncredentials-file: /etc/cloudflared/unrelated.json\n', False),
    ):
        if content is not None:
            config.write_text(content)
        result = subprocess.run(['bash', '-c', 'set -euo pipefail\ntunnel_id=$1\n' + command,
                                 'check', expected_id], capture_output=True, text=True)
        assert (result.returncode == 0) == accepted, (content, result.stdout, result.stderr)
        if content is not None:
            assert config.read_text() == content, 'existing config was modified'
print('PASS publication guard: absent/matching config accepted; unrelated tunnel/credentials refused unchanged; publish.sh not executed')
