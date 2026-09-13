import time
from unittest.mock import patch

import pytest
from flask import Flask
from aj_shared import require_auth, require_auth_by_default, register_proxy
from tests.test_proxy import StubResponse


def make_app(base='https://core-a.example.invalid', secret='synthetic-platform'):
    app = Flask(base)
    app.secret_key = 'synthetic'
    app.config['PLATFORM_SECRET'] = secret
    @app.get('/api/apps-private')
    def private(): return {'private': True}
    @app.get('/json')
    @require_auth(json=True)
    def json_route(): return {'ok': True}
    @app.get('/page')
    def page(): return 'page'
    @app.get('/public/item')
    def public(): return 'public'
    @app.get('/public-sibling')
    def sibling(): return 'private'
    register_proxy(app, app_name='Synthetic', hq_base=base, configure_cors_now=False)
    require_auth_by_default(app, public_paths=['/public/'])
    return app


def test_exact_paths_and_json_page_failures():
    c = make_app().test_client()
    assert c.get('/api/apps-private').status_code == 401
    assert c.get('/json').status_code == 401
    assert c.get('/page').status_code == 302
    assert c.get('/public/item').status_code == 200
    assert c.get('/public-sibling').status_code == 302

@pytest.mark.parametrize('age',[1200,3600,-500,float('nan')])
def test_validate_and_guard_agree_on_expired_or_invalid_cache(age):
    c = make_app().test_client()
    with c.session_transaction() as session:
        session['_aj_user'] = {'id':1,'role':'staff'}
        session['_aj_user_cached_at'] = time.time()-age
    with patch('requests.request') as request:
        assert c.get('/auth/validate').status_code == 401
        assert c.get('/json').status_code == 401
        request.assert_not_called()


def test_app_configuration_and_transport_are_isolated():
    a = make_app(secret='synthetic-core-a')
    b = make_app('https://core-b.example.invalid', secret='synthetic-core-b')
    for app, host in [(a,'core-a'),(b,'core-b'),(a,'core-a')]:
        client = app.test_client()
        assert client.get('/page').location.startswith(f'https://{host}.example.invalid/login')
        with patch('requests.request',return_value=StubResponse(b'{"valid":true,"user":{"id":1,"role":"staff"}}')) as request:
            assert client.get('/json?token=synthetic').status_code == 200
            assert request.call_args.args[1].startswith(f'https://{host}.example.invalid/auth/validate')
            assert request.call_args.kwargs['allow_redirects'] is False
            assert request.call_args.kwargs['headers']['X-AJ-Key'] == 'synthetic-' + host
        with patch('requests.request',return_value=StubResponse(b'{"apps":[]}')) as request:
            assert client.get('/api/apps').status_code == 200
            assert request.call_args.args[1].startswith(f'https://{host}.example.invalid/api/apps')

@pytest.mark.parametrize('response',[StubResponse(b'<html>'), StubResponse(status_code=302), StubResponse(headers={'Content-Length':'999999999'})])
def test_auth_dependency_failure_is_not_expired_identity(response):
    client = make_app().test_client()
    with patch('requests.request',return_value=response):
        result = client.get('/json?token=synthetic')
    assert result.status_code == 502
    assert result.is_json
    assert 'reference_id' in result.json


def test_fastapi_real_transport_session_and_api_page_contracts():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from aj_shared.fastapi_integration import FastAPIHQ
    from aj_shared.hq_client import HQClient
    from unittest.mock import Mock
    transport = Mock()
    hq = FastAPIHQ(app_name='Synthetic',hq_base='https://core.example.invalid',app_base_url='https://app.example.invalid',app_secret_key='synthetic',platform_secret='synthetic',production=False,client=HQClient('https://core.example.invalid','synthetic',session=transport))
    app = FastAPI()
    hq.install(app, public_paths=['/public/'])
    hq.install_standard_routes(app)
    @app.get('/api/private')
    def private(): return {'ok':True}
    @app.get('/page')
    def page(): return 'page'
    @app.get('/public/item')
    def public(): return 'public'
    c = TestClient(app)
    assert c.get('/api/private').status_code == 401
    assert c.get('/page',follow_redirects=False).status_code == 307
    assert c.get('/public/item').status_code == 200
    transport.request.return_value = StubResponse(status_code=302)
    assert c.get('/api/private?token=synthetic').status_code == 502
    transport.request.return_value = StubResponse(b'{"valid":true,"user":{"id":1,"role":"staff"}}')
    assert c.get('/auth/validate?token=synthetic').status_code == 200
    assert c.get('/api/private').status_code == 200
    hq.session_ttl_seconds = 0
    assert c.get('/auth/validate').status_code == 401
    assert c.get('/api/private').status_code == 401
    assert transport.request.call_count == 2
    assert transport.request.call_args.kwargs['allow_redirects'] is False


def test_fastapi_rejects_mismatched_transport_destination():
    from aj_shared.fastapi_integration import FastAPIHQ
    from aj_shared.hq_client import HQClient
    with pytest.raises(ValueError,match='destinations'):
        FastAPIHQ(app_name='Synthetic',hq_base='https://a.example.invalid',app_base_url='https://app.example.invalid',app_secret_key='synthetic',platform_secret='synthetic',client=HQClient('https://b.example.invalid','synthetic'))
