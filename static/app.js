/* Newsroom — Intelligence Dashboard JS */

let currentDate=null, currentSlug=null, reports=[], markers=[];
let map=null, markerLayer=null, coordsCache=null;
const TRUST_COLORS={high:'#22c55e',med:'#eab308',state:'#ef4444'};
const SLUG_EMOJI={world:'🌍',europe:'🇪🇺',mideast:'🕌',africa:'🌍',asia:'🌏',americas:'🌎','state-media':'📡',tech:'💻','tech-ai':'🤖','tech-security':'🔒','tech-crypto':'₿'};
const GROUP_ORDER=[
  {title:'NEWS',slugs:['world','europe','mideast','africa','asia','americas','state-media']},
  {title:'TECH',slugs:['tech','tech-ai','tech-security','tech-crypto']},
  {title:'ANALYSIS',slugs:[]},
];
const PERSPECTIVE_COLORS={western:'#3b82f6',russian:'#ef4444',chinese:'#f97316',israeli:'#14b8a6',arab:'#22c55e',iranian:'#a855f7',critical:'#06b6d4','global south':'#eab308'};

let countryIndex={};
let searchTimeout=null;
let debateCache={};

// === Toasts ===
function showToast(msg, type='info') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'toast' + (type === 'error' ? ' error' : '');
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
}

// === Safe Fetch ===
async function safeFetch(url, opts) {
  try {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  } catch (e) {
    showToast(`Failed to load: ${e.message}`, 'error');
    throw e;
  }
}

// === Country Index ===
function buildCountryIndex(){
  countryIndex={};
  markers.forEach(m=>{
    const key=m.countryKey||m.country.toLowerCase();
    if(!countryIndex[key])countryIndex[key]=[];
    countryIndex[key].push({slug:m.label,headline:m.headline,trust:m.trust,reportSlug:null});
  });
  reports.forEach(r=>{
    (r.countries||[]).forEach(c=>{
      if(!countryIndex[c])countryIndex[c]=[];
      const exists=countryIndex[c].some(e=>e.reportSlug===r.slug);
      if(!exists)countryIndex[c].push({reportSlug:r.slug,label:r.label,headline:'',trust:'high'});
    });
  });
  Object.values(countryIndex).forEach(entries=>{
    entries.forEach(e=>{
      if(!e.reportSlug){const match=reports.find(r=>r.label===e.slug);if(match)e.reportSlug=match.slug}
    });
  });
}

function findReportForCountry(countryKey){
  const entries=countryIndex[countryKey];if(!entries||!entries.length)return null;
  const regional=entries.find(e=>e.reportSlug&&e.reportSlug!=='world'&&!e.reportSlug.startsWith('tech'));
  if(regional)return regional.reportSlug;
  return entries[0].reportSlug||null;
}

// === Sidebar ===
function toggleSidebar(){
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('open');
}
function buildSidebar(){
  const nav=document.getElementById('reportNav');nav.innerHTML='';
  const grouped=GROUP_ORDER.map(g=>({...g,items:[]}));
  const otherGroup={title:'OTHER',items:[]};
  reports.forEach(r=>{
    let placed=false;
    for(const g of grouped){if(g.slugs.includes(r.slug)){g.items.push(r);placed=true;break}}
    if(!placed){
      if(r.isDebate||r.slug.includes('debate')||r.slug.includes('narrative'))grouped.find(g=>g.title==='ANALYSIS').items.push(r);
      else otherGroup.items.push(r);
    }
  });
  if(otherGroup.items.length)grouped.push(otherGroup);
  grouped.forEach(g=>{
    if(!g.items.length)return;
    const grp=document.createElement('div');grp.className='sidebar-group';
    grp.innerHTML=`<div class="sidebar-group-title">${g.title}</div>`;
    g.items.forEach(r=>{
      const item=document.createElement('div');
      item.className='sidebar-item'+(r.slug===currentSlug?' active':'');
      item.dataset.slug=r.slug;
      const emoji=SLUG_EMOJI[r.slug]||'📄';
      const shortLabel=r.label.replace(/^[^\w]*/,'').replace(/^(📰|💻|⚖️)\s*/,'');
      item.innerHTML=`<span class="emoji">${emoji}</span><span class="label">${esc(shortLabel)}</span><span class="read-time">${r.readTime}m</span>`;
      item.onclick=()=>{selectReport(r.slug);document.getElementById('sidebar').classList.remove('open');document.getElementById('sidebarOverlay').classList.remove('open')};
      grp.appendChild(item);
    });
    nav.appendChild(grp);
  });
}

