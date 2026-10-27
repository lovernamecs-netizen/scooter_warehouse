from test_workflow import env
from pathlib import Path


def test_ocr_removed(env):
    client=env[1]
    schema=client.get('/openapi.json').json()
    assert not any('registration-ocr' in path for path in schema['paths'])
    for path in ('/registration-ocr.html','/registration-ocr.js','/registration-ocr.css','/api/registration-ocr/installer','/api/tools/registration-ocr/installer'):
        assert client.get(path).status_code==404
    app=(Path(__file__).parents[1]/'web/app.js').read_text(encoding='utf8')
    assert 'registration-ocr' not in app
    assert 'ocr-connector' not in app
