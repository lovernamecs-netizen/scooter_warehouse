export function safeMessage(value,status=0){
 const fallback=status===401?'로그인이 필요하거나 만료되었습니다. 다시 로그인하세요.':status===403?'이 작업을 수행할 권한이 없습니다. 관리자에게 요청해주세요.':status===429?'요청이 많습니다. 잠시 후 다시 시도해주세요.':status>=500?'서버가 요청을 처리하지 못했습니다. 잠시 후 처리 여부를 확인해주세요.':'입력 내용을 확인해주세요.';
 if(Array.isArray(value))return '입력값이 누락되었거나 형식이 올바르지 않습니다. 입력 내용을 확인해주세요.';
 if(value&&typeof value==='object')return safeMessage(value.message,status);
 if(typeof value!=='string'||!value.trim()||value.length>1000||/[<>]|Traceback|SELECT |INSERT |OperationalError|TypeError|\\|[A-Z]:\//i.test(value))return fallback;
 return /[가-힣]/.test(value)?value:fallback;
}
let popup=null,pendingBack=false,returnFocus=null;
window.addEventListener('popstate',event=>{if(popup?.open||pendingBack){event.stopImmediatePropagation();pendingBack=false;if(popup?.open)popup.close();}},true);
export function showError(error){
 if(!popup){popup=document.createElement('dialog');popup.className='system-error';popup.innerHTML='<h2>작업을 확인해주세요</h2><p data-error-message></p><p data-error-next>입력 내용은 유지됩니다. 내용을 확인한 뒤 다시 진행해주세요.</p><small data-error-id></small><footer><button type="button">확인</button></footer>';document.body.append(popup);
 const close=()=>{popup.close();if(history.state?.warehouseError){pendingBack=true;history.back();}};
 popup.querySelector('button').onclick=close;popup.addEventListener('cancel',e=>{e.preventDefault();close();});popup.addEventListener('close',()=>returnFocus?.isConnected&&returnFocus.focus());}
 popup.querySelector('[data-error-message]').textContent=safeMessage(error?.message,error?.status);
 popup.querySelector('[data-error-next]').textContent=error?.uncertain?'입력 내용은 유지됩니다. 새 요청을 만들기 전에 같은 요청의 처리 결과를 확인해주세요.':'입력 내용은 유지됩니다. 내용을 확인한 뒤 다시 진행해주세요.';
 popup.querySelector('[data-error-id]').textContent=error?.requestId?'오류 번호: '+error.requestId:'';
 if(!popup.open){returnFocus=document.activeElement;history.pushState({...history.state,warehouseError:true},'');popup.showModal();popup.querySelector('button').focus();}
 for(const old of document.querySelectorAll('.field-error'))old.remove();
 for(const [name,message] of Object.entries(error?.fieldErrors||{})){const input=document.querySelector(`[name="${CSS.escape(name)}"]`);if(input){const note=document.createElement('small');note.className='field-error';note.textContent=safeMessage(message);input.after(note);}}
}