// === Map ===
function initMap(){
  map=L.map('map',{center:[30,20],zoom:2,zoomControl:true,attributionControl:false});
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:12}).addTo(map);
  markerLayer=L.layerGroup().addTo(map);
}
function plotMarkers(mkrs){
  if(!markerLayer)return;markerLayer.clearLayers();
  document.getElementById('mapCount').textContent=mkrs.length;
  const byCountry={};
  mkrs.forEach(m=>{
    const key=m.countryKey||m.country.toLowerCase();
    if(!byCountry[key])byCountry[key]={lat:m.lat,lng:m.lng,country:m.country,countryKey:key,trust:m.trust,items:[]};
    byCountry[key].items.push(m);
    if(m.trust==='state')byCountry[key].trust='state';
    else if(m.trust==='med'&&byCountry[key].trust!=='state')byCountry[key].trust='med';
  });
  Object.values(byCountry).forEach(g=>{
    const color=TRUST_COLORS[g.trust]||TRUST_COLORS.high;
    const size=Math.min(24,14+g.items.length*2);
    const icon=L.divIcon({className:'',html:`<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><circle cx="${size/2}" cy="${size/2}" r="${size/2-1}" fill="${color}" fill-opacity="0.5" stroke="${color}" stroke-width="1.5"/><circle cx="${size/2}" cy="${size/2}" r="${Math.max(2,size/5)}" fill="#fff" fill-opacity="0.9"/></svg>`,iconSize:[size,size],iconAnchor:[size/2,size/2],popupAnchor:[0,-size/2]});
    const mk=L.marker([g.lat,g.lng],{icon});
    let popup=`<div class="marker-popup"><h4>${esc(g.country)}</h4>`;
    const seen=new Set();
    g.items.forEach(m=>{if(seen.has(m.headline))return;seen.add(m.headline);popup+=`<div class="popup-section">${esc(m.label)}</div><div class="popup-headline">${esc(m.headline)}</div>`});
    const bestSlug=findReportForCountry(g.countryKey);
    if(bestSlug){const bestReport=reports.find(r=>r.slug===bestSlug);popup+=`<div class="popup-link" data-slug="${bestSlug}" data-country="${g.countryKey}">→ Read in ${esc(bestReport?bestReport.label:bestSlug)}</div>`}
    popup+='</div>';
    mk.bindPopup(popup,{maxWidth:300});
    mk.on('popupopen',()=>{setTimeout(()=>{document.querySelectorAll('.popup-link[data-slug]').forEach(el=>{el.onclick=()=>{selectReport(el.dataset.slug);setTimeout(()=>scrollToCountryInArticle(el.dataset.country),300)}})},50)});
    mk.on('click',()=>{if(bestSlug&&bestSlug!==currentSlug){selectReport(bestSlug);setTimeout(()=>scrollToCountryInArticle(g.countryKey),300)}else scrollToCountryInArticle(g.countryKey)});
    mk.addTo(markerLayer);
  });
}

function panMapToCountry(key){
  if(!coordsCache)return;const c=coordsCache[key];if(!c)return;
  map.flyTo([c.lat,c.lng],5,{duration:.8});
  markerLayer.eachLayer(l=>{if(Math.abs(l.getLatLng().lat-c.lat)<1&&Math.abs(l.getLatLng().lng-c.lng)<1)l.openPopup()});
}

function scrollToCountryInArticle(key){
  const names=[key,key.replace(/-/g,' ')];
  const sections=document.querySelectorAll('.section-body');
  for(const section of sections){
    const text=section.textContent.toLowerCase();
    if(names.some(n=>text.includes(n.toLowerCase()))){
      const header=section.previousElementSibling;
      if(header&&header.classList.contains('collapsed'))header.click();
      const walker=document.createTreeWalker(section,NodeFilter.SHOW_TEXT);
      let targetNode=null;
      while(walker.nextNode()){if(names.some(n=>walker.currentNode.textContent.toLowerCase().includes(n.toLowerCase()))){targetNode=walker.currentNode.parentElement;break}}
      if(targetNode){setTimeout(()=>{targetNode.scrollIntoView({behavior:'smooth',block:'center'});targetNode.classList.add('country-mention-highlight');setTimeout(()=>targetNode.classList.remove('country-mention-highlight'),2500)},50)}
      else setTimeout(()=>section.scrollIntoView({behavior:'smooth',block:'center'}),50);
      return;
    }
  }
}

