import {koreanHoliday,holidayYearSupported} from './korean-holidays.js';
// Presentation only: no API access, business records, prices or shared selection state.
export function monthCalendar({month,selected='',today='',previous='',next='',controls='',cell,label='월간 달력'}){
 if(!/^\d{4}-\d{2}$/.test(month))throw Error('조회 월을 확인하세요.');
 const [year,m]=month.split('-').map(Number);if(m<1||m>12)throw Error('조회 월을 확인하세요.');
 const first=new Date(Date.UTC(year,m-1,1)),count=new Date(Date.UTC(year,m,0)).getUTCDate();
 const days=Array.from({length:count},(_,i)=>{const day=month+'-'+String(i+1).padStart(2,'0'),weekday=(first.getUTCDay()+i)%7,h=koreanHoliday(day);let content=cell(day,i+1);if(h.name)content=content.replace('</strong>','</strong><small class="calendar-holiday"'+(h.holiday?'':' style="color:inherit"')+'>'+h.name+'</small>');return `<div data-calendar-day="${day}" class="month-calendar-day ${weekday===0?'is-sunday':weekday===6?'is-saturday':''} ${h.holiday?'is-holiday':''} ${day===selected?'is-selected':''} ${day===today?'is-today':''}">${content}</div>`;}).join('');
 return `<div class="month-calendar" aria-label="${label}"><div class="month-calendar-toolbar">${previous}<strong>${month}</strong>${next}<div class="month-calendar-controls">${controls}</div></div><div class="month-calendar-week">${['일','월','화','수','목','금','토'].map(x=>`<span>${x}</span>`).join('')}</div><div class="month-calendar-grid">${'<span class="month-calendar-blank" aria-hidden="true"></span>'.repeat(first.getUTCDay())}${days}</div>${holidayYearSupported(year)?'':'<small class="calendar-coverage">이 연도는 국경일 명칭만 표시합니다. 공휴일 자료는 2024–2027년 제공됩니다.</small>'}</div>`;
}
export function shiftMonth(month,delta){const [y,m]=month.split('-').map(Number),d=new Date(Date.UTC(y,m-1+delta,1));return d.toISOString().slice(0,7);}
