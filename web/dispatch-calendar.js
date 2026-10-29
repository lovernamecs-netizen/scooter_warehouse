import {monthCalendar,shiftMonth} from './month-calendar.js';
let activeMonth='',sequence=0;
export async function renderDispatchCalendar(target,H,day){
 const ticket=++sequence,month=day?.slice(0,7)||activeMonth||H.today.slice(0,7);activeMonth=month;
 const e=H.esc,b=(text,action,extra='')=>`<button type="button" data-dispatch="${action}" ${extra}>${text}</button>`;
 target.innerHTML='<h1>출고 일정·이력</h1><p role="status">불러오는 중…</p>';
 const rows=await H.api('/outbound?month='+month);
 if(ticket!==sequence||!target.isConnected||!H.isCurrent())return;
 H.setHistory(rows);
 const voided=o=>o.adjustments.some(a=>a.kind==='VOID');
 const actual=rows.filter(o=>!voided(o));
 const planned=H.vehicles.filter(v=>v.stay_id&&v.assignment?.scheduled?.startsWith(month+'-'));
 const shownPlanned=planned.filter(v=>!day||v.assignment.scheduled===day);
 const counts=new Map();for(const o of actual)counts.set(o.day,(counts.get(o.day)||0)+1);
 const pending=new Map();for(const v of planned)pending.set(v.assignment.scheduled,(pending.get(v.assignment.scheduled)||0)+1);
 target.innerHTML=`<h1>출고 일정·이력</h1><div class="dispatch-month-totals"><span>월 실제 출고 <strong>${actual.length}대</strong></span><span>남은 출고예정 <strong>${planned.length}대</strong></span>${rows.length!==actual.length?`<span>출고취소 ${rows.length-actual.length}건</span>`:''}</div><section class="panel">${monthCalendar({month,selected:day,today:H.today,label:'출고 일정·이력 달력',previous:b('‹','month','data-delta="-1" aria-label="이전 달"'),next:b('›','month','data-delta="1" aria-label="다음 달"'),controls:`<input type="month" data-dispatch-month value="${month}" aria-label="출고 조회 월">${b('오늘','today')}${b('월 전체','all')}`,cell:(date,n)=>b(`<strong>${n}</strong><small class="calendar-actual">출고 ${counts.get(date)||0}대</small><small>예정 ${pending.get(date)||0}대</small>`,'day',`data-day="${date}" aria-label="${date} 실제 출고 ${counts.get(date)||0}대 예정 ${pending.get(date)||0}대"`)})}</section><section class="panel"><h2>${e(day||month+' 전체')} · 남은 출고예정 ${shownPlanned.length}대</h2>${H.vehicleTable(shownPlanned)}</section><h2>${e(day||month+' 전체')} · 출고확정 이력</h2>${H.historyHTML(rows)}`;
 target.querySelectorAll('[data-dispatch]').forEach(el=>el.onclick=()=>{
  if(el.dataset.dispatch==='month'){activeMonth=shiftMonth(month,Number(el.dataset.delta));H.select(activeMonth+'-01');}
  if(el.dataset.dispatch==='day')H.select(el.dataset.day);
  if(el.dataset.dispatch==='today')H.select(H.today);
  if(el.dataset.dispatch==='all')H.select('');
 });
 target.querySelector('[data-dispatch-month]').onchange=ev=>{if(/^\d{4}-\d{2}$/.test(ev.target.value))H.select(ev.target.value+'-01');};
}