function highlightReportOnMap(r){
  if(!coordsCache||!r.countries||!r.countries.length)return;
  const points=[];
  r.countries.forEach(c=>{const cc=coordsCache[c];if(cc)points.push([cc.lat,cc.lng])});
  if(points.length>0)map.flyToBounds(L.latLngBounds(points).pad(0.3),{duration:.6,maxZoom:5});
}

// Map resize
(function(){
  const handle=document.getElementById('mapResize'),container=document.getElementById('mapContainer');
  let dragging=false,startY=0,startH=0;
  handle.addEventListener('mousedown',e=>{dragging=true;startY=e.clientY;startH=container.offsetHeight;e.preventDefault()});
  document.addEventListener('mousemove',e=>{if(!dragging)return;container.style.height=Math.max(100,Math.min(window.innerHeight*0.7,startH+(e.clientY-startY)))+'px';map.invalidateSize()});
  document.addEventListener('mouseup',()=>{dragging=false});
})();

// === Data Loading ===
async function loadDates(){
  try {
    const dates = await safeFetch('/api/dates');
    const picker=document.getElementById('datePicker');picker.innerHTML='';
    dates.forEach(d=>{const opt=document.createElement('option');opt.value=d;opt.textContent=d;picker.appendChild(opt)});
    safeFetch('/api/coords').then(c=>coordsCache=c).catch(()=>{});
    if(dates.length>0)selectDate(dates[0]);
    else document.getElementById('content').innerHTML='<div class="empty">No reports found. Run the intelligence briefing first.</div>';
  } catch(e) {
    document.getElementById('content').innerHTML='<div class="empty">Failed to load dates. Is the server running?</div>';
  }
}

async function selectDate(date){
  currentDate=date;
  document.getElementById('datePicker').value=date;
  showLoading(true);
  try {
    const data = await safeFetch(`/api/reports/${date}`);
    reports=data.reports||[];markers=data.markers||[];
    buildCountryIndex();plotMarkers(markers);buildSidebar();
    if(reports.length>0)selectReport(reports[0].slug);
    else{document.getElementById('content').innerHTML='<div class="empty">No reports for this date.</div>';document.getElementById('tocList').innerHTML=''}
  } catch(e) {
    document.getElementById('content').innerHTML='<div class="empty">Failed to load reports.</div>';
  } finally {
    showLoading(false);
  }
}

async function selectReport(slug){
  currentSlug=slug;
  document.querySelectorAll('.sidebar-item').forEach(i=>i.classList.toggle('active',i.dataset.slug===slug));
  const r=reports.find(x=>x.slug===slug);if(!r)return;

  let html='<div class="report-header">';
  html+=`<h1>${esc(r.label)}</h1><div class="report-meta">`;
  html+=`<span class="read-time">📖 ${r.readTime} min read</span>`;
  if(r.hasLog)html+=`<a class="log-btn" href="/report/${currentDate}/${slug}/log" target="_blank">📋 Editorial log</a>`;
  html+='</div>';
  if(r.countries&&r.countries.length>0){
    html+='<div class="country-tags">';
    r.countries.forEach(c=>{html+=`<span class="country-tag" data-country="${esc(c)}" onclick="panMapToCountry('${esc(c)}')">${esc(c.replace(/-/g,' '))}</span>`});
    html+='</div>';
  }
  html+='</div>';
  if(r.isDebate){try{const debates=await loadDebateData(currentDate);if(debates[slug])html+=renderDebateViz(debates[slug])}catch(e){}}
  html+=`<div class="report">${r.html}</div>`;

  document.getElementById('content').innerHTML=html;
  document.getElementById('contentScroll').scrollTop=0;
  processCollapsibleSections();buildTOC();highlightReportOnMap(r);
}

function showLoading(show) {
  let overlay = document.querySelector('.loading-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.innerHTML = '<div class="spinner"></div>';
    document.querySelector('.content-scroll').style.position = 'relative';
    document.querySelector('.content-scroll').appendChild(overlay);
  }
  overlay.classList.toggle('visible', show);
}

function processCollapsibleSections(){
  const report=document.querySelector('.report');if(!report)return;
  report.querySelectorAll('h2').forEach((h2,i)=>{
    h2.id='section-'+i;
    const wrapper=document.createElement('div');wrapper.className='section-header';
    wrapper.innerHTML='<span class="section-chevron">▼</span>';
    h2.parentNode.insertBefore(wrapper,h2);wrapper.appendChild(h2);
    const body=document.createElement('div');body.className='section-body';body.id='body-'+i;
    wrapper.parentNode.insertBefore(body,wrapper.nextSibling);
    let next=body.nextSibling;
    while(next&&!(next.classList&&next.classList.contains('section-header'))){const move=next;next=next.nextSibling;body.appendChild(move)}
    body.style.maxHeight=body.scrollHeight+'px';
    wrapper.onclick=()=>{const collapsed=wrapper.classList.toggle('collapsed');body.classList.toggle('collapsed',collapsed);if(!collapsed)body.style.maxHeight=body.scrollHeight+'px'};
  });
}

