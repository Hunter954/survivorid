window.makeLineChart = function(id, labels, kd, damage, wr){
  const el = document.getElementById(id); if(!el) return;
  new Chart(el, {type:'line', data:{labels, datasets:[
    {label:'K/D', data:kd, borderColor:'#39a7ff', tension:.35, borderWidth:2, pointRadius:2},
    {label:'Damage', data:damage.map(v=>v/100), borderColor:'#ffbd28', tension:.35, borderWidth:2, pointRadius:2},
    {label:'Win Rate', data:wr, borderColor:'#6cff7d', tension:.35, borderWidth:2, pointRadius:2}
  ]}, options:{responsive:true, plugins:{legend:{labels:{color:'#cdd5e0'}}}, scales:{x:{ticks:{color:'#8994a8'}, grid:{color:'rgba(255,255,255,.05)'}}, y:{ticks:{color:'#8994a8'}, grid:{color:'rgba(255,255,255,.05)'}}}}});
}
window.makeRadarChart = function(id){
  const el = document.getElementById(id); if(!el) return;
  new Chart(el, {type:'radar', data:{labels:['Aim','Survival','Teamplay','Clutch','Aggression','Looting'], datasets:[{label:'Playstyle', data:[82,68,74,91,84,66], borderColor:'#39a7ff', backgroundColor:'rgba(57,167,255,.2)', pointBackgroundColor:'#ffbd28'}]}, options:{plugins:{legend:{display:false}}, scales:{r:{angleLines:{color:'rgba(255,255,255,.08)'}, grid:{color:'rgba(255,255,255,.08)'}, pointLabels:{color:'#cdd5e0'}, ticks:{display:false}}}}});
}
