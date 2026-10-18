// Account-scoped recovery across tab closure. Never replay automatically.
export function pendingRequest(userId){
 const key='warehousePending.v2:'+userId;
 return {
  read(){const raw=localStorage.getItem(key);if(!raw)return null;try{const value=JSON.parse(raw);if(typeof value.command_id!=='string'||typeof value.action!=='string'||!value.payload)throw Error();return value;}catch{throw Error('보관된 미확정 요청을 읽지 못했습니다. 브라우저 데이터를 지우지 말고 관리자에게 문의하세요.');}},
  write(body){try{localStorage.setItem(key,JSON.stringify(body));}catch{throw Error('이 기기에 재시도 정보를 보관할 공간이 없습니다. 저장 요청을 보내지 않았습니다. 저장 공간을 확인하세요.');}},
  clear(){localStorage.removeItem(key);}
 };
}
