import {isPhotoBack} from './photo-viewer.js';
// Shared protection for X, Escape, browser Back and refresh.
export function installFormSafety(dialog, notify) {
  let baseline='', busy=false, parent=null,probe=()=>false;
  const controls=()=>[...dialog.querySelectorAll('input,select,textarea')];
  const values=()=>controls().map(e=>({value:e.value,checked:e.checked}));
  const fingerprint=()=>JSON.stringify(values());
  const dirty=()=>dialog.open && (fingerprint()!==baseline||probe());
  const mark=()=>{baseline=fingerprint();};
  const arm=()=>{if(!history.state?.warehouseDialog)history.pushState({...history.state,warehouseDialog:true},'');};
  function restore(snapshot) {
    dialog.innerHTML=snapshot.html;
    controls().forEach((e,i)=>{e.value=snapshot.values[i].value;if('checked' in e)e.checked=snapshot.values[i].checked;});
    baseline=snapshot.baseline;
    dialog.dispatchEvent(new CustomEvent('form-restored'));
  }
  function close() {
    if(busy){notify('저장 처리 중입니다. 결과가 표시될 때까지 기다려 주세요.');return false;}
    if(parent){dialog.dispatchEvent(new Event('form-cancelled'));const saved=parent;parent=null;restore(saved);arm();return false;}
    if(dirty()&&!confirm('작성 중인 내용을 저장하지 않고 닫을까요?'))return false;
    dialog.dispatchEvent(new Event('form-cancelled'));dialog.close();return true;
  }
  dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
  dialog.addEventListener('close',()=>{if(!dialog.open){parent=null;if(history.state?.warehouseDialog)history.back();}});
  window.addEventListener('popstate',()=>{if(isPhotoBack())return;if(dialog.open){if(!close())arm();}});
  window.addEventListener('beforeunload',e=>{if(dirty()||busy||parent){e.preventDefault();e.returnValue='';}});
  return {close,dirty,mark,setDirtyProbe(fn){probe=fn;},setBusy(value){busy=value;},opened(){mark();arm();},
    capture(){const clone=dialog.cloneNode(true);clone.querySelectorAll('[data-act=scan-receipt],[data-act=scan-dispatch]').forEach(e=>e.disabled=false);parent={html:clone.innerHTML,values:values(),baseline};},
    hasParent(){return !!parent;},clearParent(){parent=null;},
    restoreVin(value,target){if(!parent)return false;const saved=parent;parent=null;restore(saved);const field=dialog.querySelector(target);if(field)field.value=value;return true;}
  };
}
