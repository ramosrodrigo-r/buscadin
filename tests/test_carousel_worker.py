"""Security regressions for the process boundary; no model/network requests."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('carousel_worker', Path(__file__).parents[1] / 'scripts/carousel_worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_inference_does_not_inherit_worker_secrets_or_prompt_arguments(monkeypatch, tmp_path):
    executable = tmp_path / 'sandbox'
    executable.touch()
    monkeypatch.setattr(worker, 'HERMES_AGENT', executable)
    for key in ('CF_ACCESS_CLIENT_SECRET', 'BUSCADIN_CAROUSEL_WORKER_TOKEN', 'SSH_AUTH_SOCK', 'OPENAI_API_KEY'):
        monkeypatch.setenv(key, 'secret-never-forward')
    def launch(command, **kwargs):
        assert 'secret-never-forward' not in kwargs['env'].values()
        assert 'untrusted-job-data' not in ' '.join(command)
        assert 'untrusted-job-data' in kwargs['stdin'].read()
        assert kwargs['timeout'] == 300
        return SimpleNamespace(returncode=0, stdout='{"slides": []}', stderr='')
    monkeypatch.setattr(worker.subprocess, 'run', launch)
    assert worker.run_generation([{'title': 'untrusted-job-data'}]) == {'slides': []}


def test_inference_rejects_failed_sandbox_without_logging_output(monkeypatch, tmp_path, caplog):
    executable = tmp_path / 'sandbox'
    executable.touch()
    monkeypatch.setattr(worker, 'HERMES_AGENT', executable)
    monkeypatch.setattr(worker.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1, stdout='private', stderr='private'))
    with pytest.raises(RuntimeError, match='generation_failed'):
        worker.run_generation([{'id': 1}])
    assert 'private' not in caplog.text
