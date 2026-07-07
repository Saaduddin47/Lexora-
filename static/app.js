const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let activeClient = "general";
let activeClientName = "General workspace";
let network = null, statusChart = null, typeChart = null;

const api = {
  async get(u){ return (await fetch(u)).json(); },
  async post(u,b){ return (await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json(); },
  async patch(u,b){ return (await fetch(u,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json(); },
  async del(u){ return (await fetch(u,{method:'DELETE'})).json(); },
};

/* ---------------- tabs ---------------- */
$$('.tab').forEach(t=>t.onclick=()=>{
  $$('.tab').forEach(x=>x.classList.remove('active'));
  $$('.view').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  $('#view-'+t.dataset.tab).classList.add('active');
  if(t.dataset.tab==='graph') loadGraph();
  if(t.dataset.tab==='docs') loadDocs();
  if(t.dataset.tab==='dash') loadDash();
  if(t.dataset.tab==='live') liveInit();
  if(t.dataset.tab==='phone') phoneStart(); else phoneStop();
});

/* ---------------- sidebar toggle ---------------- */
$('#sidebarToggle').onclick=()=>document.getElementById('app').classList.toggle('sidebar-closed');

/* ---------------- new chat (clear thread -> centered hero) ---------------- */
$('#newChatBtn').onclick=async()=>{
  await api.del(`/api/clients/${activeClient}/messages`);
  $$('.tab').forEach(x=>x.classList.remove('active'));
  $$('.view').forEach(x=>x.classList.remove('active'));
  document.querySelector('.tab[data-tab="chat"]').classList.add('active');
  $('#view-chat').classList.add('active');
  await loadMessages();          // empty thread -> Lexora hero, prompt centered
  $('#chatInput').focus();
};

/* ---------------- clients ---------------- */
const AVATAR_COLORS=['#c8a24a','#4f8cff','#10a37f','#a371f7','#e5685e','#e0a93b','#db61a2','#3fb27f'];
function initials(name){
  const p=(name||'?').trim().split(/\s+/);
  return ((p[0]||'')[0]||'')+((p[1]||'')[0]||'')||(name||'?')[0];
}
function avatarColor(seed){
  let h=0; for(const ch of (seed||'')) h=(h*31+ch.charCodeAt(0))>>>0;
  return AVATAR_COLORS[h%AVATAR_COLORS.length];
}
async function loadClients(){
  const {clients} = await api.get('/api/clients');
  const list = $('#clientList'); list.innerHTML='';
  const gen = document.createElement('div');
  gen.className='client-item'+(activeClient==='general'?' active':'');
  gen.innerHTML='<div class="ci-avatar" style="background:#3a4768;color:#fff">💬</div>'
    +'<div class="ci-main"><div class="nm">General workspace</div><div class="meta">No specific client</div></div>';
  gen.onclick=()=>selectClient('general','General workspace');
  list.appendChild(gen);
  clients.forEach(c=>{
    const d=document.createElement('div');
    d.className='client-item'+(activeClient===c.id?' active':'');
    const st=(c.case_status||'open').replace(' ','-');
    d.innerHTML=`<button class="del-client" title="Delete client">🗑</button>
      <div class="ci-avatar" style="background:${avatarColor(c.id||c.name)}">${esc(initials(c.name))}</div>
      <div class="ci-main">
        <div class="nm">${esc(c.name)}</div>
        <div class="meta"><span class="badge ${st}">${esc(c.case_status)}</span> · ${esc(c.case_type)} · ${c.messages} msgs</div>
      </div>`;
    d.onclick=()=>selectClient(c.id,c.name);
    d.querySelector('.del-client').onclick=ev=>{ ev.stopPropagation(); deleteClient(c.id,c.name); };
    list.appendChild(d);
  });
  applyClientFilter();
}
async function deleteClient(id,name){
  if(!confirm(`Delete client "${name}" and all of their chat, statements, documents and knowledge graph?\n\nThis cannot be undone.`)) return;
  await api.del('/api/clients/'+id);
  toast(`Deleted client “${name}”`,'info');
  if(activeClient===id) selectClient('general','General workspace');
  else await loadClients();
}
async function selectClient(id,name){
  activeClient=id; activeClientName=name;
  $('#activeClient').textContent = id==='general'?'General workspace':('Client · '+name);
  $('#dzClient').textContent = id==='general'?'Indexed into the shared library':('Indexed for '+name);
  await loadClients(); await loadMessages();
  if($('.tab.active').dataset.tab==='graph') loadGraph();
}

/* ---------------- chat ---------------- */
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function addMsg(role,html,extra){
  const m=document.createElement('div');
  m.className='msg '+role;
  m.innerHTML=`<div class="av">${role==='user'?'🧑‍⚖️':'⚖'}</div><div class="body">${html}${extra||''}</div>`;
  $('#messages').appendChild(m);
  $('#messages').scrollTop=$('#messages').scrollHeight;
  return m;
}
async function loadMessages(){
  $('#messages').innerHTML='';
  const vc=document.getElementById('view-chat');
  const {messages}=await api.get(`/api/clients/${activeClient}/messages`);
  if(!messages.length){
    vc.classList.add('empty');          // show centered Lexora hero
    $('#chatHero').querySelector('.hero-tag').textContent =
      activeClient==='general' ? 'Pick or create a client to build case memory & a knowledge graph.'
                               : 'Tell me about this case — I\'ll remember details and flag contradictions.';
  } else {
    vc.classList.remove('empty');
    messages.forEach(m=>addMsg(m.role==='user'?'user':'assistant',esc(m.content)));
  }
}
async function send(){
  const inp=$('#chatInput'); const text=inp.value.trim(); if(!text) return;
  document.getElementById('view-chat').classList.remove('empty');   // leave hero, go to thread
  inp.value=''; inp.style.height='auto';
  addMsg('user',esc(text));
  const t=addMsg('assistant','<span class="typing"><i></i><i></i><i></i></span>');
  $('#sendBtn').disabled=true;
  try{
    const r=await api.post('/api/chat',{client_id:activeClient,message:text});
    let extra='';
    if(r.contradictions&&r.contradictions.length){
      const c=r.contradictions[0];
      extra+=`<div class="contradiction-card"><b>⚠ Contradiction detected</b><br>${esc(c.reason)}<br>
        <span class="muted">Earlier: “${esc(c.prior_text)}”</span></div>`;
    }
    if(r.calendar){
      const cal=r.calendar;
      if(cal.conflicts&&cal.conflicts.length){
        const x=cal.conflicts[0];
        extra+=`<div class="contradiction-card"><b>⚠ Schedule conflict</b><br>Clashes with “${esc(x.title)}” on ${esc(x.when)}.</div>`;
      }
      extra+=`<div class="action-card">📅 <b>${esc(cal.title)}</b> — ${esc(cal.when)}<br><a href="${cal.gcal_link}" target="_blank" rel="noopener" class="cal-link">➕ Add to Google Calendar</a></div>`;
    }
    if(r.email){
      extra+= r.email.sent
        ? `<div class="action-card">📧 Case summary emailed to <b>${esc(r.email.to)}</b></div>`
        : `<div class="contradiction-card"><b>⚠ Email not sent</b><br>${esc(r.email.error)}</div>`;
    }
    if(r.memory_used&&r.memory_used.length) extra+=`<span class="ctx-pill">🧠 ${r.memory_used.length} memory recall</span>`;
    if(r.documents_used&&r.documents_used.length) extra+=`<span class="ctx-pill">📄 ${r.documents_used.length} doc chunks (RAG)</span>`;
    t.querySelector('.body').innerHTML=esc(r.answer)+extra;
  }catch(e){ t.querySelector('.body').textContent='Error: '+e; }
  $('#sendBtn').disabled=false;
  $('#messages').scrollTop=$('#messages').scrollHeight;
  loadClients();
}
$('#sendBtn').onclick=send;
$('#chatInput').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}
});
$('#chatInput').addEventListener('input',e=>{e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,160)+'px';});

