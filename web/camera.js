// Shared rear-camera surface for VIN, inspection, damage and product photos.
export const cameraIcon='<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 6h4l2-3h6l2 3h4v15H3z"/><circle cx="12" cy="13" r="4"/></svg>';
export async function captureStill(track,video){
 if(typeof ImageCapture==='function'){
  try{
   const camera=new ImageCapture(track);let settings={};
   try{const caps=await camera.getPhotoCapabilities();for(const key of ['imageWidth','imageHeight'])if(caps[key]?.max>0)settings[key]=caps[key].max;}catch{}
   try{const blob=await camera.takePhoto(settings);if(blob?.size)return blob;}catch{}
   try{const blob=await camera.takePhoto();if(blob?.size)return blob;}catch{}
  }catch{}
 }
 // Older WebViews: preserve the actual video frame dimensions, never CSS dimensions.
 if(!video.videoWidth||!video.videoHeight)throw Error('카메라 화면이 준비되지 않았습니다. 다시 촬영하세요.');
 const c=document.createElement('canvas');c.width=video.videoWidth;c.height=video.videoHeight;c.getContext('2d').drawImage(video,0,0);
 return await new Promise((resolve,reject)=>c.toBlob(b=>b?resolve(b):reject(Error('사진을 저장하지 못했습니다. 다시 촬영하세요.')),'image/jpeg',.96));
}
// Android uses the system camera rather than a constrained getUserMedia preview.
async function systemCameraPhoto(){
 return await new Promise(resolve=>{
  const input=document.createElement('input');input.type='file';input.accept='image/*';input.setAttribute('capture','environment');input.hidden=true;document.body.append(input);
  let done=false;const finish=file=>{if(done)return;done=true;input.remove();resolve(file);};
  input.onchange=()=>finish(input.files?.[0]||null);input.addEventListener('cancel',()=>finish(null));input.click();
 });
}
export async function capturePhoto(){
 if(/Android/i.test(navigator.userAgent))return await systemCameraPhoto();
 const dialog=document.createElement('dialog');dialog.className='capture-dialog';dialog.innerHTML=`<header><strong>사진 촬영</strong><button type="button" data-camera="cancel" aria-label="닫기">✕</button></header><div class="capture-view"><video autoplay playsinline muted></video><span class="capture-resolution"></span><p role="status">카메라 연결 중…</p></div><footer><button type="button" data-camera="cancel">취소</button><button type="button" class="capture-shutter" data-camera="shoot" aria-label="사진 촬영" disabled>${cameraIcon}</button><button type="button" data-camera="file">파일</button></footer><input type="file" accept="image/jpeg,image/png,image/webp" hidden>`;
 document.body.append(dialog);dialog.showModal();let stream=null,done=false,busy=false;
 return await new Promise(resolve=>{
  function finish(value){if(done)return;done=true;stream?.getTracks().forEach(t=>t.stop());dialog.close();dialog.remove();resolve(value)}
  dialog.addEventListener('cancel',e=>{e.preventDefault();finish(null)});
  const video=dialog.querySelector('video'),status=dialog.querySelector('[role=status]'),input=dialog.querySelector('input'),shutter=dialog.querySelector('[data-camera=shoot]');
  input.onchange=()=>finish(input.files[0]||null);
  dialog.onclick=async e=>{const act=e.target.closest('[data-camera]')?.dataset.camera;if(act==='cancel')finish(null);if(act==='file'&&!busy)input.click();if(act==='shoot'&&!busy&&stream){
   busy=true;shutter.disabled=true;status.hidden=false;status.textContent='촬영 중…';
   try{const blob=await captureStill(stream.getVideoTracks()[0],video);if(!done){const ext=blob.type==='image/png'?'png':blob.type==='image/webp'?'webp':'jpg';finish(new File([blob],'camera.'+ext,{type:blob.type||'image/jpeg'}));}}
   catch(error){if(!done){status.hidden=false;status.textContent=error.message;}}
   finally{busy=false;if(!done)shutter.disabled=false;}
  }};
  if(!navigator.mediaDevices?.getUserMedia){status.textContent='카메라는 HTTPS 연결이 필요합니다. 파일을 선택할 수 있습니다.';return}
  (async()=>{try{
   const s=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:4096},height:{ideal:3072}},audio:false});
   if(done){s.getTracks().forEach(t=>t.stop());return}stream=s;const track=s.getVideoTracks()[0];
   try{const caps=track.getCapabilities?.()||{};const constraints={};for(const key of ['width','height'])if(caps[key]?.max>0)constraints[key]={ideal:caps[key].max};if(Object.keys(constraints).length)await track.applyConstraints(constraints);}catch{}
   if(done)return;
   const ready=()=>{if(done||!video.videoWidth)return;status.hidden=true;shutter.disabled=false;dialog.querySelector('.capture-resolution').textContent='미리보기 '+video.videoWidth+' × '+video.videoHeight;};
   video.onloadedmetadata=ready;video.onresize=ready;video.srcObject=s;await video.play();ready();
  }catch{if(!done){stream?.getTracks().forEach(t=>t.stop());status.hidden=false;status.textContent='카메라 권한을 확인하세요. 파일 선택도 가능합니다.';}}})();
 });
}
export function fileBase64(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onerror=()=>reject(Error('사진을 읽을 수 없습니다.'));r.onload=()=>resolve(String(r.result).split(',')[1]);r.readAsDataURL(file)})}
export async function previewBase64(file,maxEdge=1100,quality=.8){const url=URL.createObjectURL(file);try{const img=new Image();img.src=url;await img.decode();const scale=Math.min(1,maxEdge/Math.max(img.naturalWidth,img.naturalHeight)),c=document.createElement('canvas');c.width=Math.max(1,Math.round(img.naturalWidth*scale));c.height=Math.max(1,Math.round(img.naturalHeight*scale));const x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,c.width,c.height);x.drawImage(img,0,0,c.width,c.height);return c.toDataURL('image/jpeg',quality).split(',')[1]}finally{URL.revokeObjectURL(url)}}

export async function recognizeVin(api,image){
 if(window.WarehouseNative?.recognizeImage)return await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{window.onWarehouseOCR=null;reject(Error('VIN 분석 시간이 초과되었습니다.'))},45000);window.onWarehouseOCR=result=>{clearTimeout(timer);window.onWarehouseOCR=null;result.error?reject(Error(result.error)):resolve(result)};window.WarehouseNative.recognizeImage(image)});
 return await api('/vin/ocr',{method:'POST',body:JSON.stringify({image})});
}

export const ocrBase64=file=>previewBase64(file,4096,.94);
