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
 let st=await state();const model=st.masters.find(m=>m.kind==='model'),color=st.masters.find(m=>m.kind==='color');
 await p.locator('[data-act=receipt]').first().click();assert.equal(await p.locator('[name=ubis_installed]').isChecked(),true);
 await p.locator('#model_id').selectOption(model.id);await p.locator('#color_id').selectOption(color.id);await p.locator('#vin').fill('L1234567890123456');
 await p.locator('[data-act=save-receipt]').click();await p.locator('[data-act=ubis-set]').waitFor();st=await state();const v=st.vehicles.find(v=>v.vin==='L1234567890123456');assert.equal(v.ubis,'INSTALLED');await p.locator('[data-act=close]').click();
 await p.locator('[data-act=receipt]').first().click();await p.locator('[name=ubis_installed]').uncheck();await p.locator('[data-act=save-draft]').click();await p.locator('[data-act=close]').click();await p.locator('[data-act=receipt]').first().click();assert.equal(await p.locator('[name=ubis_installed]').isChecked(),false);
 await p.locator('#model_id').selectOption(model.id);await p.locator('#color_id').selectOption(color.id);await p.locator('#vin').fill('L1234567890123457');await p.locator('[data-act=save-receipt]').click();await p.locator('[data-act=ubis-set]').waitFor();assert.equal((await state()).vehicles.find(v=>v.vin==='L1234567890123457').ubis,'NOT_INSTALLED');await p.locator('[data-act=close]').click();
 st=await state();const wh=(await cmd('warehouse',{revision:st.revision,name:'HEADER TEST',width:2400,height:1400})).id;
 for(const [name,cols,x] of [['PCX',1,20],['아주 긴 구역 이름으로 두 줄 이상이 되는 창고 영역입니다',2,220],['NMAX',4,560]])await cmd('zone',{name,warehouse_id:wh,rows:2,cols,x,y:20,kind:'STORAGE'});
 st=await state();const zone=st.layout.zones.find(z=>z.warehouse_id===wh&&z.name==='PCX');await cmd('move',{vehicle_id:v.id,version:st.vehicles.find(x=>x.id===v.id).version,slot_id:zone.slots[0].id});
 await p.locator('[data-act=refresh]').click();await p.locator('.sidebar [data-page=map]').click();await p.locator('#warehouse-select').selectOption(wh);
 const checkHeaders=async()=>{const sizes=await p.locator('.zone').evaluateAll(els=>els.map(el=>{const r=el.getBoundingClientRect(),head=el.querySelector('.zone-title').getBoundingClientRect(),meta=el.querySelector('.zone-caption small').getBoundingClientRect(),slot=el.querySelector('.slots').getBoundingClientRect();return {h:head.height,meta:meta.top-r.top,slot:slot.top-r.top}}));for(const s of sizes)for(const k of ['h','meta','slot'])assert.ok(Math.abs(s[k]-sizes[0][k])<.1,JSON.stringify(sizes));};await checkHeaders();
 const ubis=()=>p.locator(`.map-ubis[data-id="${v.id}"]`);assert.equal(await ubis().innerText(),'U');
 await ubis().click();await p.locator('[data-act=map-ubis-save][data-status=NOT_INSTALLED]').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);assert.equal((await state()).vehicles.find(x=>x.id===v.id).ubis,'NOT_INSTALLED');assert.equal(await ubis().innerText(),'U−');
 await ubis().click();await p.locator('[data-act=map-ubis-save][data-status=INSTALLED]').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);assert.equal((await state()).vehicles.find(x=>x.id===v.id).ubis,'INSTALLED');
 // A newer command must prevent a stale popup from overwriting the state.
 await ubis().click();st=await state();await cmd('ubis',{vehicle_id:v.id,version:st.vehicles.find(x=>x.id===v.id).version,status:'UNKNOWN'});await p.locator('[data-act=map-ubis-save][data-status=NOT_INSTALLED]').click();await p.locator('.modal-error').waitFor({state:'visible'});assert.equal((await state()).vehicles.find(x=>x.id===v.id).ubis,'UNKNOWN');await p.locator('[data-act=close]').click();await p.locator('[data-act=refresh]').click();
 await p.locator('[data-act=edit-map]').click();await checkHeaders();await p.locator('[data-act=edit-map]').click();await checkHeaders();
 await p.screenshot({path:'/tmp/warehouse113-desktop.png',fullPage:true});await p.setViewportSize({width:344,height:800});await checkHeaders();await ubis().click();await p.locator('[data-act=map-ubis-save][data-status=INSTALLED]').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);
 const metrics=await p.locator(`.slot[data-vehicle="${v.id}"]`).evaluate(el=>({h:el.clientHeight,scroll:el.scrollHeight}));assert.ok(metrics.scroll<=metrics.h,JSON.stringify(metrics));
 const history=await p.evaluate(async id=>(await fetch('/api/history/'+id,{headers:{Authorization:'Bearer '+sessionStorage.warehouseToken}})).json(),v.id);assert.ok(history.filter(h=>h.event.startsWith('UBIS_')).length>=4);
 await p.screenshot({path:'/tmp/warehouse113-mobile.png',fullPage:true});assert.deepEqual(errors,[]);console.log('PASS new receipt default, explicit unchecked + saved draft preservation, U status update and audit, stale popup rejection, identical header baselines (1/2/4 cols, long names, edit/view/mobile), mobile card fit; no JS errors');
}finally{if(browser)await browser.close();server.kill();rmSync(dir,{recursive:true,force:true});}