/* suggestion chips (hero) */
$$('.chip').forEach(c=>c.onclick=()=>{ const inp=$('#chatInput'); inp.value=c.dataset.q; inp.focus(); });

/* attach in composer */
$('#pdfInput').onchange=e=>uploadPdf(e.target.files[0],true);

/* ---------------- documents / RAG ---------------- */
async function uploadPdf(file,fromChat){
  if(!file) return;
  const hint = fromChat?$('#uploadHint'):$('#dzClient');
  if(fromChat) hint.textContent=`Indexing ${file.name}…`;
  const fd=new FormData(); fd.append('file',file); fd.append('client_id',activeClient);
  const r=await (await fetch('/api/upload',{method:'POST',body:fd})).json();
  if(r.error){ if(fromChat) hint.textContent='Upload failed: '+r.error; toast('Upload failed: '+r.error,'error'); return; }
  const msg=`📄 Indexed “${r.filename}” → ${r.chunks} chunks. RAG is active — ask me about it.`;
  if(fromChat){ hint.textContent=''; document.getElementById('view-chat').classList.remove('empty'); addMsg('assistant',msg); }
  toast(`Indexed “${r.filename}” · ${r.chunks} chunks`,'ok');
  loadDocs();
}
async function loadDocs(){
  const {documents}=await api.get('/api/documents');
  const el=$('#docList'); el.innerHTML='';
  if(!documents.length){ el.innerHTML='<div class="muted">No documents indexed yet.</div>'; return; }
  documents.forEach(d=>{
    const x=document.createElement('div'); x.className='doc-item';
    x.innerHTML=`<span>📄 ${esc(d.source)}</span><span class="muted">${d.chunks} chunks · ${d.client_id==='general'?'shared':esc(d.client_id)}</span>`;
    el.appendChild(x);
  });
}
$('#docInput').onchange=e=>uploadPdf(e.target.files[0],false);
const dz=$('#dropzone');
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag');});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag'));
dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('drag');uploadPdf(e.dataTransfer.files[0],false);});

/* ---------------- knowledge graph (dependency-free canvas renderer) ---------------- */
const NODE_COLORS={client:'#c8a24a',person:'#4f8cff',place:'#e0a93b',date:'#a371f7',
  event:'#e5685e',organization:'#10a37f',object:'#8b94a7',claim:'#db61a2',entity:'#8b94a7'};
const TYPE_LABELS={client:'Client',person:'Person',place:'Place',date:'Date',event:'Event',
  organization:'Organization',object:'Object',claim:'Claim',entity:'Entity'};
const SOURCE_LABELS={chat:'💬 Chat',voice_call:'📞 Voice call',live_call:'📱 Live call',
  calendar:'📅 Calendar',email:'📧 Email'};
let graphRAF=null;          // active animation frame id
let graphCleanup=null;      // teardown for listeners
let graphApi=null;          // control surface exposed by the current render (filters/search/fit)

async function loadGraph(){
  const host=$('#graph');
  $('#graphClient').textContent = activeClient==='general'?'— select a client':('· '+activeClientName);
  if(graphRAF){ cancelAnimationFrame(graphRAF); graphRAF=null; }
  if(graphCleanup){ graphCleanup(); graphCleanup=null; }
  graphApi=null;
  $('#graphStats').textContent='';
  renderGraphPanel(null);
  if(activeClient==='general'){ host.innerHTML='<div style="padding:30px;color:var(--muted)">Select a client (left sidebar) to see their evolving knowledge graph.</div>'; return; }
  let g;
  try { g=await api.get(`/api/clients/${activeClient}/graph`); }
  catch(e){ host.innerHTML='<div style="padding:30px;color:var(--danger)">Could not load graph: '+e+'</div>'; return; }
  if(!g || !g.nodes || !g.nodes.length){
    host.innerHTML='<div style="padding:30px;color:var(--muted)">No knowledge yet for this client. Chat about the case and the graph will build automatically.</div>';
    return;
  }
  graphApi=renderForceGraph(host,g);
}

