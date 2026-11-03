"""Security regressions for the process boundary; no model/network requests."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import json

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


def test_postiz_draft_payload_never_schedules_or_publishes(monkeypatch):
    monkeypatch.setattr(worker, 'POSTIZ_INTEGRATION_ID', 'instagram-channel')
    monkeypatch.setattr(worker, 'POSTIZ_PLATFORM', 'instagram-standalone')
    def fake_request(path, body, content_type, *, creating=False):
        assert path == '/posts' and creating and content_type == 'application/json'
        payload = json.loads(body)
        assert payload['type'] == 'draft'
        assert payload['posts'][0]['integration'] == {'id': 'instagram-channel'}
        assert payload['posts'][0]['settings'] == {'__type': 'instagram-standalone', 'post_type': 'post'}
        assert [item['id'] for item in payload['posts'][0]['value'][0]['image']] == ['first', 'second']
        return [{'postId': 'post-123', 'integration': 'instagram-channel'}]
    monkeypatch.setattr(worker, 'postiz_request', fake_request)
    assert worker.postiz_create_draft('Legenda', [{'id': 'first', 'path': 'https://example.test/1.png'},
                                                  {'id': 'second', 'path': 'https://example.test/2.png'}]) == 'post-123'


def test_postiz_uncertain_creation_never_retries_the_post(monkeypatch):
    monkeypatch.setattr(worker, 'POSTIZ_API_KEY', 'test-key')
    monkeypatch.setattr(worker, 'POSTIZ_INTEGRATION_ID', 'test-channel')
    monkeypatch.setattr(worker, 'postiz_channel_ready', lambda: True)
    calls = []
    def fake_api(path, payload, **kwargs):
        calls.append(path)
        if path.endswith('/claim'):
            return {'draft_id': 7, 'caption': 'Legenda', 'slide_count': 3}
        if path.endswith('/image'):
            return {'image': 'ignored'}
        return {'ok': True}
    monkeypatch.setattr(worker, 'api', fake_api)
    monkeypatch.setattr(worker, 'postiz_upload', lambda *args: {'id': 'img', 'path': 'https://example.test/img'})
    def uncertain(*args):
        raise worker.PostizError('timeout', uncertain=True)
    monkeypatch.setattr(worker, 'postiz_create_draft', uncertain)
    assert worker.handle_postiz() is True
    assert calls.count('/api/worker/postiz/creating') == 1
    assert calls.count('/api/worker/postiz/fail') == 1
    assert '/api/worker/postiz/complete' not in calls
