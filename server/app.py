import os,time,json,hashlib,threading,zipfile,uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request,HTTPException,UploadFile,File,Form
from fastapi.responses import JSONResponse,Response,FileResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import Database
from .models import *
from .security import authorize,issue,verify
from .domain import command,state,report,admin,need,iso,vehicle_dto
from .integration import GoogleSheetFileAdapter,workbook
from . import parts

def create_app(database=None):
    db=database or Database()
    @asynccontextmanager
    async def lifespan(app):
        from .photo_backup import scheduler
        if database is None:
            from .storage_paths import require_existing
            require_existing(db.engine)
        db.init();stop=threading.Event();thread=threading.Thread(target=scheduler,args=(db,stop),daemon=True);thread.start()
        from .vehicle_inventory import scheduler as inventory_scheduler
        inventory_thread=threading.Thread(target=inventory_scheduler,args=(db,stop),daemon=True);inventory_thread.start()
        try:yield
        finally:stop.set();thread.join(timeout=2);inventory_thread.join(timeout=5)
    app=FastAPI(title='Scooter Warehouse',version='1.0.31',lifespan=lifespan)
    app.state.db=db
    from .errors import install
    install(app,db)
    attempts={};attempt_lock=threading.Lock()
    def user(s,request):return authorize(s,request.headers.get('Authorization','').removeprefix('Bearer '))
    from .google_login import install as install_google_login
    install_google_login(app,db,user)
    @app.exception_handler(IntegrityError)
    async def integrity(request,exc):return JSONResponse(status_code=409,content={'detail':'중복 등록 또는 다른 기기와의 충돌입니다. 최신 정보를 다시 확인하세요.'})
    @app.exception_handler(KeyError)
    async def missing(request,exc):return JSONResponse(status_code=422,content={'detail':'필수 입력값이 누락되었습니다.'})
    @app.middleware('http')
    async def headers(request,call_next):
        request.state.request_id=uuid.uuid4().hex
        try:
            length=int(request.headers.get('content-length','0') or 0)
        except ValueError:return app.state.error_response(request,400,'요청 형식이 올바르지 않습니다.')
        if length>38_000_000:return app.state.error_response(request,413,'요청 크기가 너무 큽니다.')
        try:response=await call_next(request)
        except Exception as exc:response=app.state.unexpected_error(request,exc)
        response.headers['X-Request-ID']=request.state.request_id
        response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
        return response
    @app.post('/api/layout/preview')
    def preview_layout(p:dict,request:Request):
        from .layout_ops import plan
        with db.transaction() as s:
            u=user(s,request);admin(u);return plan(s,p)
    @app.get('/health')
    def health():return {'ok':True,'version':app.version}
    @app.post('/api/login')
    def login(p:dict,request:Request):
        name=str(p.get('username',''))[:80];key=(request.client.host,name);t=time.monotonic()
        with attempt_lock:
            attempts[key]=[v for v in attempts.get(key,[]) if t-v<900]
            if len(attempts[key])>=10:raise HTTPException(429,'로그인 시도가 많습니다. 15분 후 다시 시도하세요.')
            attempts[key].append(t)
        with db.transaction() as s:
            u=s.scalar(select(User).where(User.username==name))
            if not u or not u.active or not verify(str(p.get('password','')),u.password):raise HTTPException(401,'아이디 또는 비밀번호를 확인하세요.')
            token=issue(s,u)
        with attempt_lock:attempts.pop(key,None)
        return {'token':token}
    @app.post('/api/logout')
    def logout(request:Request):
        with db.transaction() as s:
            user(s,request);tok=request.headers['Authorization'].removeprefix('Bearer ');sess=s.get(Session,hashlib.sha256(tok.encode()).hexdigest());s.delete(sess)
        return {'ok':True}
    @app.get('/api/notifications')
    def notifications(request:Request,after:str|None=None):
        from .notifications import feed
        with db.transaction() as s:return feed(s,user(s,request),after)
    @app.put('/api/notifications/preferences')
    def notification_preferences(p:dict,request:Request):
        from .notifications import save
        with db.transaction() as s:return save(s,user(s,request),p)
    @app.get('/api/used/{vehicle_id}')
    def used_page(vehicle_id:str,request:Request,stay_id:str|None=None):
        from .used_stock import page
        with db.transaction() as s:return page(s,user(s,request),vehicle_id,stay_id)
    @app.get('/api/used/{vehicle_id}/photos/{photo_id}')
    def used_photo_download(vehicle_id:str,photo_id:str,request:Request,preview:bool=False,stay_id:str|None=None):
        from .used_stock import media_download
        with db.transaction() as s:raw,mime,name=media_download(s,user(s,request),vehicle_id,photo_id=photo_id,preview=preview,stay_id=stay_id)
        return Response(raw,media_type=mime,headers={'Content-Disposition':'attachment; filename="'+name+'"','Cache-Control':'no-store'})
    @app.get('/api/used/{vehicle_id}/download')
    def used_zip(vehicle_id:str,request:Request,category:str='product',stay_id:str|None=None):
        from .used_stock import media_download
        with db.transaction() as s:raw,mime,name=media_download(s,user(s,request),vehicle_id,category=category,stay_id=stay_id)
        def chunks():
            try:
                while chunk:=raw.read(1024*1024):yield chunk
            finally:raw.close()
        return StreamingResponse(chunks(),media_type=mime,headers={'Content-Disposition':'attachment; filename="'+name+'"','Cache-Control':'no-store'})
    @app.post('/api/used/{vehicle_id}/upload')
    async def photo_upload(vehicle_id:str,request:Request,file:UploadFile=File(...),upload_id:str=Form(...),stay_id:str=Form(...),category:str=Form(...),key:str=Form(...),captured_at:str=Form(''),sha256:str=Form(''),damage_note:str=Form(''),damage_status:str=Form(''),base_damage:str=Form('')):
        from .photo_store import upload,LIMIT
        with db.transaction() as s:need(user(s,request).role in ['admin','worker'],'권한이 없습니다.',403)
        raw=await file.read(LIMIT+1)
        with db.transaction() as s:
            u=user(s,request)
            from .used_stock import put,read
            if category=='damage' and damage_status and not s.get(Setting,'photo_upload:'+upload_id):
                need(u.role in ['admin','worker'],'사진 등록 권한이 없습니다.',403)
                need(damage_status in ['unchecked','normal','damaged','repaired'] and len(damage_note)<=1000,'파손 메모 형식 오류')
                st=s.get(Stay,stay_id);need(st is not None and st.vehicle_id==vehicle_id,'입고 회차 오류',409)
                profile=read(s,st);damage=dict(profile.get('damage',{}));previous=damage.get(key,{'status':'unchecked','note':''})
                try:base=json.loads(base_damage)
                except ValueError:raise HTTPException(422,'파손 메모 기준 형식 오류')
                desired={'status':damage_status,'note':damage_note}
                need(previous==base or previous==desired,'다른 작업자가 파손 메모를 변경했습니다. PC에서 확인하세요. 촬영 원본은 휴대폰에 남아 있습니다.',409)
                damage[key]=desired;profile['damage']=damage;put(s,'used_profile:'+stay_id,profile)
            return upload(s,u,vehicle_id,stay_id,upload_id,category,key,raw,captured_at,sha256)
    @app.get('/api/used/{vehicle_id}/metadata')
    def photo_metadata(vehicle_id:str,request:Request,stay_id:str|None=None):
        from .used_stock import page
        with db.transaction() as s:
            d=page(s,user(s,request),vehicle_id,stay_id);d.pop('photos',None)
            from .photo_store import config,safe,atomic
            cfg=config(s)
            if d['stay_id']:atomic(safe(cfg['roots'][cfg['active']],vehicle_id+'/'+d['stay_id']+'/Metadata/vehicle.json'),json.dumps(d,ensure_ascii=False,default=str).encode())
            return d
    @app.get('/api/photo-storage')
    def photo_storage(request:Request):
        from .photo_store import status
        with db.transaction() as s:admin(user(s,request));return status(s)
    @app.put('/api/photo-storage')
    def photo_settings(p:dict,request:Request):
        from .photo_store import configure
        with db.transaction() as s:admin(user(s,request));return configure(s,p)
    @app.post('/api/photo-backup')
    def photo_backup(request:Request):
        from .photo_backup import backup
        with db.transaction() as s:admin(user(s,request))
        try:return backup(db)
        except HTTPException:raise
        except Exception as e:return app.state.unexpected_error(request,e)
    @app.get('/api/photo-backups')
    def photo_backups(request:Request):
        from .photo_store import config
        with db.transaction() as s:
            admin(user(s,request));root=Path(config(s)['backup_path'])
            return [{'name':p.name,'size':p.stat().st_size} for p in sorted(root.glob('ScooterWarehouse-*.zip'),reverse=True)]
    @app.post('/api/photo-restore/preview')
    def photo_restore_preview(p:dict,request:Request):
        from .photo_store import config,safe
        from .photo_backup import restore
        with db.transaction() as s:
            admin(user(s,request));root=config(s)['backup_path'];name=p.get('name','');need(Path(name).name==name and name.endswith('.zip'),'백업 이름 오류')
        try:return restore(safe(root,name),None,False)
        except HTTPException:raise
        except ValueError:raise HTTPException(422,'백업 파일과 복구 대상 폴더를 확인하세요.')
        except Exception as e:return app.state.unexpected_error(request,e)
    @app.post('/api/photo-restore/stage')
    def photo_restore_stage(p:dict,request:Request):
        from .photo_store import config,safe
        from .photo_backup import restore
        with db.transaction() as s:
            admin(user(s,request));root=config(s)['backup_path'];name=p.get('name','');need(Path(name).name==name and name.endswith('.zip'),'백업 이름 오류')
        need(p.get('confirm')=='RESTORE','복구 확인이 필요합니다.')
        destination=Path(p.get('destination',''));need(destination.is_absolute(),'새 복구 폴더의 절대 경로를 입력하세요.')
        try:return restore(safe(root,name),destination,True)
        except HTTPException:raise
        except ValueError:raise HTTPException(422,'백업 파일과 복구 대상 폴더를 확인하세요.')
        except Exception as e:return app.state.unexpected_error(request,e)
    @app.post('/api/used/{vehicle_id}/open-folder')
    def open_folder(vehicle_id:str,request:Request):
        from .photo_store import config,safe
        from .used_stock import stay
        with db.transaction() as s:
            admin(user(s,request));v=s.get(Vehicle,vehicle_id);need(v is not None,'차량이 없습니다.',404)
            need(os.name=='nt','폴더 열기는 Windows 서버에서만 가능합니다.')
            cfg=config(s);paths=[safe(root,v.id) for root in cfg['roots'].values()];paths=[p for p in paths if p.is_dir()]
            need(bool(paths),'저장된 차량 폴더가 없습니다.',404)
            for path in paths:os.startfile(str(path))
            return {'ok':True}
    @app.post('/api/vin/ocr')
    def local_ocr(p:dict,request:Request):
        from .vin_ocr import recognize
        with db.transaction() as s:need(user(s,request).role in ['admin','worker'],'권한이 없습니다.',403)
        return recognize(p.get('image',''))
    @app.get('/api/state')
    def get_state(request:Request):
        with db.transaction() as s:
            u=user(s,request);result=state(s,u)
            if u.role=='admin':
                from .photo_store import backup_warnings
                result['backup_warnings']=backup_warnings(s)
            return result
    @app.post('/api/command')
    def mutate(body:dict,request:Request):
        with db.transaction() as s:return command(s,user(s,request),body)
    @app.post('/api/purchases/google')
    def purchase_google(request:Request,p:dict):
        with db.read() as s:
            u=user(s,request);ident=u.id;need(u.role in ['admin','worker'],'구매 자료 접근 권한이 없습니다.',403)
        from .google_purchase import read
        from .google_login import token,connection_key
        return read(p.get('url',''),p.get('sheet',''),access_token=token(connection_key(ident,request)))
    @app.post('/api/purchases/xlsx')
    async def purchase_xlsx(request:Request,file:UploadFile=File(...)):
        with db.read() as s:
            u=user(s,request);need(u.role in ['admin','worker'],'구매 자료 접근 권한이 없습니다.',403)
        data=await file.read(20_000_001)
        from .purchase_xlsx import parse
        return await run_in_threadpool(parse,data,file.filename or '')
    @app.get('/api/purchases/review')
    def purchase_review_list(request:Request):
        from .purchase_review import view
        with db.transaction() as s:
            u=user(s,request);need(u.role in ['admin','worker'],'접근 권한이 없습니다.',403)
            return view(s)
    @app.post('/api/purchases/review')
    def purchase_review_mutate(request:Request,p:dict):
        from .purchase_review import mutate
        with db.transaction() as s:return mutate(s,user(s,request),p)
    @app.post('/api/purchases/import')
    def purchase_import_all(request:Request,p:dict):
        from .purchase_review import import_all
        with db.transaction() as s:return import_all(s,user(s,request),p)
    @app.post('/api/purchases/source-scan')
    def purchase_source_scan(request:Request,p:dict):
        from .purchase_month import store_source
        with db.transaction() as s:return store_source(s,user(s,request),p)
    @app.get('/api/purchases/month-history')
    def purchase_month_history(request:Request,month:str):
        from .purchase_month import approvals
        with db.read() as s:return approvals(s,user(s,request),month)
    @app.get('/api/purchases/month-snapshot/{ident}')
    def purchase_month_snapshot(ident:str,request:Request,page:int=0):
        from .purchase_month import approved_snapshot
        with db.read() as s:return approved_snapshot(s,user(s,request),ident,page)
    @app.get('/api/purchases/month')
    def purchase_month(request:Request,month:str,page:int=0,namespace:str=''):
        from .purchase_month import scan
        with db.read() as s:return scan(s,user(s,request),month,page,namespace)
    @app.post('/api/purchases/month')
    def purchase_month_confirm(request:Request,p:dict):
        from .purchase_month import confirm
        with db.transaction() as s:return confirm(s,user(s,request),p)
    @app.get('/api/purchases/source-review')
    def purchase_source_review(request:Request,namespace:str,through:int):
        from .purchase_bookmark import review
        with db.read() as s:
            result=review(s,user(s,request),namespace,through)
            result.pop('bindings',None);return result
    @app.post('/api/purchases/source-review')
    def purchase_source_confirm(request:Request,p:dict):
        from .purchase_bookmark import confirm
        with db.transaction() as s:return confirm(s,user(s,request),p)
    @app.get('/api/purchases/sources')
    def purchase_sources(request:Request):
        from .purchase_queries import sources
        with db.read() as s:return sources(s,user(s,request))
    @app.get('/api/purchases/conflicts')
    def purchase_conflicts(request:Request,page:int=0):
        from .purchase_review import conflicts
        with db.read() as s:return conflicts(s,user(s,request),page)
    @app.get('/api/purchases/review-summary')
    def purchase_review_summary(request:Request,through:str,page:int=0):
        from .purchase_review import summary
        with db.read() as s:return summary(s,user(s,request),through,page)
    @app.get('/api/purchases/page')
    def purchase_page(request:Request,month:str,selected:str='',page:int=0,filters:str='{}',deleted:bool=False):
        from .purchase_queries import page as query
        with db.read() as s:return query(s,user(s,request),month,selected,page,filters,deleted)
    @app.get('/api/purchases/history/{ident}')
    def purchase_history(ident:str,request:Request,page:int=0):
        from .purchase_queries import history
        with db.read() as s:return history(s,user(s,request),ident,page)
    @app.get('/api/purchases/requests/{ident}')
    def purchase_request_status(ident:str,request:Request):
        with db.read() as s:
            u=user(s,request);entry=s.get(Command,ident)
            need(not entry or entry.user_id==u.id,'다른 계정의 요청입니다.',403)
            return {'state':'committed' if entry else 'unconfirmed','result':entry.result if entry else None}
    @app.get('/api/purchases')
    def purchase_list(request:Request):
        from .purchase_sheet import listing
        with db.read() as s:return listing(s,user(s,request))
    @app.post('/api/purchases/preview')
    def purchase_preview(request:Request,p:dict):
        from .purchase_sheet import preview
        with db.read() as s:return preview(s,user(s,request),p)
    @app.post('/api/purchases/apply')
    def purchase_apply(request:Request,p:dict):
        from .purchase_sheet import apply
        with db.transaction() as s:return apply(s,user(s,request),p)
    @app.get('/api/vehicle-inventory')
    def vehicle_inventory_view(request:Request,day:str,month:str):
        from .vehicle_inventory import view
        with db.transaction() as s:return view(s,user(s,request),day,month)
    @app.get('/api/vehicle-inventory/candidates')
    def vehicle_inventory_candidates(request:Request,day:str):
        from .vehicle_inventory import candidates
        with db.transaction() as s:return candidates(s,user(s,request),day)
    @app.post('/api/vehicle-inventory/command')
    def vehicle_inventory_command(request:Request,p:dict):
        from .vehicle_inventory import mutate
        with db.transaction() as s:return mutate(s,user(s,request),p)
    @app.get('/api/report/{day}')
    def daily(day:str,request:Request):
        with db.transaction() as s:
            u=user(s,request);need(u.role!='ubis','권한이 없습니다.',403);return report(s,day)
    @app.get('/api/history/{vehicle_id}')
    def history(vehicle_id:str,request:Request):
        with db.transaction() as s:
            u=user(s,request);need(u.role!='ubis','권한이 없습니다.',403)
            return [{'id':h.id,'at':iso(h.at),'event':h.event,'actor':h.actor,'data':h.data} for h in s.scalars(select(History).where(History.vehicle_id==vehicle_id).order_by(History.at))]
    @app.get('/api/outbound')
    def outbound(request:Request):
        with db.transaction() as s:
            u=user(s,request);need(u.role!='ubis','권한이 없습니다.',403)
            return [{'id':o.id,'vehicle_id':o.vehicle_id,'at':iso(o.at),'day':o.day,'snapshot':o.snapshot,'adjustments':[{'kind':a.kind,'reason':a.reason,'at':iso(a.at),'detail':a.detail} for a in s.scalars(select(Adjustment).where(Adjustment.outbound_id==o.id))]} for o in s.scalars(select(Outbound).order_by(Outbound.at.desc()))]
    @app.post('/api/customers/search')
    def customer_search(request:Request,p:dict):
        from .customer_privacy import search
        with db.transaction() as s:return search(s,user(s,request),p)
    @app.post('/api/customers')
    def customer_create(request:Request,p:dict):
        from .customer_privacy import create
        with db.transaction() as s:return create(s,user(s,request),p)
    @app.post('/api/customers/orders')
    def customer_orders(request:Request,p:dict):
        from .customer_privacy import order_names
        with db.transaction() as s:return order_names(s,user(s,request),p.get('order_ids'))
    @app.get('/api/customers/order/{order_id}')
    def customer_order(order_id:str,request:Request):
        from .customer_privacy import order_name
        with db.transaction() as s:return order_name(s,user(s,request),order_id)
    @app.get('/api/customers/{customer_id}/history')
    def customer_history(customer_id:str,request:Request,after:str=''):
        from .customer_privacy import history
        with db.transaction() as s:return history(s,user(s,request),customer_id,after)
    @app.post('/api/customers/access')
    def customer_access(request:Request,p:dict):
        from .customer_privacy import grant
        with db.transaction() as s:
            u=user(s,request);target=s.get(User,str(p.get('user_id','')))
            need(target is not None,'계정이 없습니다.',404);need(type(p.get('allowed')) is bool,'권한 값을 확인하세요.',422)
            grant(s,u,target,p['allowed']);return {'ok':True}
    @app.get('/api/users')
    def users(request:Request):
        with db.transaction() as s:
            from .customer_privacy import permissions
            admin(user(s,request));return [{'id':u.id,'username':u.username,'role':u.role,'active':u.active,**permissions(s,u)} for u in s.scalars(select(User))]
    @app.post('/api/import/preview')
    async def preview(request:Request,file:UploadFile=File(...),mapping:str=Form('{}')):
        data=await file.read(3_000_001)
        try:mp=json.loads(mapping);need(isinstance(mp,dict),'헤더 매핑 형식 오류')
        except ValueError:raise HTTPException(422,'매핑 JSON 오류')
        with db.transaction() as s:
            u=user(s,request);need(u.role in ['admin','worker'],'입고 권한이 없습니다.',403)
            try:job=GoogleSheetFileAdapter().preview(s,u,data,file.filename or '',mp)
            except (ValueError,UnicodeError,EOFError,zipfile.BadZipFile):raise HTTPException(422,'UTF-8 CSV/TSV 또는 XLSX 파일을 선택하세요.')
            return {'id':job.id,'rows':job.rows,'applied':job.applied}
    @app.get('/api/export')
    def export(request:Request):
        with db.transaction() as s:
            u=user(s,request);need(u.role!='ubis','내보내기 권한이 없습니다.',403)
            from .domain import layout,rows
            vehicles=[vehicle_dto(s,v,u) for v in rows(s,Vehicle)]
            data={'VEHICLES':[{k:v for k,v in x.items() if k not in ['smart_key','assignment','equipment','location']} for x in vehicles], 'CURRENT_STOCK':[{'vehicle_id':x['id'],'vin':x['vin'],'model':x['model'],'color':x['color'],'state':x['state'],'location':x['location'],'scheduled':x['assignment']['scheduled'] if x['assignment'] else ''} for x in vehicles if x['stay_id']]}
            # Relational exchange tabs; credentials and session/command tables are never exported.
            for name,cls in [('MASTERS',Master),('STOCK_STAYS',Stay),('ORDERS',Order),('ORDER_VEHICLES',Assignment),('ORDER_OPTIONS',OptionLine),('DELIVERY_ITEMS',DeliveryLine),('VEHICLE_EQUIPMENT',Equipment),('ZONES',Zone),('LOCATIONS',Slot),('LAYOUT_REVISIONS',LayoutRevision),('OUTBOUND',Outbound),('VEHICLE_HISTORY',History),('OUTBOUND_ADJUSTMENTS',Adjustment),('DAILY_CLOSINGS',Closing),('VEHICLE_STOCK_SNAPSHOTS',VehicleInventorySnapshot),('VEHICLE_STOCK_EVENTS',VehicleInventoryEvent),('VEHICLE_PRICES',VehicleValuation),('VEHICLE_STOCK_FACTS',VehicleInventoryFact),('PURCHASE_RECORDS',PurchaseRecord)]:
                data[name]=[{c.name:(iso(getattr(r,c.name)) if isinstance(getattr(r,c.name),datetime) else getattr(r,c.name)) for c in cls.__table__.columns} for r in rows(s,cls)]
            warehouse_layout=layout(s)
            data['WAREHOUSES']=warehouse_layout['warehouses']
            data['ZONE_WAREHOUSES']=[{'zone_id':z['id'],'warehouse_id':z['warehouse_id']} for z in warehouse_layout['zones']]
            data['MAP_OBJECTS']=warehouse_layout['objects']
            data['OUTBOUND_OPTIONS']=[{'outbound_id':o.id,**l} for o in rows(s,Outbound) for l in o.snapshot['options']]
            data['OUTBOUND_DELIVERY_ITEMS']=[{'outbound_id':o.id,**l} for o in rows(s,Outbound) for l in o.snapshot['items']]
            _,part_data=parts.load(s)
            data['PART_ITEMS']=part_data['items']
            data['PART_ENTRIES']=part_data['entries']
            data['PART_CLOSINGS']=part_data['closings']
            data['PART_AUDIT']=part_data['audit']
            data['EXPORT_MANIFEST']=[{'schema_version':1,'exported_at':iso(now()),'timezone':'Asia/Seoul','table':k,'row_count':len(v)} for k,v in data.items()]
            content=workbook(data)
        return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="warehouse_export.xlsx"'})
    @app.get('/api/parts')
    def parts_view(request:Request,day:str,month:str):
        with db.transaction() as s:return parts.view(s,user(s,request),day,month)
    @app.post('/api/parts/order-preview')
    def parts_order_preview(p:dict,request:Request):
        from .parts_orders import build
        with db.transaction() as s:
            u=user(s,request);need(u.role in ['admin','worker'],'권한이 없습니다.',403)
            _,data=parts.load(s)
            return build(data,p['model_id'],p.get('vehicle_kind','NEW'),p['plan'])
    @app.post('/api/parts/preview')
    def parts_preview(p:dict,request:Request):
        with db.transaction() as s:return parts.preview(s,user(s,request),p)
    @app.post('/api/parts/command')
    def parts_command(p:dict,request:Request):
        with db.transaction() as s:return parts.mutate(s,user(s,request),p)
    @app.get('/api/parts/export/{day}')
    def parts_export(day:str,request:Request):
        with db.transaction() as s:return parts.export(s,user(s,request),day)
    root=Path(__file__).resolve().parent.parent/'web'
    @app.get('/')
    def index():return FileResponse(root/'index.html')
    app.mount('/',StaticFiles(directory=root),name='web')
    return app
app=create_app()