function renderForceGraph(host,g){
  host.innerHTML='';
  const canvas=document.createElement('canvas');
  canvas.style.cssText='width:100%;height:100%;display:block;cursor:grab';
  host.appendChild(canvas);
  const ctx=canvas.getContext('2d');
  let W=1,H=1,dpr=window.devicePixelRatio||1;

  function resize(){
    const r=host.getBoundingClientRect();
    W=Math.max(r.width,300); H=Math.max(r.height,300);
    canvas.width=W*dpr; canvas.height=H*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);
  }
  resize();

  // ---- connection count per node (drives sizing) ----
  const degree={};
  g.edges.forEach(e=>{ degree[e.source]=(degree[e.source]||0)+1; degree[e.target]=(degree[e.target]||0)+1; });

  // ---- build node/edge model with positions spread around the centre ----
  const idx={};
  const nodes=g.nodes.map((n,i)=>{
    const a=(i/g.nodes.length)*Math.PI*2;
    const deg=degree[n.id]||0;
    const base=(n.type==='client')?22:12;
    const o={id:n.id,label:n.label||n.id,type:n.type||'entity',degree:deg,raw:n,
      x:W/2+Math.cos(a)*Math.min(W,H)*0.28+(i%2?12:-12),
      y:H/2+Math.sin(a)*Math.min(W,H)*0.28,vx:0,vy:0,fixed:false,
      r:Math.min(base+deg*1.6,(n.type==='client')?34:26)};
    idx[n.id]=o; return o;
  });
  const edges=g.edges.filter(e=>idx[e.source]&&idx[e.target])
    .map(e=>({s:idx[e.source],t:idx[e.target],label:e.label||'',raw:e}));

  // ---- type filters ----
  const hiddenTypes=new Set();
  const isHidden=n=>hiddenTypes.has(n.type);
  const visNodes=()=>nodes.filter(n=>!isHidden(n));
  const visEdges=()=>edges.filter(e=>!isHidden(e.s)&&!isHidden(e.t));

  // ---- pan / zoom transform ----
  const view={scale:1,ox:0,oy:0};
  const toWorld=(sx,sy)=>({x:(sx-view.ox)/view.scale,y:(sy-view.oy)/view.scale});
  function fit(){
    const vn=visNodes();
    if(!vn.length) return;
    let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
    vn.forEach(n=>{ minX=Math.min(minX,n.x-n.r); maxX=Math.max(maxX,n.x+n.r);
                    minY=Math.min(minY,n.y-n.r); maxY=Math.max(maxY,n.y+n.r); });
    const w=Math.max(maxX-minX,40), h=Math.max(maxY-minY,40);
    view.scale=Math.max(Math.min(W/(w+80),H/(h+80),1.6),0.15);
    view.ox=W/2-(minX+w/2)*view.scale;
    view.oy=H/2-(minY+h/2)*view.scale;
  }

  let alpha=1.0;                       // simulation temperature
  const K=Math.max(70,Math.min(150,Math.sqrt(W*H/Math.max(nodes.length,1))*0.55));

  function step(){
    // repulsion (all pairs)
    for(let i=0;i<nodes.length;i++){
      const a=nodes[i];
      for(let j=i+1;j<nodes.length;j++){
        const b=nodes[j];
        let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy||0.01, d=Math.sqrt(d2);
        const f=(K*K)/d2*alpha*0.9;
        const fx=dx/d*f, fy=dy/d*f;
        a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
      }
    }
    // spring attraction along edges
    edges.forEach(e=>{
      let dx=e.t.x-e.s.x, dy=e.t.y-e.s.y, d=Math.sqrt(dx*dx+dy*dy)||0.01;
      const f=(d-K)/d*alpha*0.06;
      const fx=dx*f, fy=dy*f;
      e.s.vx+=fx; e.s.vy+=fy; e.t.vx-=fx; e.t.vy-=fy;
    });
    // gravity toward centre + integrate
    nodes.forEach(n=>{
      if(n.fixed) { n.vx=0; n.vy=0; return; }
      n.vx+=(W/2-n.x)*0.004*alpha; n.vy+=(H/2-n.y)*0.004*alpha;
      n.vx*=0.85; n.vy*=0.85;
      n.x+=Math.max(-30,Math.min(30,n.vx));
      n.y+=Math.max(-30,Math.min(30,n.vy));
    });
    if(alpha>0.03) alpha*=0.985;
  }

  // ---- selection ----
  let selected=null;
  function neighborsOf(node){
    const set=new Set([node.id]);
    edges.forEach(e=>{ if(e.s.id===node.id) set.add(e.t.id); if(e.t.id===node.id) set.add(e.s.id); });
    return set;
  }

  function draw(){
    ctx.clearRect(0,0,W,H);
    ctx.save();
    ctx.translate(view.ox,view.oy); ctx.scale(view.scale,view.scale);
    const focus = selected?neighborsOf(selected):null;
    ctx.font='10px Inter, Segoe UI, sans-serif';
    visEdges().forEach(e=>{
      const dim = focus && !(focus.has(e.s.id)&&focus.has(e.t.id));
      ctx.lineWidth=1.3;
      ctx.strokeStyle= dim?'rgba(200,162,74,0.14)':'rgba(200,162,74,0.32)';
      ctx.beginPath(); ctx.moveTo(e.s.x,e.s.y); ctx.lineTo(e.t.x,e.t.y); ctx.stroke();
      // arrow head
      const ang=Math.atan2(e.t.y-e.s.y,e.t.x-e.s.x);
      const ax=e.t.x-Math.cos(ang)*(e.t.r+2), ay=e.t.y-Math.sin(ang)*(e.t.r+2);
      ctx.fillStyle= dim?'rgba(200,162,74,0.25)':'rgba(200,162,74,0.6)'; ctx.beginPath();
      ctx.moveTo(ax,ay);
      ctx.lineTo(ax-Math.cos(ang-0.4)*8,ay-Math.sin(ang-0.4)*8);
      ctx.lineTo(ax-Math.cos(ang+0.4)*8,ay-Math.sin(ang+0.4)*8);
      ctx.closePath(); ctx.fill();
      // edge label
      if(e.label){
        const mx=(e.s.x+e.t.x)/2, my=(e.s.y+e.t.y)/2;
        ctx.fillStyle= dim?'#5b6478':'#9aa4bd'; ctx.textAlign='center';
        ctx.fillText(e.label,mx,my-3);
      }
    });
    // nodes (with glow)
    visNodes().forEach(n=>{
      const dim = focus && !focus.has(n.id);
      const col=NODE_COLORS[n.type]||'#8b94a7';
      ctx.save();
      ctx.globalAlpha= dim?0.3:1;
      ctx.shadowColor=col; ctx.shadowBlur=n.type==='client'?22:14;
      ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,Math.PI*2);
      ctx.fillStyle=col; ctx.fill();
      ctx.restore();
      ctx.save();
      ctx.globalAlpha= dim?0.3:1;
      ctx.lineWidth=2; ctx.strokeStyle='#0a0e18'; ctx.stroke();
      if(n.type==='client'){ ctx.lineWidth=2.5; ctx.strokeStyle='rgba(255,255,255,0.85)'; ctx.stroke(); }
      if(selected && n.id===selected.id){ ctx.lineWidth=3; ctx.strokeStyle='#ffffff'; ctx.stroke(); }
      // label
      ctx.font=(n.type==='client'?'600 13px':'12px')+' Inter, Segoe UI, sans-serif';
      ctx.textAlign='center'; ctx.textBaseline='middle';
      const tw=ctx.measureText(n.label).width;
      ctx.fillStyle='rgba(10,14,24,0.82)';
      ctx.fillRect(n.x-tw/2-5,n.y+n.r+3,tw+10,17);
      ctx.fillStyle= dim?'#7d879c':'#eef1f7';
      ctx.fillText(n.label,n.x,n.y+n.r+11.5);
      ctx.restore();
    });
    ctx.restore();
  }

  function frame(){ step(); draw(); graphRAF=requestAnimationFrame(frame); }
  fit(); frame();

  // ---- interaction: drag nodes, pan background, zoom, hover, select ----
  let drag=null, panStart=null, downPos=null, moved=false;
  function pos(ev){ const r=canvas.getBoundingClientRect(); return {x:ev.clientX-r.left,y:ev.clientY-r.top}; }
  function pickNode(pw){ return visNodes().find(n=>{const dx=n.x-pw.x,dy=n.y-pw.y;return dx*dx+dy*dy<=(n.r+4)*(n.r+4);}); }
  function distToSeg(p,a,b){
    const dx=b.x-a.x, dy=b.y-a.y, len2=dx*dx+dy*dy||0.0001;
    let t=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/len2));
    return Math.hypot(p.x-(a.x+t*dx), p.y-(a.y+t*dy));
  }
  function pickEdge(pw){
    const thresh=6/view.scale; let best=null,bestD=thresh;
    visEdges().forEach(e=>{ const d=distToSeg(pw,e.s,e.t); if(d<bestD){ bestD=d; best=e; } });
    return best;
  }
  function showTooltip(html,p){
    const tip=$('#graphTooltip'); if(!tip) return;
    tip.innerHTML=html;
    tip.style.left=Math.min(p.x+14,W-190)+'px';
    tip.style.top=Math.max(p.y-10,4)+'px';
    tip.classList.remove('hidden');
  }
  function hideTooltip(){ const tip=$('#graphTooltip'); if(tip) tip.classList.add('hidden'); }
  function select(node){
    selected=node;
    if(node) node.fixed=false;
    renderGraphPanel(node,edges);
  }
  function focusById(id){
    const n=nodes.find(x=>x.id===id); if(!n) return;
    select(n);
    view.ox=W/2-n.x*view.scale; view.oy=H/2-n.y*view.scale;
  }
  function focusByLabel(q){
    if(!q) return;
    const low=q.toLowerCase();
    const n=visNodes().find(x=>x.label.toLowerCase().includes(low));
    if(n) focusById(n.id);
  }

  function onDown(ev){
    const p=pos(ev); downPos=p; moved=false;
    const n=pickNode(toWorld(p.x,p.y));
    if(n){ drag=n; n.fixed=true; alpha=Math.max(alpha,0.5); canvas.style.cursor='grabbing'; }
    else { panStart={x:p.x,y:p.y,ox:view.ox,oy:view.oy}; canvas.style.cursor='grabbing'; }
  }
  function onMove(ev){
    const p=pos(ev);
    if(downPos && (Math.abs(p.x-downPos.x)>4||Math.abs(p.y-downPos.y)>4)) moved=true;
    if(drag){
      const w=toWorld(p.x,p.y); drag.x=w.x; drag.y=w.y; alpha=Math.max(alpha,0.3);
    } else if(panStart){
      view.ox=panStart.ox+(p.x-panStart.x); view.oy=panStart.oy+(p.y-panStart.y);
    } else {
      const w=toWorld(p.x,p.y);
      const n=pickNode(w);
      if(n){
        canvas.style.cursor='pointer';
        showTooltip(`<b>${esc(n.label)}</b><span class="gt-type">${esc(TYPE_LABELS[n.type]||n.type)}</span><span class="gt-deg">${n.degree} connection${n.degree===1?'':'s'}</span>`,p);
      } else {
        const e=pickEdge(w);
        if(e){ canvas.style.cursor='pointer'; showTooltip(`<b>${esc(e.s.label)} → ${esc(e.t.label)}</b><span class="gt-type">${esc(e.label||'related')}</span>`,p); }
        else { canvas.style.cursor='grab'; hideTooltip(); }
      }
    }
  }
  function onUp(ev){
    const p=pos(ev);
    if(drag){ drag.fixed=false; drag=null; }
    else if(!moved){
      const n=pickNode(toWorld(p.x,p.y));
      select(n||null);
    }
    panStart=null; downPos=null; moved=false;
    canvas.style.cursor='grab';
  }
  function onWheel(ev){
    ev.preventDefault();
    const p=pos(ev), before=toWorld(p.x,p.y);
    view.scale=Math.max(0.15,Math.min(3.2,view.scale*(ev.deltaY<0?1.12:0.89)));
    view.ox=p.x-before.x*view.scale; view.oy=p.y-before.y*view.scale;
  }
  canvas.addEventListener('mousedown',onDown);
  window.addEventListener('mousemove',onMove);
  window.addEventListener('mouseup',onUp);
  canvas.addEventListener('wheel',onWheel,{passive:false});
  canvas.addEventListener('mouseleave',hideTooltip);
  const ro=new ResizeObserver(()=>{ resize(); alpha=Math.max(alpha,0.2); });
  ro.observe(host);

  graphCleanup=()=>{
    window.removeEventListener('mousemove',onMove);
    window.removeEventListener('mouseup',onUp);
    ro.disconnect();
    hideTooltip();
  };

  // ---- toolbar control surface (filters / search / fit) ----
  function setHidden(type,hide){
    if(hide) hiddenTypes.add(type); else hiddenTypes.delete(type);
    if(hide && selected && selected.type===type) select(null);
    updateStats();
  }
  function updateStats(){
    const counts={};
    nodes.forEach(n=>{ counts[n.type]=(counts[n.type]||0)+1; });
    const parts=Object.keys(counts).sort().map(t=>`${counts[t]} ${(TYPE_LABELS[t]||t).toLowerCase()}${counts[t]===1?'':'s'}`);
    const stats=$('#graphStats');
    if(stats) stats.textContent=`${nodes.length} entities · ${edges.length} relations`+(parts.length?' · '+parts.join(' · '):'');
  }
  updateStats();

  return {setHidden, focusByLabel, focusById, fit};
}

