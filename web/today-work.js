export function todayWorkVehicles(vehicles,today){
 return vehicles.filter(v=>v.stay_id&&v.assignment&&v.assignment.work!=='COMPLETED'&&!v.assignment.ready&&v.assignment.scheduled&&v.assignment.scheduled<=today)
 .sort((a,b)=>a.assignment.scheduled.localeCompare(b.assignment.scheduled)||String(a.assignment.number).localeCompare(String(b.assignment.number),undefined,{numeric:true}));
}
