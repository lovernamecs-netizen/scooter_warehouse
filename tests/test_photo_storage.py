import io,uuid,hashlib,json,base64,zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from sqlalchemy import select
from test_workflow import env
from server.models import Setting,User
from server.used_stock import put
from server.photo_backup import backup,verify,restore
from server.photo_tools import migrate
from server.db import Database

def image(w=2000,h=1500):
 b=io.BytesIO();im=Image.new('RGB',(w,h),'green');ex=Image.Exif();ex[274]=6;im.save(b,'JPEG',exif=ex);return b.getvalue()
def post(c,h,vehicle,stay,raw,uid=None,**extra):
 return c.post('/api/used/'+vehicle+'/upload',headers=h,data={'upload_id':uid or str(uuid.uuid4()),'stay_id':stay,'category':'damage','key':'left',**extra},files={'file':('original.jpg',raw,'image/jpeg')})
def test_original_idempotency_orientation_permissions(env):
 db,c,h,cmd,state,receive,v,*_=env;one=receive('USED');st=v(one)['stay_id'];raw=image();uid=str(uuid.uuid4())
 r=post(c,h,one,st,raw,uid);assert r.status_code==200,r.text;d=r.json();assert (d['width'],d['height'],d['orientation'])==(2000,1500,6)
 assert post(c,h,one,st,raw,uid).json()['id']==uid
 assert post(c,h,one,st,image(120,150),uid).status_code==409
 assert post(c,{},one,st,raw).status_code==401
 assert post(c,h,one,str(uuid.uuid4()),raw).status_code==404
 assert post(c,h,one,st,b'not-image').status_code==415
 assert post(c,h,one,st,raw,sha256='bad').status_code==422
 p=c.get('/api/used/'+one,headers=h).json();assert len(p['media'])==1
 assert c.get('/api/used/'+one+'/photos/'+uid,headers=h).content==raw
 preview=c.get('/api/used/'+one+'/photos/'+uid+'?preview=true',headers=h).content
 with Image.open(io.BytesIO(preview)) as im:assert im.height>im.width and max(im.size)<=1100
 with db.transaction() as s:assert s.get(Setting,'used_media_data:'+st+':'+uid) is None

def test_backup_restore_preserves_bytes_and_relocates(env,tmp_path):
 db,c,h,cmd,state,receive,v,*_=env;one=receive('USED');raw=image();d=post(c,h,one,v(one)['stay_id'],raw).json()
 result=backup(db);assert verify(result['file'])['files']==4
 restored=tmp_path/'restored';assert restore(result['file'],restored)['files']==4;assert not restored.exists()
 restore(result['file'],restored,True);new=Database('sqlite:///'+str(restored/'warehouse.db'));new.init()
 from server.photo_store import read_file
 with new.transaction() as s:
  row=s.get(Setting,'used_media:'+v(one)['stay_id']+':'+d['id']);assert read_file(s,row.value)[0]==raw
  assert str(restored) in s.get(Setting,'photo_storage').value['roots']['default']
 with zipfile.ZipFile(result['file'],'a') as z:z.writestr('unexpected','bad')
 import pytest
 with pytest.raises(ValueError):verify(result['file'])

def test_migration_retains_legacy_and_is_resumable(env):
 db,c,h,cmd,state,receive,v,*_=env;one=receive('USED');st=v(one)['stay_id'];raw=image();encoded=base64.b64encode(raw).decode();uid=str(uuid.uuid4())
 with db.transaction() as s:
  put(s,'used_media:'+st+':'+uid,{'id':uid,'category':'damage','key':'front','mime':'image/jpeg','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
  put(s,'used_media_data:'+st+':'+uid,{'original':encoded,'preview':encoded})
 report=migrate(db);assert not report['failed'];assert uid in report['migrated'];assert not migrate(db)['migrated']
 with db.transaction() as s:assert s.get(Setting,'used_media_data:'+st+':'+uid).value['original']==encoded
 assert c.get('/api/used/'+one+'/photos/'+uid,headers=h).content==raw

def test_interrupted_commit_retries_without_duplicate(env):
 db,c,h,cmd,state,receive,v,*_=env;one=receive('USED');st=v(one)['stay_id'];raw=image();uid=str(uuid.uuid4())
 from server.photo_store import upload,status
 import pytest
 with pytest.raises(RuntimeError):
  with db.transaction() as s:
   upload(s,s.scalar(select(User).where(User.role=='admin')),one,st,uid,'damage','left',raw)
   raise RuntimeError('simulated DB rollback after file write')
 with db.transaction() as s:assert any(x['id']==uid for x in status(s)['failures'])
 assert post(c,h,one,st,raw,uid).status_code==200
 assert len(c.get('/api/used/'+one,headers=h).json()['media'])==1
 with db.transaction() as s:assert not status(s)['failures']

def test_native_note_conflict_and_deleted_photo(env):
 db,c,h,cmd,state,receive,v,vc,*_=env;one=receive('USED');st=v(one)['stay_id'];raw=image(80,60)
 base=json.dumps({'status':'unchecked','note':''})
 result=post(c,h,one,st,raw,damage_note='흠집',damage_status='damaged',base_damage=base)
 assert result.status_code==200,result.text
 assert c.get('/api/used/'+one,headers=h).json()['profile']['damage']['left']['note']=='흠집'
 assert post(c,h,one,st,raw,damage_note='다른 메모',damage_status='damaged',base_damage=base).status_code==409
 d=result.json();vc('used_media',one,{'category':'damage','key':'left','id':d['id'],'remove':True})
 assert c.get('/api/used/'+one+'/photos/'+d['id'],headers=h).status_code==404
 with db.transaction() as s:
  from server.photo_store import read_file
  assert read_file(s,s.get(Setting,'used_media:'+st+':'+d['id']).value)[0]==raw

def test_storage_and_restore_admin_endpoints(env,tmp_path):
 db,c,h,*_=env
 folder=tmp_path/'other-images';backups=tmp_path/'backup-target'
 r=c.put('/api/photo-storage',headers=h,json={'root':str(folder),'backup_path':str(backups),'daily':True,'retention':2});assert r.status_code==200
 assert c.get('/api/photo-storage').status_code==401
 r=c.post('/api/photo-backup',headers=h);assert r.status_code==200,r.text
 items=c.get('/api/photo-backups',headers=h).json();name=items[0]['name']
 assert c.post('/api/photo-restore/preview',headers=h,json={'name':name}).status_code==200
 assert c.post('/api/photo-restore/stage',headers=h,json={'name':name,'destination':str(tmp_path/'recovered')}).status_code==422
 r=c.post('/api/photo-restore/stage',headers=h,json={'name':name,'destination':str(tmp_path/'recovered'),'confirm':'RESTORE'});assert r.status_code==200,r.text
 assert (tmp_path/'recovered/warehouse.db').is_file()