/* ---------------- knowledge graph: details side panel ---------------- */
function renderGraphPanel(node, edges){
  const panel=$('#graphPanel'); if(!panel) return;
  if(!node){ panel.innerHTML='<div class="gp-empty muted">Click a node to see its details, relations and where each fact came from.</div>'; return; }
  const raw=node.raw||{};
  const mentions=raw.mentions||[];
  const rels=(edges||[]).filter(e=>e.s.id===node.id||e.t.id===node.id);
  const col=NODE_COLORS[node.type]||'#8b94a7';

  let html=`<div class="gp-head">
    <span class="gp-badge" style="background:${col}22;color:${col};border-color:${col}55">${esc(TYPE_LABELS[node.type]||node.type)}</span>
    <h4>${esc(node.label)}</h4>
    <div class="muted">${node.degree} connection${node.degree===1?'':'s'}</div>
  </div>`;

  html+='<div class="gp-section"><h5>Relations</h5>';
  if(!rels.length){
    html+='<div class="muted">No recorded relations yet.</div>';
  } else {
    html+='<div class="gp-rels">'+rels.map((e,i)=>{
      const outgoing=e.s.id===node.id;
      const other=outgoing?e.t:e.s;
      const evid=(e.raw&&e.raw.evidence)||[];
      return `<div class="gp-rel" data-jump="${esc(other.id)}">
        <div class="gp-rel-row">
          <span class="gp-arrow">${outgoing?'→':'←'}</span>
          <span class="gp-rel-label">${esc(e.label||'related')}</span>
          <span class="gp-rel-other">${esc(other.label)}</span>
          ${evid.length?`<button type="button" class="gp-evid-btn" data-evid="gr${i}" title="Show evidence">🔎 ${evid.length}</button>`:''}
        </div>
        ${evid.length?`<div class="gp-evid hidden" id="gr${i}">${evid.map(ev=>
          `<div class="gp-quote">"${esc(ev.text)}"<span class="gp-meta">${SOURCE_LABELS[ev.source]||esc(ev.source||'')} · ${esc(ev.ts||'')}</span></div>`
        ).join('')}</div>`:''}
      </div>`;
    }).join('')+'</div>';
  }
  html+='</div>';

  html+='<div class="gp-section"><h5>Mentioned in</h5>';
  if(!mentions.length){
    html+='<div class="muted">No recorded mentions for this entity yet.</div>';
  } else {
    html+='<div class="gp-mentions">'+mentions.slice().reverse().map(m=>
      `<div class="gp-quote">"${esc(m.text)}"<span class="gp-meta">${SOURCE_LABELS[m.source]||esc(m.source||'')} · ${esc(m.ts||'')}</span></div>`
    ).join('')+'</div>';
  }
  html+='</div>';

  panel.innerHTML=html;
  panel.querySelectorAll('.gp-rel').forEach(row=>{
    row.addEventListener('click',ev=>{
      if(ev.target.closest('.gp-evid-btn')) return;
      if(graphApi) graphApi.focusById(row.dataset.jump);
    });
  });
  panel.querySelectorAll('.gp-evid-btn').forEach(btn=>{
    btn.addEventListener('click',ev=>{
      ev.stopPropagation();
      const box=document.getElementById(btn.dataset.evid);
      if(box) box.classList.toggle('hidden');
    });
  });
}

