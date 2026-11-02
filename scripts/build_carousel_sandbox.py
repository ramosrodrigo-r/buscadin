#!/usr/bin/env python3
"""Build locally on the homelab from the audited Hermes runtime, without credentials."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

AUDITED_COMMIT = 'f0d94882e89ab8d4098b5bb2f166adfb9ee0a0ab'
root = Path.home() / '.hermes'
source = root / 'hermes-agent'
revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if revision != AUDITED_COMMIT:
    raise SystemExit('Review the new Hermes revision before rebuilding the inference runtime')
venvs = list(root.glob('installs/*/environments/*/venv'))
if len(venvs) != 1:
    raise SystemExit('Expected exactly one audited dependency environment')
python = root / 'tools/python-3.14.9+20261021-linux-x64'
with tempfile.TemporaryDirectory(prefix='buscadin-hermes-build-') as temp:
    build = Path(temp)
    runtime = build / 'runtime'
    runtime.mkdir()
    shutil.copytree(source, runtime / 'hermes-agent', symlinks=True,
                    ignore=shutil.ignore_patterns('.git', 'node_modules', 'tests', '.env*', '*.pem', '__pycache__'))
    shutil.copytree(root / 'installs', runtime / 'installs', symlinks=True)
    shutil.copytree(python, runtime / 'tools' / python.name, symlinks=True)
    (runtime / 'manifest.json').write_text(json.dumps({
        'repo': 'hermes-agent', 'venv': str(venvs[0].relative_to(root)), 'store': 'tools',
    }))
    for source_name, target_name in [('carousel-sandbox.Dockerfile', 'Dockerfile'),
                                     ('carousel_hermes_runner.py', 'carousel_hermes_runner.py')]:
        shutil.copyfile(Path(__file__).parent / source_name, build / target_name)
    subprocess.run(['docker', 'build', '-t', 'buscadin-hermes:isolated-v1', str(build)], check=True)
