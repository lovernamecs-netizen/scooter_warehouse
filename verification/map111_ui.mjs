import {createRequire} from 'node:module';
import {mkdtempSync,rmSync} from 'node:fs';
import {execFileSync,spawn} from 'node:child_process';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dir=mkdtempSync(tmpdir()+'/warehouse-108-'),cwd=resolve('scooter_warehouse'),env={...process.env,DATABASE_URL:'sqlite:///'+dir+'/test.db',WAREHOUSE_ADMIN_PASSWORD:'LocalTestOnly-1234'};
for(const arg of ['init','demo'])execFileSync('python3',['-m','server.cli',arg],{cwd,env});
const server=spawn('python3',['-m','uvicorn','server.app:app','--port','8893'],{cwd,env,stdio:'ignore'});let browser;
try{
 for(let i=0;i<100;i++){try{if((await fetch('http://127.0.0.1:8893/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox']});
 const p=await browser.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(6000);const errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
 const login=async p=>{await p.goto('http://127.0.0.1:8893');await p.locator('[name=username]').fill('admin');await p.locator('[name=password]').fill('LocalTestOnly-1234');await p.locator('#login button').click();await p.locator('#global-search').waitFor();};
 await login(p);
 const cmd=(action,payload)=>p.evaluate(async({action,payload})=>{const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+sessionStorage.warehouseToken},body:JSON.stringify({command_id:crypto.randomUUID(),action,payload})});if(!r.ok)throw Error(await r.text());return r.json()},{action,payload});
 const state=()=>p.evaluate(async()=>await (await fetch('/api/state',{headers:{Authorization:'Bearer '+sessionStorage.warehouseToken}})).json());
 await cmd('zone',{name:'DRAG VIEW TEST',rows:1,cols:1,x:900,y:400,kind:'STORAGE'});
 let st=await state();const zone=st.layout.zones.find(z=>z.name==='DRAG VIEW TEST');
 const other=await cmd('warehouse',{revision:st.revision,name:'OTHER',width:2000,height:1000});st=await state();await cmd('map_objects',{revision:st.revision,objects:[{warehouse_id:'main',label:'VIEW OBJECT',kind:'MATERIAL',x:1500,y:800,width:80,height:70}]});
 await p.locator('[data-act=refresh]').click();await p.locator('.sidebar [data-page=map]').click();await p.locator('[data-act=edit-map]').click();
 const selector=`.zone[data-zone-id="${zone.id}"]`;
 await p.evaluate(()=>{const e=document.querySelector('.map-viewport');e.scrollLeft=280;e.scrollTop=120;window.scrollTo(0,100)});
 const view=()=>p.evaluate(()=>{const e=document.querySelector('.map-viewport');return {x:e.scrollLeft,y:e.scrollTop,zoom:e.dataset.mapZoom,windowY:window.scrollY}});
 const original=await view();assert.ok(original.x>0&&original.y>0);
 const drag=async(sel,dx,dy)=>{await p.evaluate(()=>window.previousMap=document.querySelector('.map-viewport'));const b=await p.locator(sel).boundingBox();await p.mouse.move(b.x+10,b.y+12);await p.mouse.down();await p.mouse.move(b.x+10+dx,b.y+12+dy,{steps:10});await p.mouse.up();await p.waitForFunction(()=>document.querySelector('.map-viewport')!==window.previousMap);};
 await drag(selector+' .zone-title',32,16);assert.deepEqual(await view(),original);st=await state();let moved=st.layout.zones.find(z=>z.id===zone.id);assert.equal(moved.x,940);assert.equal(moved.y,420);
 await drag(selector+' .zone-title',1000,0);assert.deepEqual(await view(),original);st=await state();assert.equal(st.layout.zones.find(z=>z.id===zone.id).x,940);
 await drag('.map-object',16,16);assert.deepEqual(await view(),original);st=await state();assert.equal(st.layout.objects[0].x,1520);
 await p.locator('#warehouse-select').selectOption(other.id);assert.equal((await view()).x,0);await p.locator('#warehouse-select').selectOption('main');assert.equal((await view()).x,original.x);assert.equal((await view()).y,original.y);
 await p.locator('[data-act=edit-map]').click();assert.equal((await view()).x,original.x);await p.locator('[data-act=zoom][data-delta="0.1"]').click();const scaled=await view();assert.ok(Math.abs(scaled.x-original.x*Number(scaled.zoom)/Number(original.zoom))<=1);assert.ok(Math.abs(scaled.y-original.y*Number(scaled.zoom)/Number(original.zoom))<=1);
 assert.deepEqual(errors,[]);console.log('PASS: real pointer drag success/rejection/object drag retain both scroll axes, zoom and page scroll; per-warehouse restoration; edit toggle and zoom preserve map position; no JS errors');
}finally{if(browser)await browser.close();server.kill();rmSync(dir,{recursive:true,force:true});}