function buildTOC(){
  const tocList=document.getElementById('tocList');
  const h2s=document.querySelectorAll('.report h2');
  const tocSection=document.getElementById('sidebarToc');
  tocList.innerHTML='';
  if(h2s.length===0){tocSection.style.display='none';return}
  tocSection.style.display='block';
  h2s.forEach((h2,i)=>{
    const a=document.createElement('a');a.className='toc-link';a.href='#section-'+i;
    a.textContent=h2.textContent.replace(/^[\d.]+\s*/,'').substring(0,45);
    a.onclick=e=>{e.preventDefault();h2.scrollIntoView({behavior:'smooth',block:'start'})};
    tocList.appendChild(a);
  });
}

// Progress + TOC highlight
document.getElementById('contentScroll').addEventListener('scroll',function(){
  const scrollEl=this;
  const pct=Math.min(100,Math.max(0,(scrollEl.scrollTop/(scrollEl.scrollHeight-scrollEl.clientHeight))*100));
  document.getElementById('progressBar').style.width=pct+'%';
  const h2s=document.querySelectorAll('.report h2');
  const links=document.querySelectorAll('.toc-link');
  let activeIdx=0;
  h2s.forEach((h2,i)=>{if(h2.getBoundingClientRect().top<200)activeIdx=i});
  links.forEach((l,i)=>l.classList.toggle('active',i===activeIdx));
});

// Keyboard
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT'||e.target.tagName==='TEXTAREA')return;
  if(e.key==='ArrowLeft'){navReport(-1);e.preventDefault()}
  if(e.key==='ArrowRight'){navReport(1);e.preventDefault()}
  if(e.key==='/'&&!e.ctrlKey&&!e.metaKey){e.preventDefault();document.getElementById('searchInput').focus()}
});
function navReport(dir){
  if(!reports.length)return;
  const idx=reports.findIndex(r=>r.slug===currentSlug);
  const next=idx+dir;
  if(next>=0&&next<reports.length)selectReport(reports[next].slug);
}

// === Search ===
function initSearch() {
  const input = document.getElementById('searchInput');
  const results = document.getElementById('searchResults');

  input.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    const q = input.value.trim();
    if (q.length < 2) { results.classList.remove('visible'); return; }
    results.innerHTML = '<div class="search-loading">Searching…</div>';
    results.classList.add('visible');
    searchTimeout = setTimeout(() => doSearch(q), 300);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') { input.blur(); results.classList.remove('visible'); }
  });

  // Close on outside click
  document.addEventListener('click', e => {
    if (!e.target.closest('.search-box')) results.classList.remove('visible');
  });
}

async function doSearch(q) {
  const results = document.getElementById('searchResults');
  try {
    const data = await safeFetch(`/api/search?q=${encodeURIComponent(q)}`);
    if (!data.results || data.results.length === 0) {
      results.innerHTML = '<div class="search-empty">No results found</div>';
      return;
    }
    results.innerHTML = data.results.map(r => {
      const snippet = (r.snippet || '').substring(0, 200);
      return `<div class="search-result" onclick="navigateToResult('${r.date}','${r.slug}')">
        <span class="sr-date">${r.date}</span><span class="sr-slug">${r.slug}</span>
        <div class="sr-snippet">${snippet}</div>
      </div>`;
    }).join('');
  } catch(e) {
    results.innerHTML = '<div class="search-empty">Search failed</div>';
  }
}

