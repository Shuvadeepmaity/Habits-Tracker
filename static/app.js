let charts={}; let currentRows=[]; let habitColumns=[];
const $=id=>document.getElementById(id);
function iso(d){return d.toISOString().slice(0,10)}
function initDates(){const today=new Date(); $("end").value=iso(today); const past=new Date(today); past.setDate(today.getDate()-30); $("start").value=iso(past); $("dailyDate").value=iso(today)}
async function api(url,opts){const r=await fetch(url,opts); if(!r.ok) throw new Error(await r.text()); return r.json()}
function destroy(id){if(charts[id]) charts[id].destroy()}
function chart(id,type,labels,data){
  destroy(id);
  const canvas=$(id);
  const gradientPlugin={
    id:'habitGradient',
    beforeDatasetsDraw(chart){
      const area=chart.chartArea;
      if(!area) return;
      const ctx=chart.ctx;
      const grad=ctx.createLinearGradient(0,area.bottom,0,area.top);
      grad.addColorStop(0,'rgba(255,48,48,.30)');
      grad.addColorStop(.45,'rgba(255,212,59,.45)');
      grad.addColorStop(1,'rgba(255,239,128,.85)');
      const lineGrad=ctx.createLinearGradient(area.left,0,area.right,0);
      lineGrad.addColorStop(0,'#ff3030');
      lineGrad.addColorStop(.5,'#ffd43b');
      lineGrad.addColorStop(1,'#fff09a');
      chart.data.datasets.forEach(ds=>{
        ds.backgroundColor=type==='line' ? grad : lineGrad;
        ds.borderColor=lineGrad;
        ds.pointBackgroundColor='#ffd43b';
        ds.pointBorderColor='#0b0b0b';
        ds.pointHoverBackgroundColor='#fff09a';
        ds.pointHoverBorderColor='#ff3030';
      });
    }
  };
  charts[id]=new Chart(canvas,{type,data:{labels,datasets:[{
    data,
    borderWidth:2.5,
    tension:.38,
    fill:type==='line',
    pointRadius:type==='line'?3:0,
    pointHoverRadius:type==='line'?6:0,
    borderRadius:type==='bar'?6:0
  }]},plugins:[gradientPlugin],options:{
    responsive:true,
    animation:{duration:900,easing:'easeOutQuart'},
    plugins:{legend:{display:false}},
    scales:{
      x:{ticks:{color:'#9b9b9b'},grid:{color:'rgba(255,212,59,.07)'}},
      y:{ticks:{color:'#9b9b9b'},grid:{color:'rgba(255,212,59,.07)'},beginAtZero:true,max:100}
    }
  }})
}
async function refresh(){
 const q=`?start=${$("start").value}&end=${$("end").value}`;
 const s=await api('/api/stats'+q);
 $("avg").textContent=s.avg.toFixed(1)+'%'; $("cardAvg").textContent=s.avg.toFixed(1)+'%'; $("days").textContent=s.days;
 document.querySelector('.ring').style.setProperty('--score',s.avg+'%');
 if(s.daily.scores.length){let i=s.daily.scores.indexOf(Math.max(...s.daily.scores));$("best").textContent=s.daily.labels[i];$("bestScore").textContent=s.daily.scores[i].toFixed(1)+'%';}
 const pairs=Object.entries(s.habit_avgs).sort((a,b)=>a[1]-b[1]);
 if(pairs.length){$("weak").textContent=pairs[0][0];$("weakScore").textContent=pairs[0][1].toFixed(1)+'%';}
 chart('dailyChart','line',s.daily.labels,s.daily.scores);
 chart('weeklyChart','line',s.weekly.labels,s.weekly.scores);
 chart('habitChart','bar',Object.keys(s.habit_avgs).map(x=>x.replace(/\(.*/,'')),Object.values(s.habit_avgs));
 await renderWeekly(s); await renderMonthly(s);
}
async function renderWeekly(s){
 chart('weeklyBig','line',s.weekly.labels,s.weekly.scores);
 const rows=s.weekly.labels.map((x,i)=>`<tr><td>${x}</td><td>${s.weekly.scores[i].toFixed(1)}%</td></tr>`).join('');
 $("weeklyTable").innerHTML='<table><thead><tr><th>WEEK START</th><th>AVG SCORE</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
async function renderMonthly(s){
 chart('monthlyChart','bar',s.monthly.labels,s.monthly.scores);
 const rows=s.monthly.labels.map((x,i)=>`<tr><td>${x}</td><td>${s.monthly.scores[i].toFixed(1)}%</td></tr>`).join('');
 $("monthlyTable").innerHTML='<table><thead><tr><th>MONTH</th><th>AVG SCORE</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
async function loadDailyForm(){
 const d=$("dailyDate").value; const data=await api('/api/daily?start='+d+'&end='+d); currentRows=data.rows; habitColumns=data.habit_columns;
 const row=currentRows[0]||{}; $("notes").value=row["Notes"]||"";
 $("habitForm").innerHTML=habitColumns.map((h,i)=>{const v=row[h]||'';return `<div class="habit"><label>${h}</label><div class="choices" data-value="${v}" data-h="${h}"><button class="${v==='✓'?'on y':''}" onclick="pick(this,'${esc(h)}','✓')">✓</button><button class="${v==='✗'?'on n':''}" onclick="pick(this,'${esc(h)}','✗')">✗</button></div></div>`}).join('');
 updateScore();
}
function esc(x){return x.replaceAll("'","\\'")}
function pick(btn,h,v){const box=btn.parentElement; box.querySelectorAll('button').forEach(b=>b.classList.remove('on','y','n'));btn.classList.add('on',v==='✓'?'y':'n');btn.parentElement.dataset.value=v;btn.parentElement.dataset.h=h;updateScore()}
function updateScore(){const all=[...document.querySelectorAll('.choices')]; const valid=all.filter(x=>x.dataset.value); const yes=valid.filter(x=>x.dataset.value==='✓').length; $("dailyScore").textContent=(all.length?yes/all.length*100:0).toFixed(1)+'%'}
async function saveDaily(){
 const values={};document.querySelectorAll('.choices').forEach(x=>{if(x.dataset.value)values[x.dataset.h]=x.dataset.value});
 const r=await api('/api/daily',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:$("dailyDate").value,values,notes:$("notes").value})});
 $("dailyScore").textContent=r.score.toFixed(1)+'%'; await refresh(); alert('Saved successfully. Your progress is stored for future days.');
}
function openClear(){$("clearModal").classList.add('show')}function closeClear(){$("clearModal").classList.remove('show')}
async function clearRange(){await api('/api/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start:$("start").value,end:$("end").value,scope:'daily'})});closeClear();await refresh();await loadDailyForm();alert('Range cleared. A backup workbook was created.')}
async function sendChat(){const input=$("chatinput");const msg=input.value.trim();if(!msg)return; $("chatlog").innerHTML+=`<div class="bubble me">${msg}</div>`;input.value='';const r=await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});$("chatlog").innerHTML+=`<div class="bubble bot">${r.answer}</div>`;$("chatlog").scrollTop=$("chatlog").scrollHeight}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));$(b.dataset.page).classList.add('active');if(b.dataset.page==='daily')loadDailyForm();});
$("chatinput").addEventListener('keydown',e=>{if(e.key==='Enter')sendChat()});
initDates();refresh();loadDailyForm();
