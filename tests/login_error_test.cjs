// Regression: login credential failures must not be labelled expired sessions.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const api=source.slice(source.indexOf('async function api('),source.indexOf('\nasync function refresh('));
let response;
const ctx=vm.createContext({AbortController,FormData,setTimeout,clearTimeout,fetch:async()=>response,sessionStorage:{removeItem(){}},describe:x=>typeof x==='string'?x:JSON.stringify(x)});
const errorSource=readFileSync(require('node:path').join(__dirname,'../web/errors.js'),'utf8');
const safe=errorSource.slice(0,errorSource.indexOf('let popup=')).replace('export function','function');
vm.runInContext("let token='old',online=true;"+safe+api,ctx);
(async()=>{
 response={status:401,ok:false,json:async()=>({detail:'아이디 또는 비밀번호를 확인하세요.'})};
 await assert.rejects(vm.runInContext("api('/login')",ctx),/아이디 또는 비밀번호를 확인하세요/);
 await assert.rejects(vm.runInContext("api('/state')",ctx),/로그인이 만료되었습니다/);
 assert.equal(vm.runInContext('token',ctx),'');
 response={status:200,ok:true,json:async()=>({token:'valid'})};
 assert.equal((await vm.runInContext("api('/login')",ctx)).token,'valid');
 response={status:429,ok:false,json:async()=>({detail:'잠시 후 다시 시도하세요.'})};
 await assert.rejects(vm.runInContext("api('/login')",ctx),/잠시 후 다시 시도하세요/);
 console.log('PASS: invalid credentials, expired session, successful login, throttling');
})().catch(e=>{console.error(e);process.exitCode=1});