/* ---------------- knowledge graph: toolbar bindings (bound once) ---------------- */
$('#graphSearch').addEventListener('input',e=>{ if(graphApi) graphApi.focusByLabel(e.target.value.trim()); });
$('#graphFit').onclick=()=>{ if(graphApi) graphApi.fit(); };
$$('#graphLegend .lg-chip').forEach(chip=>{
  chip.onclick=()=>{
    chip.classList.toggle('active');
    const hide=!chip.classList.contains('active');
    chip.dataset.type.split(',').forEach(t=>{ if(graphApi) graphApi.setHidden(t,hide); });
  };
});

/* ---------------- voice call ---------------- */
let recog=null, recording=false, transcript=[], curRole='Lawyer';
$$('.role').forEach(b=>b.onclick=()=>{
  $$('.role').forEach(x=>x.classList.remove('active'));b.classList.add('active');curRole=b.dataset.role;
});
function initRecog(){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR) return null;
  const r=new SR(); r.continuous=true; r.interimResults=true; r.lang='en-US';
  let finalText='';
  r.onresult=ev=>{
    let interim='';
    for(let i=ev.resultIndex;i<ev.results.length;i++){
      const tr=ev.results[i][0].transcript;
      if(ev.results[i].isFinal){ pushTranscript(curRole,tr.trim()); }
      else interim+=tr;
    }
    renderTranscript(interim);
  };
  r.onend=()=>{ if(recording) r.start(); };
  return r;
}
function pushTranscript(role,text){ if(text) transcript.push({role,text}); renderTranscript(''); }
function renderTranscript(interim){
  const el=$('#liveTranscript');
  el.innerHTML=transcript.map(t=>`<div><b class="${t.role.toLowerCase()}">${t.role}:</b> ${esc(t.text)}</div>`).join('')
    + (interim?`<div style="opacity:.5"><b>${curRole}:</b> ${esc(interim)}</div>`:'');
  el.scrollTop=el.scrollHeight;
}
$('#startCall').onclick=()=>{
  if(activeClient==='general'){ $('#callStatus').innerHTML='⚠ Please select a client first (left sidebar).'; return; }
  recog=initRecog();
  transcript=[]; renderTranscript('');
  $('#callResult').innerHTML='<div class="muted">Recording… speak as Lawyer / Client. End the call to generate the summary.</div>';
  if(recog){ recording=true; recog.start();
    $('#callStatus').innerHTML='<span class="recording">● Recording</span> — call with '+esc(activeClientName);
  } else {
    $('#callStatus').innerHTML='⚠ Browser speech recognition unavailable. Use Chrome/Edge. You can still type the transcript manually below.';
    $('#liveTranscript').innerHTML='<div contenteditable="true" id="manualT" style="min-height:160px;outline:none" data-ph="Type the call here…"></div>';
  }
  $('#startCall').disabled=true; $('#endCall').disabled=false;
};
$('#endCall').onclick=async()=>{
  recording=false; if(recog) try{recog.stop()}catch(e){}
  $('#startCall').disabled=false; $('#endCall').disabled=true;
  $('#callStatus').textContent='Processing call…';
  let text='';
  if($('#manualT')) text=$('#manualT').innerText;
  else text=transcript.map(t=>`${t.role}: ${t.text}`).join('\n');
  if(!text.trim()){ $('#callStatus').textContent='No speech captured.'; return; }
  $('#callResult').innerHTML='<div class="typing"><i></i><i></i><i></i></div>';
  const r=await api.post('/api/call',{client_id:activeClient,transcript:text});
  $('#callStatus').textContent='Call complete — memory & graph updated.';
  let html=`<div class="ai-block"><h5>📝 Meeting summary</h5><div>${esc(r.summary)}</div>`;
  html+=`<h5>✅ Action items</h5>`;
  html+= r.action_items&&r.action_items.length?`<ul class="ai-list">${r.action_items.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>`:'<div class="muted">None extracted.</div>';
  if(r.contradictions&&r.contradictions.length){
    html+=`<div class="contradiction-card"><b>⚠ Contradiction vs earlier statements</b><br>${esc(r.contradictions[0].reason)}</div>`;
  }
  html+=`<h5>🧠 Memory</h5><div class="muted">Transcript stored, client knowledge graph updated.</div></div>`;
  $('#callResult').innerHTML=html;
  loadClients();
};

