import json
import fitz
import pytest
from server.insurance_documents import iter_pdf, InsuranceDocumentError
from test_workflow import env


def pdf_bytes(count):
    with fitz.open() as doc:
        for n in range(count):
            page=doc.new_page(width=600,height=850)
            page.insert_text((25,210),f"Page {n+1}")
        return doc.tobytes()


def test_real_500_pages_streamed_without_accumulation():
    events=iter_pdf(pdf_bytes(500));assert next(events)=={'type':'start','total':500}
    count=0
    for event in events:
        if event['type']=='page':
            count+=1;record=event['record']
            assert record['page']==count and record['within_limit']
            assert record['size_bytes']<=199000
        else:assert event['type']=='complete'
    assert count==500


def test_500_page_limit_and_oversized_rejected():
    events=iter_pdf(pdf_bytes(500));assert next(events)['total']==500;events.close()
    with pytest.raises(InsuranceDocumentError,match='500'):next(iter_pdf(pdf_bytes(501)))
    with pytest.raises(InsuranceDocumentError,match='35MB'):next(iter_pdf(b'x'*(35*1024*1024+1)))


def test_stream_route_errors_release_lock_and_keep_legacy(env):
    _,client,headers,*_=env
    route='/api/insurance/convert?stream=1'
    response=client.post(route,headers=headers,files={'file':('test.pdf',pdf_bytes(3),'application/pdf')})
    events=[json.loads(line) for line in response.text.splitlines()]
    assert response.status_code==200 and events[0]['total']==3
    assert [x['record']['page'] for x in events if x['type']=='page']==[1,2,3]
    assert events[-1]['type']=='complete'
    assert client.post(route,headers=headers,files={'file':('bad.pdf',b'bad','application/pdf')}).status_code==422
    response=client.post('/api/insurance/convert',headers=headers,files={'file':('test.pdf',pdf_bytes(1),'application/pdf')})
    assert response.status_code==200 and len(response.json()['pages'])==1


def test_stream_mid_file_failure_reports_error_and_unlocks(env):
    _,client,headers,*_=env
    with fitz.open() as doc:
        doc.new_page(width=600,height=850);doc.new_page(width=100,height=100);data=doc.tobytes()
    response=client.post('/api/insurance/convert?stream=1',headers=headers,files={'file':('badpage.pdf',data,'application/pdf')})
    events=[json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type']=='error' and not any(x['type']=='complete' for x in events)
    response=client.post('/api/insurance/convert?stream=1',headers=headers,files={'file':('good.pdf',pdf_bytes(1),'application/pdf')})
    assert json.loads(response.text.splitlines()[-1])['type']=='complete'
