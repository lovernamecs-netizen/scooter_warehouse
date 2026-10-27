import json
from server.google_login import config

def test_local_oauth_config_and_environment_precedence(tmp_path,monkeypatch):
 for k in ['CLIENT_ID','CLIENT_SECRET','REDIRECT_URI']:monkeypatch.delenv('WAREHOUSE_GOOGLE_'+k,raising=False)
 path=tmp_path/'oauth.json';monkeypatch.setenv('WAREHOUSE_GOOGLE_CONFIG',str(path))
 assert not any(config().values())
 path.write_text(json.dumps({'client_id':'synthetic-client','client_secret':'synthetic-secret','redirect_uri':'http://127.0.0.1:8765/api/google/callback'}))
 assert config()['CLIENT_ID']=='synthetic-client'
 monkeypatch.setenv('WAREHOUSE_GOOGLE_CLIENT_ID','environment-client')
 assert config()['CLIENT_ID']=='environment-client' and not config()['CLIENT_SECRET']
 monkeypatch.delenv('WAREHOUSE_GOOGLE_CLIENT_ID');path.write_text('{invalid')
 assert not any(config().values())
 path.write_text('[]');assert not any(config().values())