/* ---------------- LIVE CALL (real-time → memory + graph + auto-client) ---------- */
let liveRecog=null, liveOn=false, liveRole='Lawyer';
let liveTranscript=[], livePending=[], liveClientId=null, liveCommitted=0, liveBusy=false;

function liveInit(){
  // bind once; reflect current selected client as the initial call target
  if(!liveInit._bound){
    liveInit._bound=true;
    $$('.lrole').forEach(b=>b.onclick=()=>{ $$('.lrole').forEach(x=>x.classList.remove('active')); b.classList.add('active'); liveRole=b.dataset.role; });
    $('#liveStart').onclick=liveStart;
    $('#liveEnd').onclick=liveEnd;
    $('#liveOpenGraph').onclick=()=>{ $$('.tab').forEach(x=>x.classList.remove('active')); $$('.view').forEach(x=>x.classList.remove('active')); document.querySelector('.tab[data-tab="graph"]').classList.add('active'); $('#view-graph').classList.add('active'); loadGraph(); };
  }
  if(!liveOn){
    liveClientId = activeClient!=='general' ? activeClient : null;
    $('#liveClientName').textContent = liveClientId ? activeClientName : 'Not identified yet — say e.g. “This is Ravi Kumar”.';
  }
}
function liveRenderTranscript(interim){
  const el=$('#liveTranscript2');
  el.innerHTML=liveTranscript.map(t=>`<div><b class="${t.role.toLowerCase()}">${t.role}:</b> ${esc(t.text)}</div>`).join('')
    + (interim?`<div style="opacity:.5"><b>${liveRole}:</b> ${esc(interim)}</div>`:'');
  el.scrollTop=el.scrollHeight;
}
function liveStart(){
  liveInit();
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  liveTranscript=[]; livePending=[]; liveCommitted=0; liveRenderTranscript('');
  $('#liveResult').innerHTML=''; $('#liveContra').innerHTML='';
  $('#liveCommitted').textContent='0 statements captured';
  $('#liveGraphInfo').textContent='0 nodes / 0 links';
  if(!SR){
    $('#liveStatus').innerHTML='⚠ Speech recognition needs Chrome/Edge. You can still type lines below and press Enter.';
    $('#liveTranscript2').innerHTML='<input id="liveManual" placeholder="Type a spoken line + Enter…" style="width:100%;background:#0c0e12;border:1px solid #2a2f38;color:#ECECF1;border-radius:8px;padding:8px">';
    $('#liveManual').addEventListener('keydown',e=>{ if(e.key==='Enter'&&e.target.value.trim()){ liveHandle(liveRole,e.target.value.trim()); e.target.value=''; } });
  } else {
    liveRecog=new SR(); liveRecog.continuous=true; liveRecog.interimResults=true; liveRecog.lang='en-US';
    liveRecog.onresult=ev=>{ let interim=''; for(let i=ev.resultIndex;i<ev.results.length;i++){ const tr=ev.results[i][0].transcript; if(ev.results[i].isFinal) liveHandle(liveRole,tr.trim()); else interim+=tr; } liveRenderTranscript(interim); };
    liveRecog.onend=()=>{ if(liveOn) try{liveRecog.start()}catch(e){} };
    liveOn=true; try{liveRecog.start()}catch(e){}
    $('#liveStatus').innerHTML='<span class="recording">● Live</span> — transcribing and updating memory in real time.';
  }
  liveOn=true;
  $('#liveStart').disabled=true; $('#liveEnd').disabled=false;
}
async function liveHandle(role,text){
  if(!text) return;
  liveTranscript.push({role,text}); liveRenderTranscript('');
  try{
    const r=await api.post('/api/live',{client_id: liveClientId||'general', text, speaker: role, pending: liveClientId?[]:livePending});
    if(!liveClientId){
      if(r.client_id){                       // a client was just auto-created
        liveClientId=r.client_id; livePending=[];
        $('#liveClientName').innerHTML=`<b>${esc(r.client_name)}</b> <span class="muted">(auto-created)</span>`;
        $('#liveStatus').innerHTML=`<span class="recording">● Live</span> — client <b>${esc(r.client_name)}</b> created. Memory & graph updating.`;
        await loadClients(); selectClientSilent(r.client_id, r.client_name);
      } else {
        livePending.push(text);              // buffer until caller is named
      }
    }
    if(liveClientId){
      liveCommitted += (r.committed||0);
      $('#liveCommitted').textContent=`${liveCommitted} statement(s) captured`;
      if(r.graph) $('#liveGraphInfo').textContent=`${r.graph.nodes.length} nodes / ${r.graph.edges.length} links`;
      if(r.contradictions && r.contradictions.length){
        const c=r.contradictions[0];
        $('#liveContra').innerHTML=`<div class="contradiction-card"><b>⚠ Contradiction detected live</b><br>${esc(c.reason)}<br><span class="muted">Earlier: “${esc(c.prior_text)}”</span></div>`;
      }
    }
  }catch(e){ console.error('live error',e); }
}
function selectClientSilent(id,name){ activeClient=id; activeClientName=name; $('#activeClient').textContent='Client · '+name; }
async function liveEnd(){
  liveOn=false; if(liveRecog) try{liveRecog.stop()}catch(e){}
  $('#liveStart').disabled=false; $('#liveEnd').disabled=true;
  if(!liveClientId){ $('#liveStatus').textContent='Call ended. No client was identified — nothing was saved.'; return; }
  $('#liveStatus').textContent='Call ended — generating summary…';
  const full=liveTranscript.map(t=>`${t.role}: ${t.text}`).join('\n');
  $('#liveResult').innerHTML='<div class="typing"><i></i><i></i><i></i></div>';
  try{
    const r=await api.post('/api/call',{client_id:liveClientId,transcript:full});
    let html=`<div class="ai-block"><h5>📝 Meeting summary</h5><div>${esc(r.summary)}</div><h5>✅ Action items</h5>`;
    html+= r.action_items&&r.action_items.length?`<ul class="ai-list">${r.action_items.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>`:'<div class="muted">None extracted.</div>';
    html+=`</div>`;
    $('#liveResult').innerHTML=html;
    $('#liveStatus').textContent='Call complete — saved to this client\'s memory, graph and call history.';
  }catch(e){ $('#liveResult').innerHTML='<div class="muted">Summary failed: '+e+'</div>'; }
  loadClients();
}

