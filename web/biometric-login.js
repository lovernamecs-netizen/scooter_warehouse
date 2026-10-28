let pending=null;
export function biometricStatus(){try{return JSON.parse(window.WarehouseNative?.biometricStatus?.()||'{}');}catch{return {};}}
function request(method,...args){
 if(pending)return Promise.reject(Error('생체인증이 진행 중입니다.'));
 return new Promise((resolve,reject)=>{
  const id=crypto.randomUUID();
  const timer=setTimeout(()=>{if(pending?.id===id){pending=null;window.WarehouseNative?.biometricCancel?.();reject(Error('인증 시간이 초과되었습니다. 다시 시도하세요.'));}},90000);
  pending={id,resolve,reject,timer};
  try{window.WarehouseNative[method](id,...args);}catch{clearTimeout(timer);pending=null;reject(Error('새 APK에서 생체 로그인을 사용할 수 있습니다.'));}
 });
}
window.onWarehouseBiometric=(id,data)=>{
 if(!pending||pending.id!==id)return;
 const task=pending;pending=null;clearTimeout(task.timer);
 if(data.error)task.reject(Error(data.error));else task.resolve(data);
};
export function biometricFields(){const s=biometricStatus();return (s.available?'<label class="check"><input type="checkbox" id="enable-biometric">이 기기에서 생체 로그인 사용</label>':'')+(s.ready?'<div class="actions"><button type="button" id="biometric-login">지문으로 로그인</button><button type="button" id="biometric-clear">생체 로그인 해제</button></div>':'');}
export async function enrollBiometric(username,password,enabled){
 if(!window.WarehouseNative?.biometricClear)return;
 window.WarehouseNative.biometricClear();
 if(enabled)await request('biometricEnroll',username,password);
}
export function bindBiometricLogin(accept,repaint){
 const login=document.querySelector('#biometric-login');
 if(login)login.onclick=async()=>{
  login.disabled=true;const submit=document.querySelector('#login [type=submit]');submit.disabled=true;const error=document.querySelector('#login-error');error.textContent='';
  try{const r=await request('biometricLogin');if(!r.token)throw Error('로그인에 실패했습니다.');await accept(r.token);}
  catch(e){if(error.isConnected)error.textContent=e.message;}
  finally{login.disabled=false;submit.disabled=false;}
 };
 const clear=document.querySelector('#biometric-clear');if(clear)clear.onclick=()=>{window.WarehouseNative.biometricClear();clear.disabled=true;if(login)login.hidden=true;setTimeout(repaint,100);};
}
