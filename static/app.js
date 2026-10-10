(function(){
"use strict";
/* ================= theme ================= */
const root=document.documentElement, tBtn=document.getElementById("themeBtn"), tLbl=document.getElementById("themeLbl");
const mq=window.matchMedia?window.matchMedia("(prefers-color-scheme: dark)"):null;
const curTheme=()=>root.getAttribute("data-theme")||(mq&&mq.matches?"dark":"light");
function paintTheme(){const t=curTheme(); root.setAttribute("data-theme",t); tLbl.textContent=t==="dark"?"Dark":"Light"; tBtn.setAttribute("aria-label",t==="dark"?"Switch to light mode":"Switch to dark mode");}
tBtn.addEventListener("click",()=>{const n=curTheme()==="dark"?"light":"dark"; root.setAttribute("data-theme",n); try{localStorage.setItem("ideabank:theme",n);}catch(e){} paintTheme();});
paintTheme();

/* ================= api ================= */
async function api(path,opts){
  const o=Object.assign({headers:{"Content-Type":"application/json"}},opts||{});
  if(o.body&&typeof o.body!=="string") o.body=JSON.stringify(o.body);
  const r=await fetch(path,o); let d={}; try{d=await r.json();}catch(e){}
  if(!r.ok) throw new Error(d.error||("Request failed ("+r.status+")"));
  return d;
}
const store={get(k,d){try{const v=localStorage.getItem("ideabank:"+k);return v?JSON.parse(v):d;}catch(e){return d;}},set(k,v){try{localStorage.setItem("ideabank:"+k,JSON.stringify(v));}catch(e){}},del(k){try{localStorage.removeItem("ideabank:"+k);}catch(e){}}};

/* ================= constants ================= */
const FIELDS={cs:{label:"Computer science",short:"CS",cls:"c-blue"},mech:{label:"Mechanical",short:"ME",cls:"c-amber"},elec:{label:"Electrical",short:"EE",cls:"c-lav"},civil:{label:"Civil",short:"CE",cls:"c-green"},biz:{label:"Business",short:"BZ",cls:"c-pink"},other:{label:"Other",short:"OT",cls:"c-gray"}};
const LENSES=[{k:"need",label:"Need",max:25},{k:"revenue",label:"Revenue",max:25},{k:"seed",label:"Seed-ready",max:20},{k:"entre",label:"Entrepreneurial",max:15},{k:"impact",label:"Impact",max:15}];
const CHECKS=[{k:"demand",q:"Do people really need this?"},{k:"today",q:"What do they do today?"},{k:"who",q:"Who needs it most?"},{k:"wedge",q:"Smallest version to sell first"},{k:"seen",q:"Have we seen the struggle?"},{k:"future",q:"Will it matter more later?"}];
const PRODUCT={app:"App",device:"Device",service:"Service",mix:"Mix"};
const BUDGET={low:"Under ₹50,000",mid:"₹50,000 – ₹5 lakh",high:"Above ₹5 lakh"};
const SETTING={city:"Big city",town:"Small town",rural:"Rural area",any:"Anywhere in India"};
const QUESTIONS=["Your field","Your skills","Hours per week","How many months","Market or industry","Product type","Budget to start","City or region"];
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ftag=k=>`<span class="tag ${FIELDS[k]?FIELDS[k].cls:"c-gray"}">${esc(FIELDS[k]?FIELDS[k].label:k)}</span>`;
function ring(score,label){const r=25,c=2*Math.PI*r,off=c*(1-Math.max(0,Math.min(100,score))/100),col=score>=75?"var(--teal)":score>=50?"var(--ring-mid)":"var(--gray-line)";
  return `<div class="ring" role="img" aria-label="${label?esc(label)+" ":""}${score} out of 100"><svg width="60" height="60" viewBox="0 0 60 60"><circle cx="30" cy="30" r="${r}" fill="none" stroke="var(--line)" stroke-width="6"/><circle cx="30" cy="30" r="${r}" fill="none" stroke="${col}" stroke-width="6" stroke-linecap="round" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/></svg><b>${score}</b></div>`;}
const VERDICT=t=>t>=75?{k:"Build",cls:"c-green",why:"Strong enough to start building. Test it with real customers first."}:t>=50?{k:"Explore",cls:"c-amber",why:"Real potential, but one thing needs testing before you build."}:{k:"Skip",cls:"c-gray",why:"Not worth the time yet. Reshape the strongest part or pick another idea."};
const vtag=t=>{const v=VERDICT(t); return `<span class="tag ${v.cls}">${v.k}</span>`;};
const badge=i=>i.origin==="seed"?'<span class="ex-badge">Example</span>':'<span class="live-badge">Live</span>';
if($("#heroRing")) $("#heroRing").innerHTML=ring(84,"Score");

let META={ai:false,sectors:[]}, ideas=[], team=null, teamCode=store.get("teamCode",null);

/* ================= feed ================= */
let minScore=0;
function fillFilters(){
  if(!$("#fField")) return;
  $("#fField").innerHTML='<option value="">All fields</option>'+Object.keys(FIELDS).filter(k=>k!=="other").map(k=>`<option value="${k}">${FIELDS[k].label}</option>`).join("");
  const fs=$("#fSector"),cur=fs.value,secs=[...new Set(ideas.map(i=>i.sector))].sort();
  fs.innerHTML='<option value="">All markets</option>'+secs.map(s=>`<option>${esc(s)}</option>`).join(""); fs.value=secs.includes(cur)?cur:"";
}
function card(i){
  return `<button class="card" type="button" data-id="${i.id}">
    <div class="card-top"><div><div class="sector">${esc(i.sector)}${badge(i)}</div><h3>${esc(i.title)}</h3></div>${ring(i.total,"Score")}</div>
    <p class="prob">${esc(i.problem)}</p>
    <div class="facts">${PRODUCT[i.product]||"Mix"} · ${esc(BUDGET[i.budget]||"")} · ${i.hours} team hrs a week for ${i.months} months</div>
    <div class="meta">${vtag(i.total)}${Object.keys(i.roles||{}).map(ftag).join("")}</div></button>`;
}
function renderFeed(){
  if(!$("#ideaGrid")) return;
  const q=$("#q").value.trim().toLowerCase(),f=$("#fField").value,s=$("#fSector").value;
  const list=ideas.filter(i=>i.total>=minScore&&(!f||(i.roles||{})[f])&&(!s||i.sector===s)&&(!q||(i.title+" "+i.problem+" "+i.solution).toLowerCase().includes(q)));
  $("#ideaGrid").innerHTML=list.length?list.map(card).join(""):`<p class="empty">No ideas match these filters. Clear the search or pick another field.</p>`;
}
async function loadIdeas(){
  try{ const d=await api("/api/ideas?limit=200"); ideas=d.ideas; fillFilters(); renderFeed(); }
  catch(e){ if($("#ideaGrid")) $("#ideaGrid").innerHTML=`<p class="empty">Couldn't load ideas: ${esc(e.message)}. Check that the server is running.</p>`; }
}
if($("#q")){ $("#q").addEventListener("input",renderFeed); $("#fField").addEventListener("change",renderFeed); $("#fSector").addEventListener("change",renderFeed); }
document.querySelectorAll(".seg button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".seg button").forEach(x=>x.setAttribute("aria-pressed","false")); b.setAttribute("aria-pressed","true"); minScore=+b.dataset.min; renderFeed();}));
document.addEventListener("click",e=>{const el=e.target.closest("[data-id]"); if(el) openIdea(+el.dataset.id);});

/* ================= idea dialog ================= */
const dlg=$("#dlg");
const NEXT={need:"Talk to 15 people who face this problem and ask how often it happens and what it costs them.",revenue:"Ask 10 possible customers what they pay today for a workaround, and whether they would pay for yours.",seed:"Write down how this grows past the first town or customer group, and what changes in the next 2 years.",entre:"List the skills and weekly hours your team really has, and how you will reach the first 10 customers.",impact:"Estimate who benefits and how, then ask one expert or user to check it."};
function weakest(sc){const worst=LENSES.map(l=>({k:l.k,label:l.label,r:(sc[l.k]||0)/l.max})).sort((a,b)=>a.r-b.r)[0]; return `${worst.label} is the lowest area. ${NEXT[worst.k]}`;}
async function openIdea(id){
  $("#dlgBody").innerHTML=`<p class="note">Loading…</p>`;
  if(typeof dlg.showModal==="function"&&!dlg.open) dlg.showModal(); else dlg.setAttribute("open","");
  let i; try{ i=(await api("/api/ideas/"+id)).idea; }catch(e){ $("#dlgBody").innerHTML=`<p class="msg c-amber">${esc(e.message)}</p><button class="btn btn-ghost" type="button" onclick="this.closest('dialog').close()">Close</button>`; return; }
  const t=i.total, model=i.model||{}, checks=i.checks||{}, dm=i.domain_metrics||{};
  const metrics=Object.keys(dm).map(f=>`<div><b>${esc(FIELDS[f]?FIELDS[f].label:f)}</b>${Object.entries(dm[f]).map(([k,v])=>`${esc(k)}: ${esc(v)}`).join(" · ")}</div>`).join("");
  $("#dlgBody").innerHTML=`
   <div class="dlg-head"><div><div style="font-size:13px;font-weight:700;color:var(--teal)">${esc(i.sector)}${badge(i)}</div><h2 id="dlgTitle">${esc(i.title)}</h2>
     <span class="tag ${VERDICT(t).cls}">${VERDICT(t).k} · ${t} / 100</span></div>
     <button class="x" type="button" id="dlgClose" aria-label="Close">✕</button></div>
   <div class="box c-teal"><h3>Verdict: ${VERDICT(t).k}</h3><p>${VERDICT(t).why}</p><p style="margin-top:6px"><b>Test next:</b> ${weakest(i.scores)}</p></div>
   <div class="two"><div class="box"><h3>Problem statement</h3><p>${esc(i.problem)}</p></div><div class="box"><h3>Business idea</h3><p>${esc(i.solution)}</p></div></div>
   <div class="box"><h3>Where each field could help (suggestions)</h3><div class="roles">${Object.keys(i.roles||{}).map(k=>`<div class="role">${ftag(k)}<span>${esc(i.roles[k])}</span></div>`).join("")}</div>
     <p class="note" style="margin:12px 0 0">${PRODUCT[i.product]||"Mix"} · start budget ${esc(BUDGET[i.budget]||"")} · about ${i.hours} team hours a week for ${i.months} months.</p></div>
   <div class="two">
     <div class="box c-lav"><h3>Reality check</h3><div class="qa">${CHECKS.map(q=>`<div><b>${q.q}</b>${esc(checks[q.k]||"Not checked yet")}</div>`).join("")}</div></div>
     <div class="box"><h3>Score out of 100</h3><div class="bars">${LENSES.map(l=>`<div class="bar-row"><span>${l.label}</span><div class="bar"><i style="width:${((i.scores[l.k]||0)/l.max*100).toFixed(0)}%"></i></div><b>${i.scores[l.k]||0}/${l.max}</b></div>`).join("")}</div>
       ${metrics?`<h3 style="margin-top:16px">Domain metrics</h3><div class="qa">${metrics}</div>`:""}</div>
   </div>
   <div class="box c-amber"><h3>Business model to consider</h3><div class="qa" style="gap:6px">${[["customer","Customer"],["value","Value"],["revenue","Revenue"],["pricing","Pricing"],["costs","Costs"],["channels","Channels"]].map(([k,l])=>`<div><b style="display:inline">${l}:</b> ${esc(model[k]||"—")}</div>`).join("")}</div></div>
   ${i.reviewed_by?`<p class="note">Finalized by ${esc(i.reviewed_by)}${i.reviewed_at?" on "+esc(String(i.reviewed_at).slice(0,10)):""}.</p>`:""}
   ${i.evidence&&i.evidence.length?`<div class="box proof"><h3>Proof from the market</h3>${i.evidence.slice(0,8).map(e=>`<a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)} <span class="note">(${esc(e.source)})</span></a>`).join("")}</div>`:""}
`;
  $("#dlgClose").onclick=()=>dlg.close();
}
dlg.addEventListener("click",e=>{if(e.target===dlg) dlg.close();});
/* ================= chatbot ================= */
const log=$("#chatLog"),input=$("#chatInput"),hasChat=!!log;
let answered=new Set(), draft=null, size=0, idx=0;
const renderQs=()=>{$("#qlist").innerHTML=QUESTIONS.map((q,n)=>`<li class="${answered.has(n)?"done":""}"><i>${n+1}</i>${q}</li>`).join("");};
const setProgress=t=>{$("#progress").textContent=t||"";};
function say(t,who){const d=document.createElement("div"); d.className="bubble "+(who==="me"?"me":"bot"); d.textContent=t; log.appendChild(d); log.scrollTop=log.scrollHeight;}
function chips(opts,onPick){input.innerHTML=""; const w=document.createElement("div"); w.className="chips";
  opts.forEach(o=>{const b=document.createElement("button"); b.type="button"; b.className="chip"; b.textContent=o.label; b.onclick=()=>{say(o.label,"me"); onPick(o.value);}; w.appendChild(b);}); input.appendChild(w);}
function text(ph,onDone,skip){input.innerHTML=""; const f=document.createElement("form"); f.className="text-row";
  f.innerHTML=`<label class="sr" for="chatTxt">${esc(ph)}</label><input id="chatTxt" autocomplete="off" maxlength="120" placeholder="${esc(ph)}"><button class="btn btn-primary btn-sm" type="submit">Send</button>`;
  f.onsubmit=e=>{e.preventDefault(); const v=f.querySelector("input").value.trim(); if(!v) return; say(v,"me"); onDone(v);}; input.appendChild(f);
  if(skip){const s=document.createElement("div"); s.className="chips"; const b=document.createElement("button"); b.type="button"; b.className="chip"; b.textContent=skip; b.onclick=()=>{say(skip,"me"); onDone("");}; s.appendChild(b); input.appendChild(s);}
  const t=f.querySelector("input"); if(t) t.focus({preventScroll:true});}
function startChat(){
  log.innerHTML=""; answered=new Set(); renderQs(); setProgress(""); draft=null;
  say("Hi! I'll help your team find one business idea that uses everyone's skills. Are you starting a new team, or joining one with a code?");
  chips([{label:"Start a new team",value:"new"},{label:"Join with a team code",value:"join"}],v=>v==="new"?newTeam():joinTeam());
}
function newTeam(){
  draft={members:[],market:"Any",product:"mix",budget:"unsure",setting:"any",city:""};
  say("How many people are in your team?");
  chips([2,3,4,5,6].map(n=>({label:String(n),value:n})),n=>{size=n; idx=0; askMember(m=>{draft.members.push(m); renderDraft(); idx++; if(idx<size) askNext(); else askTeam();});});
  function askNext(){ askMember(m=>{draft.members.push(m); renderDraft(); idx++; if(idx<size) askNext(); else askTeam();}); }
}
function askMember(done){
  const n=(draft?idx:0)+1; setProgress(draft?`Member ${n} of ${size}`:"Your answers");
  const m={field:"other",skills:"",hours:10,months:6};
  say(draft?`Member ${n}: what's their field?`:"What's your field?");
  chips(Object.keys(FIELDS).map(k=>({label:FIELDS[k].label,value:k})),f=>{
    m.field=f; answered.add(0); renderQs();
    say("What are they good at? For example: coding, CAD, circuits, sales.");
    text("Skills",s=>{ m.skills=s; answered.add(1); renderQs();
      say("How many hours a week can they give?");
      chips([5,10,15,20,30].map(h=>({label:h+" hrs",value:h})),h=>{ m.hours=h; answered.add(2); renderQs();
        say("For how many months?");
        chips([3,6,9,12].map(x=>({label:x+" months",value:x})),mo=>{ m.months=mo; answered.add(3); renderQs(); done(m); });
      });
    },"Skip");
  });
}
function askTeam(){
  setProgress("Team questions");
  say("Now a few questions for the whole team. Which market or industry interests you?");
  const secs=["Any"].concat([...new Set(ideas.map(i=>i.sector))].sort());
  chips(secs.map(s=>({label:s,value:s})),mk=>{ draft.market=mk; answered.add(4); renderQs();
    say("What would you like to build: an app, a device, or a service?");
    chips([{label:"App",value:"app"},{label:"Device",value:"device"},{label:"Service",value:"service"},{label:"A mix",value:"mix"}],p=>{ draft.product=p; answered.add(5); renderQs();
      say("Roughly how much can the team spend to start?");
      chips([{label:BUDGET.low,value:"low"},{label:BUDGET.mid,value:"mid"},{label:BUDGET.high,value:"high"},{label:"Not sure",value:"unsure"}],b=>{ draft.budget=b; answered.add(6); renderQs();
        say("Where do you want to start selling?");
        chips(Object.keys(SETTING).map(k=>({label:SETTING[k],value:k})),st=>{ draft.setting=st;
          say("Which city or region exactly? You can skip this.");
          text("City or region",async c=>{ draft.city=c; answered.add(7); renderQs(); input.innerHTML=""; say("Saving your team…");
            try{ const d=await api("/api/teams",{method:"POST",body:draft}); team=d.team; teamCode=team.code; store.set("teamCode",teamCode); finish(true); }
            catch(e){ say("Couldn't save the team: "+e.message); chips([{label:"Try again",value:1}],()=>askTeam()); }
          },"Skip");
        });
      });
    });
  });
}
function joinTeam(){
  say("Type the 6-character team code your teammate shared.");
  text("Team code",async code=>{
    try{ team=(await api("/api/teams/"+encodeURIComponent(code.trim().toUpperCase()))).team; }
    catch(e){ say("I couldn't find that code. Check it and try again."); return joinTeam(); }
    teamCode=team.code; store.set("teamCode",teamCode); renderTeam();
    say(`Found team ${team.code} with ${team.members.length} members. Now your own answers.`);
    draft=null; askMember(async m=>{
      try{ team=(await api(`/api/teams/${teamCode}/members`,{method:"POST",body:m})).team; [4,5,6,7].forEach(n=>answered.add(n)); renderQs(); finish(false); }
      catch(e){ say("Couldn't add you: "+e.message); }
    });
  });
}
function finish(isNew){
  setProgress("Done"); renderTeam();
  const fl=[...new Set(team.members.map(m=>FIELDS[m.field].label))];
  say(`${isNew?"Saved":"Added"}: ${team.members.length} members across ${fl.join(", ")}, ${team.hours_per_week} hours a week for about ${team.months} months. Here are some ideas you could consider. They're only suggestions, so it's your call.`);
  doneChips(); loadMatches(); setTimeout(()=>{const a=$("#matchArea"); if(a) a.scrollIntoView({block:"start"});},120);
}
function doneChips(){
  input.innerHTML=`<div class="chips"><button class="chip" type="button" id="seeM">See matched ideas</button><button class="chip" type="button" id="againC">Start a different team</button></div>`;
  $("#seeM").onclick=()=>$("#matchArea").scrollIntoView({block:"start"});
  $("#againC").onclick=()=>{store.del("teamCode"); teamCode=null; team=null; renderTeam(); $("#matchArea").innerHTML=""; startChat();};
}
if(hasChat) $("#restartChat").onclick=()=>{store.del("teamCode"); teamCode=null; team=null; renderTeam(); $("#matchArea").innerHTML=""; startChat();};

function renderDraft(){ team={members:draft.members,hours_per_week:draft.members.reduce((a,m)=>a+m.hours,0),months:Math.min(...draft.members.map(m=>m.months))}; renderTeam(true); }
function renderTeam(isDraft){
  const tl=$("#teamList"),ts=$("#teamStats");
  if(!team||!team.members||!team.members.length){tl.innerHTML=`<p class="empty">No members yet. Start the chat to add your team.</p>`; ts.innerHTML=""; return;}
  tl.innerHTML=team.members.map((m,n)=>`<div class="member"><div class="avatar ${FIELDS[m.field].cls}">${FIELDS[m.field].short}</div><div><b>Member ${n+1} · ${FIELDS[m.field].label}</b><span>${esc(m.skills||"Skills not added")} · ${m.hours} hrs a week · ${m.months} months</span></div></div>`).join("");
  const prefs=[];
  if(team.market) prefs.push(`<span class="tag c-green">${esc(team.market==="Any"?"Any market":team.market)}</span>`);
  if(team.product) prefs.push(`<span class="tag c-blue">${team.product==="mix"?"Any product":PRODUCT[team.product]}</span>`);
  if(team.budget) prefs.push(`<span class="tag c-amber">${team.budget==="unsure"?"Budget not sure":esc(BUDGET[team.budget])}</span>`);
  if(team.setting) prefs.push(`<span class="tag c-pink">${esc(team.city||SETTING[team.setting])}</span>`);
  ts.innerHTML=`<div class="stats"><div class="stat"><b>${team.hours_per_week}</b><span>team hrs a week</span></div><div class="stat"><b>${team.months}</b><span>months together</span></div><div class="stat"><b>${new Set(team.members.map(m=>m.field)).size}</b><span>fields</span></div></div>`+(prefs.length?`<div class="team-prefs">${prefs.join("")}</div>`:"")+
    (!isDraft&&team.code?`<div class="code-box">Team code <b>${esc(team.code)}</b><span>Share it so teammates can add themselves from their own device.</span><button class="btn btn-ghost btn-sm" type="button" id="copyCode">Copy</button></div>`:"");
  const cc=$("#copyCode"); if(cc) cc.onclick=()=>{ if(navigator.clipboard) navigator.clipboard.writeText(team.code).then(()=>{cc.textContent="Copied";},()=>{}); };
}
function matchRow(m){
  const i=m.idea,f=m.fit;
  return `<div class="match">${ring(f.match,"Team match")}
   <div><h4>${esc(i.title)}${badge(i)}</h4><p>${esc(i.problem)}</p>
    <div class="why-tags"><span class="tag c-teal">${f.fields_used} of ${f.fields_total} fields used</span>
      ${f.missing.length?`<span class="tag c-amber">Could add ${esc(f.missing.join(", "))}</span>`:`<span class="tag c-green">Covers every field</span>`}
      <span class="tag ${f.fits_time?"c-green":"c-amber"}">${f.fits_time?"Fits your time":"May need more time"}</span>
      <span class="tag ${f.fits_budget?"c-green":"c-amber"}">${f.fits_budget?"Fits budget":"Budget may be tight"}</span>
      ${f.unused.length?`<span class="tag c-gray">Less relevant for ${esc(f.unused.join(", "))}</span>`:""}</div></div>
   <div class="act"><button class="btn btn-ghost btn-sm" type="button" data-id="${i.id}">Open idea</button></div></div>`;
}
async function loadMatches(){
  const a=$("#matchArea"); if(!teamCode){a.innerHTML=""; return;}
  a.innerHTML=`<p class="note" style="margin-top:32px">Finding your best ideas…</p>`;
  try{
    const d=await api(`/api/teams/${teamCode}/matches?limit=3`);
    a.innerHTML=`<div class="matches-head"><div><h3>Ideas you could consider</h3><p>Suggested from your skills, time, product, budget, market and the idea's score. Treat them as a starting point.</p></div>
      ${META.ai?`<button class="btn btn-soft" type="button" id="genIdeas">Find new ideas from live data</button>`:""}</div>
      <div class="matches">${d.matches.map(matchRow).join("")||'<p class="empty">No ideas yet.</p>'}</div><div id="genOut" aria-live="polite"></div>`;
    const g=$("#genIdeas"); if(g) g.onclick=genIdeas;
  }catch(e){ a.innerHTML=`<p class="msg c-amber">${esc(e.message)}</p>`; }
}
async function genIdeas(){
  const btn=$("#genIdeas"),out=$("#genOut"); btn.disabled=true;
  out.innerHTML=`<p class="msg c-lav">Building new ideas from the latest market problems for your team. This can take a minute or two.</p>`;
  try{
    const d=await api(`/api/teams/${teamCode}/generate`,{method:"POST"});
    out.innerHTML=d.sent_for_review?`<p class="msg c-green">${d.sent_for_review} new idea${d.sent_for_review===1?"":"s"} made for your team. A reviewer will read ${d.sent_for_review===1?"it":"them"} first, and ${d.sent_for_review===1?"it":"they"} will appear on the site once approved.</p>`:d.ideas.length?`<div class="matches" style="margin-top:14px">${d.ideas.map(matchRow).join("")}</div><p class="note">New ideas are added to the idea bank too. Check each problem with real people before you build.</p>`:`<p class="msg c-amber">No new idea passed all four business rules this time. Try again after the next data run.</p>`;
    loadIdeas();
  }catch(e){ out.innerHTML=`<p class="msg c-amber">${esc(e.message)}</p>`; }
  finally{ btn.disabled=false; }
}

/* ================= init ================= */
(async function init(){
  if($("#ideaGrid")||hasChat){ try{ META=await api("/api/meta"); }catch(e){} await loadIdeas(); }
  if(!hasChat) return;
  renderQs();
  if(teamCode){
    try{ team=(await api("/api/teams/"+teamCode)).team; [0,1,2,3,4,5,6,7].forEach(n=>answered.add(n)); renderQs(); renderTeam();
      say(`Welcome back. Team ${team.code} has ${team.members.length} members and ${team.hours_per_week} hours a week.`); doneChips(); setProgress("Done"); loadMatches(); }
    catch(e){ store.del("teamCode"); teamCode=null; startChat(); }
  } else startChat();
})();
})();