/* ---------------- PHONE LINE (Twilio live transcription) ---------------- */
let phonePoll=null, phoneLastLen=-1, phoneSummaryShown=false;
function phoneStart(){
  if(!phonePoll){ phoneTick(); phonePoll=setInterval(phoneTick,1500); }
  if(!phoneStart._bound){
    phoneStart._bound=true;
    $('#phoneOpenGraph').onclick=()=>{ $$('.tab').forEach(x=>x.classList.remove('active')); $$('.view').forEach(x=>x.classList.remove('active')); document.querySelector('.tab[data-tab="graph"]').classList.add('active'); $('#view-graph').classList.add('active'); loadGraph(); };
  }
}
function phoneStop(){ if(phonePoll){ clearInterval(phonePoll); phonePoll=null; } }
async function phoneTick(){
  let s; try{ s=await api.get('/api/telephony/live'); }catch(e){ return; }
  if(!s.configured){
    $('#phoneStatus').innerHTML='⚠ Twilio not configured. Set TWILIO_NUMBER, TWILIO_CLIENT_NUMBER and PUBLIC_URL, then restart the server. See TWILIO_SETUP.md.';
  } else if(s.active){
    $('#phoneStatus').innerHTML='<span class="recording">● Call in progress</span> — transcribing both phones live.';
  } else if(s.ended){
    $('#phoneStatus').textContent='Call ended — memory, graph and summary updated.';
  } else {
    $('#phoneStatus').innerHTML='Ready. Call your Twilio number from your phone to begin.';
  }
  // transcript
  const tr=s.transcript||[];
  if(tr.length!==phoneLastLen){
    phoneLastLen=tr.length;
    $('#phoneTranscript').innerHTML = tr.length
      ? tr.map(u=>`<div><b class="${(u.speaker||'').toLowerCase()}">${esc(u.speaker)}:</b> ${esc(u.text)}</div>`).join('')
      : '<span class="muted">When the call connects, the conversation streams here in real time.</span>';
    $('#phoneTranscript').scrollTop=$('#phoneTranscript').scrollHeight;
  }
  $('#phoneClient').innerHTML = s.client_name ? `<b>${esc(s.client_name)}</b> <span class="muted">(auto-created)</span>` : 'Not identified yet…';
  $('#phoneGraph').textContent = (s.graph_nodes||0)+' nodes';
  if(s.contradictions && s.contradictions.length){
    const c=s.contradictions[s.contradictions.length-1];
    $('#phoneContra').innerHTML=`<div class="contradiction-card"><b>⚠ Contradiction detected live</b><br>${esc(c.reason)}<br><span class="muted">Earlier: “${esc(c.prior_text)}”</span></div>`;
  }
  if(s.ended && s.summary && !phoneSummaryShown){
    phoneSummaryShown=true;
    let html=`<div class="ai-block"><h5>📝 Meeting summary</h5><div>${esc(s.summary)}</div><h5>✅ Action items</h5>`;
    html+= s.action_items&&s.action_items.length?`<ul class="ai-list">${s.action_items.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>`:'<div class="muted">None extracted.</div>';
    html+='</div>';
    $('#phoneResult').innerHTML=html;
    loadClients();
  }
  if(s.active) phoneSummaryShown=false;
}

