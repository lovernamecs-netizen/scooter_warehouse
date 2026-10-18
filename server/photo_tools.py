"""Offline administrator tools. Never resets a database."""
import argparse,base64,json,uuid
from pathlib import Path
from sqlalchemy import select
from .db import Database
from .models import Setting,Stay,User
from . import photo_backup
from .photo_store import upload,read_file

def migrate(db):
 saved=photo_backup.backup(db);result={'backup':saved,'migrated':[],'failed':[]}
 with db.transaction() as s:
  user=s.scalar(select(User).where(User.role=='admin',User.active==True));assert user,'활성 관리자가 필요합니다.';uid=user.id
  keys=list(s.scalars(select(Setting.key).where(Setting.key.startswith('used_media:')|Setting.key.startswith('used_photo:'))))
 for k in keys:
  try:
   with db.transaction() as s:
    row=s.get(Setting,k);d=row.value
    if d.get('root_id') or d.get('deleted_at'):continue
    _,stay_id,key=k.split(':');st=s.get(Stay,stay_id)
    if k.startswith('used_photo:'):
     raw=base64.b64decode(d['jpeg'],validate=True);category='product';ident=str(uuid.uuid5(uuid.NAMESPACE_URL,k))
    else:
     blob=s.get(Setting,'used_media_data:'+stay_id+':'+key);raw=base64.b64decode((blob.value if blob else d)['original'],validate=True);category=d['category'];key=d['key'];ident=d['id']
    meta=upload(s,s.get(User,uid),st.vehicle_id,stay_id,ident,category,key,raw,d.get('at',''),migration=True)
    assert read_file(s,meta)[0]==raw
    result['migrated'].append(ident)
  except Exception as e:result['failed'].append({'key':k,'error':str(e)})
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','migrate','verify','restore']);p.add_argument('--file');p.add_argument('--destination');p.add_argument('--confirm',action='store_true');a=p.parse_args()
 if a.action=='verify':r=photo_backup.verify(a.file);r.pop('manifest',None)
 elif a.action=='restore':r=photo_backup.restore(a.file,a.destination,a.confirm)
 else:
  db=Database();db.init();r=migrate(db) if a.action=='migrate' else photo_backup.backup(db)
 print(json.dumps(r,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