function navigateToResult(date, slug) {
  document.getElementById('searchResults').classList.remove('visible');
  document.getElementById('searchInput').value = '';
  if (date !== currentDate) {
    // Need to load a different date first
    currentDate = date;
    document.getElementById('datePicker').value = date;
    selectDate(date).then(() => selectReport(slug));
  } else {
    selectReport(slug);
  }
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

// === Debate Visualizations ===
async function loadDebateData(date){if(debateCache[date])return debateCache[date];const data=await safeFetch(`/api/debate-data/${date}`);debateCache[date]=data;return data}

function renderDebateViz(d){
  const{scores,divergence,agreement,truth,perspectives,colors}=d;let h='';
  if(Object.keys(scores).length>0)h+=`<div class="debate-viz"><h3>📊 Narrative Spectrum</h3>${buildSpectrumBar(scores,colors)}</div>`;
  if(Object.keys(divergence||{}).length>0)h+=`<div class="debate-viz"><h3>🕸 Divergence Radar</h3>${buildRadarChart(divergence,colors)}</div>`;
  if(Object.keys(agreement||{}).length>0)h+=`<div class="debate-viz"><h3>🔥 Agreement Heatmap</h3>${buildHeatmap(agreement,perspectives,colors)}</div>`;
  if(Object.keys(truth||{}).length>0)h+=`<div class="debate-viz"><h3>⚖️ Truth Landscape</h3>${buildTruthGauge(truth)}</div>`;
  return h;
}
function buildSpectrumBar(scores,colors){
  let h='<div class="spectrum-bar">';
  Object.entries(scores).sort((a,b)=>b[1]-a[1]).forEach(([p,s])=>{h+=`<div class="spectrum-segment" style="flex:${s};background:${colors[p]||'#888'}">${s}<div class="spectrum-tooltip">${p}: ${s}/100</div></div>`});
  h+='</div><div class="spectrum-legend">';
  Object.entries(scores).sort((a,b)=>b[1]-a[1]).forEach(([p,s])=>{h+=`<span class="legend-item"><span class="legend-dot" style="background:${colors[p]||'#888'}"></span>${p} ${s}</span>`});
  return h+'</div>';
}
function buildHeatmap(agreement,perspectives,colors){
  const n=perspectives.length;const icons={agree:'🟢',partial:'🟡',conflict:'🔴'};const labels={agree:'Agree',partial:'Partial',conflict:'Conflict'};
  let h=`<div class="heatmap-grid" style="grid-template-columns:80px repeat(${n},36px)"><div></div>`;
  perspectives.forEach(p=>{h+=`<div class="heatmap-header" style="color:${colors[p]||'#888'}">${p.slice(0,4)}</div>`});
  perspectives.forEach((row,i)=>{
    h+=`<div class="heatmap-row-label" style="color:${colors[row]||'#888'}">${row}</div>`;
    perspectives.forEach((col,j)=>{
      if(i===j)h+='<div class="heatmap-cell self">—</div>';
      else{const v=agreement[`${row}-${col}`]||agreement[`${col}-${row}`]||'partial';h+=`<div class="heatmap-cell ${v}">${icons[v]}<div class="heatmap-tooltip">${row} ↔ ${col}: ${labels[v]}</div></div>`}
    });
  });
  return h+'</div>';
}
function buildTruthGauge(truth){
  const pos=truth.position||50;
  return`<div class="truth-gauge"><div class="truth-gauge-fill"></div><div class="truth-gauge-marker" style="left:calc(${pos}% - 14px)">${pos}</div></div><div class="truth-labels"><span>${truth.left_label||'Mainstream'}</span><span>${truth.right_label||'Counter-narrative'}</span></div>`;
}
function buildRadarChart(divergence,colors){
  const dims=Object.keys(divergence);if(!dims.length)return'';
  const cx=140,cy=140,r=110,n=dims.length;
  const perspectives=Object.keys(divergence[dims[0]]||{});
  let svg=`<svg viewBox="0 0 280 280">`;
  for(let ring=1;ring<=4;ring++){const rr=r*ring/4;let pts=dims.map((_,i)=>{const a=(Math.PI*2*i/n)-Math.PI/2;return`${cx+rr*Math.cos(a)},${cy+rr*Math.sin(a)}`}).join(' ');svg+=`<polygon points="${pts}" fill="none" stroke="var(--border)" stroke-width="0.5"/>`}
  dims.forEach((d,i)=>{const a=(Math.PI*2*i/n)-Math.PI/2;const x=cx+r*Math.cos(a),y=cy+r*Math.sin(a);svg+=`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--border)" stroke-width="0.5"/>`;const lx=cx+(r+20)*Math.cos(a),ly=cy+(r+20)*Math.sin(a);svg+=`<text x="${lx}" y="${ly}" class="radar-axis-label">${d}</text>`});
  perspectives.forEach(p=>{const c=colors[p]||'#888';let pts=dims.map((d,i)=>{const v=(divergence[d]?.[p]||0)/100;const a=(Math.PI*2*i/n)-Math.PI/2;return`${cx+r*v*Math.cos(a)},${cy+r*v*Math.sin(a)}`}).join(' ');svg+=`<polygon points="${pts}" class="radar-polygon" fill="${c}" stroke="${c}"/>`});
  return`<div class="radar-container">${svg}</svg></div>`;
}

// === Init ===
initMap();
initSearch();
loadDates();