/* ---------------- dashboard ---------------- */
async function loadDash(){
  const d=await api.get('/api/dashboard');
  const solved=d.by_status.solved||0, unsolved=d.by_status.unsolved||0;
  $('#statRow').innerHTML=[
    ['Clients',d.total_clients],['Solved',solved],['Unsolved',unsolved],
    ['Calls',d.total_calls],['Statements',d.total_statements],
    ['Documents',d.total_documents],['Contradictions',d.contradictions]
  ].map(([l,n])=>`<div class="stat"><div class="num">${n}</div><div class="lab">${l}</div></div>`).join('');

  drawChart('statusChart','doughnut',d.by_status,'status');
  drawChart('typeChart','bar',d.by_type,'type');

  const tb=$('#caseTable').querySelector('tbody'); tb.innerHTML='';
  d.rows.forEach(r=>{
    const st=(r.case_status||'').replace(' ','-');
    tb.innerHTML+=`<tr><td>${esc(r.name)}</td><td>${esc(r.case_type)}</td>
      <td><span class="badge ${st}">${esc(r.case_status)}</span></td>
      <td>${r.statements}</td><td>${r.calls}</td><td>${r.graph_nodes}</td></tr>`;
  });
  $('#activityLog').innerHTML = d.activity.length? d.activity.map(a=>
    `<div class="act"><div>${esc(a.action)} — <b>${esc(a.client_name)}</b></div>
     <div class="muted">${esc(a.detail||'')}</div><div class="at">${esc(a.ts)}</div></div>`).join('')
    : '<div class="muted">No activity yet.</div>';
}
const PALETTE=['#c8a24a','#4f8cff','#10a37f','#a371f7','#e5685e','#e0a93b','#db61a2'];
function themeColors(){
  const css=getComputedStyle(document.documentElement);
  return {
    text:(css.getPropertyValue('--text')||'#eef1f7').trim(),
    muted:(css.getPropertyValue('--muted')||'#98a2bd').trim(),
    grid:(css.getPropertyValue('--border')||'#27304a').trim(),
    surface:(css.getPropertyValue('--surface')||'#151b2d').trim(),
  };
}
function drawChart(id,type,obj,_){
  const ctx=$('#'+id); const labels=Object.keys(obj), vals=Object.values(obj);
  const tc=themeColors();
  if(id==='statusChart'&&statusChart) statusChart.destroy();
  if(id==='typeChart'&&typeChart) typeChart.destroy();
  const cfg={type,data:{labels,datasets:[{data:vals,backgroundColor:PALETTE,borderColor:tc.surface,borderWidth:2}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{labels:{color:tc.text},display:type==='doughnut'}},
      scales:type==='bar'?{x:{ticks:{color:tc.muted},grid:{color:tc.grid}},y:{ticks:{color:tc.muted},grid:{color:tc.grid}}}:{}}};
  const c=new Chart(ctx,cfg);
  if(id==='statusChart') statusChart=c; else typeChart=c;
}

/* ---------------- modal ---------------- */
$('#newClientBtn').onclick=()=>$('#modal').classList.remove('hidden');
$('#m_cancel').onclick=()=>$('#modal').classList.add('hidden');
$('#m_save').onclick=async()=>{
  const name=$('#m_name').value.trim(); if(!name) return;
  const c=await api.post('/api/clients',{name,case_type:$('#m_type').value||'General',
    case_status:$('#m_status').value,summary:$('#m_summary').value,email:$('#m_email').value.trim()});
  $('#modal').classList.add('hidden');
  $('#m_name').value=$('#m_type').value=$('#m_summary').value=$('#m_email').value='';
  await loadClients(); selectClient(c.id,c.name);
};

/* ---------------- toasts ---------------- */
function toast(msg,type){
  const c=$('#toasts'); if(!c) return;
  const t=document.createElement('div');
  t.className='toast'+(type?' '+type:'');
  t.textContent=msg;
  c.appendChild(t);
  requestAnimationFrame(()=>t.classList.add('show'));
  setTimeout(()=>{ t.classList.remove('show'); setTimeout(()=>t.remove(),320); },3200);
}

/* ---------------- theme toggle ---------------- */
const THEME_KEY='lexora-theme';
function applyTheme(t){ document.documentElement.setAttribute('data-theme', t==='light'?'light':'dark'); }
(function(){ applyTheme(localStorage.getItem(THEME_KEY)||'dark'); })();
$('#themeToggle').onclick=()=>{
  const next=document.documentElement.getAttribute('data-theme')==='light'?'dark':'light';
  applyTheme(next); localStorage.setItem(THEME_KEY,next);
  const tab=$('.tab.active')?.dataset.tab;
  if(tab==='dash') loadDash();          // re-theme charts
  if(tab==='graph') loadGraph();        // re-theme graph stage
};

/* ---------------- client search ---------------- */
function applyClientFilter(){
  const q=($('#clientSearch')?.value||'').toLowerCase();
  $$('#clientList .client-item').forEach((it,i)=>{
    if(i===0){ it.style.display=''; return; }   // keep "General workspace" visible
    const nm=(it.querySelector('.nm')?.textContent||'').toLowerCase();
    it.style.display=nm.includes(q)?'':'none';
  });
}
$('#clientSearch').addEventListener('input',applyClientFilter);

/* ---------------- init ---------------- */
loadClients(); loadMessages();
