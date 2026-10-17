import './style.css';
import { GridStack } from 'gridstack';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import { createIcons, BookOpen, House, Files, Newspaper, ChartNoAxesCombined, CalendarDays, CloudUpload,
  History, Link, SlidersHorizontal, Monitor, LogOut, Search, Sparkles, ExternalLink, ArrowRight, Plus,
  Pencil, Trash2, X, Check, CheckCircle2, FileText, Mail, Video, File, GripVertical, RotateCcw, Save,
  ChevronLeft, ChevronRight, RefreshCw, Download, Filter, Upload, Clock, Copy, Info, Archive, Database,
  CircleHelp, NotebookPen, Settings2, Eye, ShieldCheck } from 'lucide';

const iconSet = {BookOpen, House, Files, Newspaper, ChartNoAxesCombined, CalendarDays, CloudUpload, History,
  Link, SlidersHorizontal, Monitor, LogOut, Search, Sparkles, ExternalLink, ArrowRight, Plus, Pencil, Trash2,
  X, Check, CheckCircle2, FileText, Mail, Video, File, GripVertical, RotateCcw, Save, ChevronLeft, ChevronRight,
  RefreshCw, Download, Filter, Upload, Clock, Copy, Info, Archive, Database, CircleHelp, NotebookPen, Settings2, Eye, ShieldCheck};
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => '<i data-lucide="' + name + '"></i>';
const md = value => DOMPurify.sanitize(marked.parse(value || ''), {ALLOW_DATA_ATTR:false,
  FORBID_TAGS:['style','iframe','form','input','button','select','textarea'], FORBID_ATTR:['style']});
const state = {boot:null, csrf:'', grid:null, editing:false, route:'overview', filter:'', kind:'', offset:0,
  month:new Date().getMonth(), year:new Date().getFullYear(), selectedDay:'', uploadQueue:[], preview:null,
  selectedConversations:new Set(), sourceRows:[], digestRows:[], timer:null};

function icons(){ createIcons({icons:iconSet, attrs:{'aria-hidden':'true'}}); }
function toast(message, error=false){
  const el=$('#toast'); el.textContent=message; el.className=error?'error':''; el.hidden=false;
  clearTimeout(state.timer); state.timer=setTimeout(()=>el.hidden=true, error?7000:4000);
}
async function api(path, options={}){
  const headers = {'X-CSRF-Token':state.csrf, ...options.headers};
  if (options.body && !(options.body instanceof FormData)){ headers['Content-Type']='application/json'; options.body=JSON.stringify(options.body); }
  const response=await fetch('/api'+path, {...options, headers, credentials:'same-origin'});
  if(response.status===401){ $('#login-screen').hidden=false; $('#login-password').focus(); throw new Error('Sign in to your workspace.'); }
  const value=await response.json().catch(()=>({}));
  if(!response.ok){ const detail=Array.isArray(value.detail)?value.detail.map(x=>x.msg).join('; '):value.detail; throw new Error(detail || 'The request could not be completed.'); }
  return value;
}
const post=(path,body={})=>api(path,{method:'POST',body});
const money=(value,currency='USD')=>value==null?'—':new Intl.NumberFormat(undefined,{style:'currency',currency,maximumFractionDigits:2}).format(value);
const number=value=>new Intl.NumberFormat().format(value);
function dateLabel(value,options={dateStyle:'medium'}){
  if(!value)return 'Date unknown';
  const d=new Date(value.length===10?value+'T12:00:00Z':value);
  return isNaN(d)?'Date unknown':new Intl.DateTimeFormat(undefined,{...options,timeZone:state.boot?.preferences.timezone}).format(d);
}
function localDay(value=new Date()){
  return new Intl.DateTimeFormat('en-CA',{timeZone:state.boot?.preferences.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
}
const badge=(label,cls='')=>'<span class="badge '+cls+'">'+esc(label)+'</span>';
const button=(action,label,iconName='',id='',classes='')=>'<button class="button '+classes+'" data-action="'+action+'" data-id="'+esc(id)+'">'+(iconName?icon(iconName):'')+esc(label)+'</button>';
function empty(title,description,action='upload',label='Add your first source',iconName='book-open'){
  return '<div class="empty-state">'+icon(iconName)+'<h3>'+esc(title)+'</h3><p>'+esc(description)+'</p>'+(action?button(action,label,'plus'):'')+'</div>';
}
function openModal(title,html){
  $('#modal-title').textContent=title; $('#modal-content').innerHTML=html;
  if(!$('#modal').open)$('#modal').showModal(); icons();
}
function closeModal(){ $('#modal').close(); }
function formData(form){return Object.fromEntries(new FormData(form));}
function tags(value){return value.split(',').map(x=>x.trim()).filter(Boolean);}
function field(label,name,value='',type='text',extra=''){
  return '<label>'+esc(label)+'<input name="'+name+'" type="'+type+'" value="'+esc(value)+'" '+extra+'></label>';
}
function selectField(label,name,value,options){
  return '<label>'+esc(label)+'<select aria-label="'+esc(label)+'" name="'+name+'">'+options.map(([v,t])=>'<option value="'+esc(v)+'" '+(v===value?'selected':'')+'>'+esc(t)+'</option>').join('')+'</select></label>';
}
function formActions(label='Save changes'){return '<div class="form-actions">'+button('close-modal','Cancel')+'<button class="button primary" type="submit">'+icon('check')+label+'</button></div>';}
async function refresh(render=true){
  state.boot=await api('/bootstrap'); state.csrf=state.boot.csrf;
  $('#login-screen').hidden=true;
  $('#dot-link').href=state.boot.preferences.dot_url;
  $('#workspace-status').textContent='Database online · v'+state.boot.version;
  $('#demo-banner').hidden=!state.boot.demo;
  $('#demo-banner').innerHTML='<span><strong>DEMO DATA</strong> · Sample research and prices. Clear the sample workspace before adding personal data.</span>'+button('clear-demo','Clear sample data','','','small');
  if(render)await renderRoute();
}
function header(){
  const route=location.hash.slice(1).split('/')[0]||'overview'; state.route=route;
  const titles={overview:'Your research, in focus.',library:'Your source library.',digests:'Your daily perspective.',
    portfolio:'Portfolio & watchlist.',calendar:'Make time for the details.',uploads:'Bring your research together.',
    activity:'Every action, accounted for.',connections:'Your sources, connected.',settings:'Your research, your way.',document:'From your library.'};
  $('#page-title').textContent=titles[route]||titles.overview;
  $('#page-subtitle').textContent=dateLabel(new Date().toISOString(),{weekday:'long',year:'numeric',month:'long',day:'numeric'});
  $$('[data-nav]').forEach(el=>el.classList.toggle('active',el.dataset.nav===route || (route==='document'&&el.dataset.nav==='library')));
}
async function renderRoute(){
  if(!state.boot)return;
  if(state.grid){state.grid.destroy(false);state.grid=null;} state.editing=false;
  header();
  const renderers={overview:renderOverview,library:renderLibrary,digests:renderDigests,portfolio:renderPortfolio,
    calendar:renderCalendar,uploads:renderUploads,activity:renderActivity,connections:renderConnections,settings:renderSettings,
    document:()=>renderDocument(location.hash.split('/')[1])};
  await (renderers[state.route]||renderOverview)(); icons();
}
function dropzone(){return '<button class="dropzone" data-action="upload">'+icon('cloud-upload')+'<span><strong>Drop files to add to your library</strong><small>PDF · Email · Video transcripts · Markdown · ChatGPT ZIP</small></span></button>';}
function card(id,title,content,actions=''){
  return '<div class="grid-stack-item" gs-id="'+id+'"><section class="grid-stack-item-content '+(id==='upload'?'upload-card':'')+'">'
    +(title?'<div class="card-head card-drag"><h2>'+esc(title)+'</h2><div class="head-actions"><span class="layout-handle">'+icon('grip-vertical')+'</span>'+actions+'</div></div>':'<span class="upload-grip card-drag layout-handle" aria-label="Move upload card">'+icon('grip-vertical')+'</span>')
    +'<div class="card-body">'+content+'</div></section></div>';
}
function digestCard(){
  const d=state.boot.digest;
  if(!d)return empty('A fresh perspective starts here','Add a source, then ask your dot to publish a cited digest—or create a local excerpt digest.','generate-digest','Create excerpt digest','newspaper');
  const stamp=new Date(d.day+'T12:00:00Z');
  return '<div class="digest-meta"><div class="date-chip"><span>'+stamp.getUTCDate()+'</span><span>'+stamp.toLocaleDateString('en',{month:'short',timeZone:'UTC'}).toUpperCase()+'</span></div><div><h3>'+esc(d.title)+'</h3><span class="small-text muted">'+esc(d.method)+' · '+d.document_ids.length+' saved sources</span></div></div><div class="digest-preview">'+md(d.content)+'</div><div class="digest-footer">Every summary links back to its saved sources.</div>';
}
function sparkline(history,currency){
  const points=history.filter(x=>x.currency===currency).slice(-30);
  if(points.length<2)return '<div class="history-empty">Value history builds as quotes are refreshed.</div>';
  const values=points.map(x=>x.value),lo=Math.min(...values),hi=Math.max(...values);
  const coords=values.map((value,i)=>(i/(values.length-1)*300).toFixed(2)+','+(42-(value-lo)/(hi-lo||1)*36).toFixed(2)).join(' ');
  return '<svg class="sparkline" viewBox="0 0 300 46" role="img" aria-label="Saved portfolio value snapshots"><polyline fill="none" stroke="#3a8a72" stroke-width="1.7" points="'+coords+'"/></svg>';
}
function stockRows(stocks,compact=true){
  if(!stocks.length)return '<tr><td colspan="5" class="empty-state">Add stocks to start your watchlist.</td></tr>';
  return stocks.map(s=>{
    const change=s.last_price!=null&&s.previous_price?((s.last_price/s.previous_price-1)*100):null;
    return '<tr><td><span class="stock-symbol">'+esc(s.symbol)+'</span>'+(!compact?'<div class="doc-subtitle">'+esc(s.exchange)+' · '+esc(s.category)+'</div>':'')+'</td>'
      +(!compact?'<td>'+esc(s.currency)+'</td><td class="numeric">'+number(s.shares)+'</td><td class="numeric">'+money(s.average_cost,s.currency)+'</td>':'')
      +'<td class="numeric">'+money(s.last_price,s.currency)+'</td><td class="numeric '+(change==null?'muted':change>=0?'positive':'negative')+'">'+(change==null?'—':(change>=0?'+':'')+change.toFixed(2)+'%')+'</td>'
      +(!compact?'<td><span class="small-text">'+esc(s.provider||'No quote')+'</span><div class="doc-subtitle">'+esc(s.price_at?dateLabel(s.price_at):'Awaiting price')+'</div>'+(s.quote_error?'<span class="small-text danger-text">'+esc(s.quote_error)+'</span>':'')+'</td><td class="align-right"><button class="icon-button" data-action="edit-stock" data-id="'+s.id+'" aria-label="Edit '+esc(s.symbol)+'">'+icon('pencil')+'</button><button class="icon-button" data-action="manual-price" data-id="'+s.id+'" aria-label="Set price for '+esc(s.symbol)+'">'+icon('notebook-pen')+'</button><button class="icon-button" data-action="delete-stock" data-id="'+s.id+'" aria-label="Remove '+esc(s.symbol)+'">'+icon('trash-2')+'</button></td>':'')+'</tr>';
  }).join('');
}
function portfolioCard(){
  const p=state.boot.portfolio,currencies=Object.keys(p.totals),currency=currencies.includes('USD')?'USD':currencies[0]||'USD';
  const total=p.totals[currency],change=p.day_changes[currency];
  return '<div class="portfolio-heading-row"><div><div class="portfolio-value">'+money(total,currency)+'</div>'
    +'<div class="portfolio-change '+(change>=0?'positive':'negative')+'">'+(change==null?'':(change>=0?'+':'')+money(change,currency))+'</div></div><div class="portfolio-meta">'+(p.stocks.some(s=>s.demo)?'Sample prices':esc(currency)+' holdings · saved quotes')+'</div></div>'
    +(p.missing.length?'<p class="small-text muted">Valuation incomplete: '+esc(p.missing.join(', '))+' need prices.</p>':'')
    +(currencies.length>1?'<p class="small-text muted">Other currencies are shown separately in Portfolio.</p>':'')
    +sparkline(p.history,currency)
    +'<table class="data-table compact-table"><thead><tr><th>Ticker</th><th class="numeric">Price</th><th class="numeric">Change</th></tr></thead><tbody>'+stockRows(p.stocks.slice(0,4))+'</tbody></table>';
}
function calendarGrid(large=false){
  const first=new Date(state.year,state.month,1),days=new Date(state.year,state.month+1,0).getDate(),today=localDay();
  const datesWithTasks=new Set(state.boot.tasks.filter(t=>!t.done).map(t=>localDay(t.due_at)));
  let cells=['S','M','T','W','T','F','S'].map(d=>'<span class="calendar-weekday">'+d+'</span>').join('');
  cells+='<span></span>'.repeat(first.getDay());
  for(let day=1;day<=days;day++){
    const key=state.year+'-'+String(state.month+1).padStart(2,'0')+'-'+String(day).padStart(2,'0');
    cells+='<button class="calendar-day '+(key===today?'today ':'')+(key===state.selectedDay?'selected ':'')+(datesWithTasks.has(key)?'has-task':'')+'" data-action="select-day" data-id="'+key+'" aria-label="'+key+'">'+day+'</button>';
  }
  return '<div class="calendar-top"><strong>'+esc(first.toLocaleDateString(undefined,{month:'long',year:'numeric'}))+'</strong><span><button class="icon-button" data-action="prev-month" aria-label="Previous month">'+icon('chevron-left')+'</button><button class="icon-button" data-action="next-month" aria-label="Next month">'+icon('chevron-right')+'</button></span></div><div class="calendar-grid '+(large?'large':'')+'">'+cells+'</div>';
}
function taskRows(tasks,limit=5){
  if(!tasks.length)return '<div class="empty-state">No tasks scheduled. Make space for your next review.</div>';
  return tasks.slice(0,limit).map(t=>'<div class="task-row '+(t.done?'done':'')+'"><button class="task-check" data-action="toggle-task" data-id="'+t.id+'" aria-label="'+(t.done?'Reopen ':'Complete ')+esc(t.title)+'">'+(t.done?icon('check'):'')+'</button><span class="task-title" data-action="edit-task" data-id="'+t.id+'">'+esc(t.title)+'</span><time class="task-time">'+esc(dateLabel(t.due_at,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}))+'</time></div>').join('');
}
function activityRows(rows){
  if(!rows.length)return '<div class="empty-state">Your system and dot actions will appear here.</div>';
  return rows.map(a=>'<div class="activity-row"><time>'+esc(dateLabel(a.at,{hour:'2-digit',minute:'2-digit',hour12:false}))+'</time><div><span class="activity-title">'+esc(a.action)+'</span><br><span class="actor">'+esc(a.actor)+'</span></div></div>').join('');
}
const typeIcon=kind=>({email:'mail',transcript:'video',chatgpt:'sparkles',note:'notebook-pen',article:'newspaper'}[kind]||'file-text');
function libraryTable(items,compact=false){
  if(!items.length)return empty('Your library is ready','Drop a document, import old ChatGPT research, or connect a feed. Every source gets a searchable record and Markdown copy.');
  return '<div class="table-scroll"><table class="data-table '+(compact?'compact-table':'')+'"><thead><tr><th>Source / title</th>'+(compact?'':'<th>Type</th>')+'<th>Topics</th><th>Research date</th><th>Status</th></tr></thead><tbody>'+items.map(d=>'<tr><td><div class="doc-cell"><span class="doc-icon '+esc(d.kind)+'">'+icon(typeIcon(d.kind))+'</span><div><button class="doc-title" data-action="document" data-id="'+d.id+'">'+esc(d.title)+'</button><div class="doc-subtitle">'+esc(d.source_name)+'</div></div></div></td>'
      +(compact?'':'<td>'+badge(d.ai_generated?'AI research':d.kind,d.ai_generated?'ai':'neutral')+'</td>')
      +'<td>'+d.tags.slice(0,2).map(t=>badge(t)).join('')+d.tickers.slice(0,1).map(t=>badge(t,'green')).join('')+'</td><td class="small-text muted">'+esc(dateLabel(d.created_at,{month:'short',day:'numeric',year:'numeric'}))+'</td><td><span class="indexed">'+icon('check-circle-2')+'Indexed · MD</span></td></tr>').join('')+'</tbody></table></div>';
}
function renderOverview(){
  const s=state.boot.stats;
  $('#view').innerHTML='<div class="stats-row"><div class="stat">'+icon('link')+'<span><strong>'+number(s.sources)+'</strong>connected sources</span></div><div class="stat">'+icon('files')+'<span><strong>'+number(s.documents)+'</strong>library items</span></div><div class="stat">'+icon('file-text')+'<span><strong>'+number(s.new_today)+'</strong>new today</span></div><div class="stat">'+icon('check-circle-2')+'<span><strong>'+s.tasks+'</strong>tasks due</span></div><div class="layout-toolbar">'+button('edit-layout','Edit dashboard','sliders-horizontal','','small')+'</div></div><div class="grid-stack">'
    +card('digest','Daily digest',digestCard(),'<a class="link-button" href="#digests">Read full digest →</a>')
    +card('portfolio','Portfolio & watchlist',portfolioCard(),button('add-stock','Add','plus','','small')+'<a class="link-button" href="#portfolio">Manage</a>')
    +card('calendar','Calendar & tasks',calendarGrid()+'<div class="task-list">'+taskRows(state.boot.tasks.filter(t=>!t.done),2)+'</div>','<a class="link-button" href="#calendar">Open calendar →</a>')
    +card('library','Latest in your library','<div class="pills"><span class="pill active">All</span><a class="pill" href="#library">Email</a><a class="pill" href="#library">Articles</a><a class="pill" href="#library">Video</a><a class="pill" href="#library">Documents</a></div>'+libraryTable(state.boot.library.slice(0,4),true),'<a class="link-button" href="#library">View library →</a>')
    +card('activity','Recent activity',activityRows(state.boot.activity.slice(0,4)),'<a class="link-button" href="#activity">View log →</a>')
    +card('upload','',dropzone())+'</div>';
  const layouts=state.boot.layout;
  $$('.grid-stack-item').forEach(el=>{
    const layout=layouts.find(x=>x.id===el.getAttribute('gs-id'));
    for(const key of ['x','y','w','h'])el.setAttribute('gs-'+key,layout[key]);
    el.setAttribute('gs-min-w',Math.min(layout.w,3)); el.setAttribute('gs-min-h',layout.id==='upload'?2:3);
  });
  state.grid=GridStack.init({column:12,cellHeight:44,margin:7,handle:'.card-drag',animate:true,
    disableDrag:true,disableResize:true,columnOpts:{breakpoints:[{w:750,c:1}]}},$('.grid-stack'));
  enableDrops();
}
async function renderLibrary(){
  const params=new URLSearchParams({q:state.filter,kind:state.kind,offset:state.offset,limit:30});
  for(const key of ['topic','ticker','source','date_from','date_to'])if(state[key])params.set(key,state[key]);
  const result=await api('/documents?'+params);
  $('#view').innerHTML='<div class="section-toolbar"><span class="small-text muted">'+number(result.total)+' saved sources · Original files and Markdown retained</span><div class="controls">'+button('new-note','New note','notebook-pen')+button('import-url','Add article URL','link')+button('upload','Upload sources','plus','','primary')+'</div></div><div class="page-panel flush"><form id="library-filters" class="filter-bar"><input name="q" value="'+esc(state.filter)+'" placeholder="Search your library" aria-label="Search library"><select name="kind" aria-label="Source type"><option value="">All formats</option>'+['article','email','transcript','document','chatgpt','note'].map(x=>'<option '+(state.kind===x?'selected':'')+' value="'+x+'">'+x+'</option>').join('')+'</select><input name="topic" value="'+esc(state.topic||'')+'" placeholder="Topic" aria-label="Topic filter"><input name="ticker" value="'+esc(state.ticker||'')+'" placeholder="Ticker" aria-label="Ticker filter"><input name="source" value="'+esc(state.source||'')+'" placeholder="Source name" aria-label="Source filter"><input name="date_from" type="date" value="'+esc(state.date_from||'')+'" aria-label="Research date from"><input name="date_to" type="date" value="'+esc(state.date_to||'')+'" aria-label="Research date to"><button class="button small" type="submit">'+icon('filter')+'Filter</button>'+button('reset-filters','Clear','','','small')+'</form>'+libraryTable(result.items)
    +'<div class="pagination"><span>'+result.total+' results</span><span>'+button('prev-library','Previous','chevron-left','','small')+' '+button('next-library','Next','chevron-right','','small')+'</span></div></div>';
  $('#library-filters').onsubmit=async e=>{e.preventDefault();Object.assign(state,formData(e.target));state.filter=state.q;state.offset=0;await renderLibrary();icons();};
}
async function renderDocument(identity){
  if(!identity){location.hash='library';return;}
  const d=await api('/documents/'+encodeURIComponent(identity));
  $('#page-title').textContent=d.title;
  $('#view').innerHTML='<div class="source-toolbar"><a class="button" href="#library">'+icon('chevron-left')+'Back to library</a>'+button('edit-document','Edit details','pencil',d.id)+
    '<a class="button" href="/api/documents/'+d.id+'/file/markdown">'+icon('download')+'Markdown</a><a class="button" href="/api/documents/'+d.id+'/file/original">'+icon('download')+'Original</a>'+button('source-versions','Version history','history',d.id)+button('task-from-source','Add review task','calendar-days',d.id)+button('archive-document',d.archived?'Restore source':'Archive source','archive',d.id)+'</div>'
    +'<div class="source-meta">'+badge(d.ai_generated?'AI-generated research':d.kind,d.ai_generated?'ai':'neutral')+d.tags.map(t=>badge(t)).join('')+d.tickers.map(t=>badge(t,'green')).join('')+'</div>'
    +'<div class="source-details"><span>Source: '+esc(d.source_name)+'</span><span>Research date: '+esc(dateLabel(d.created_at))+'</span><span>Published: '+esc(dateLabel(d.published_at))+'</span><span>Imported: '+esc(dateLabel(d.retrieved_at))+'</span>'+(d.url?'<a href="'+esc(d.url)+'" target="_blank" rel="noopener noreferrer">Open original webpage ↗</a>':'')+'</div>'
    +(d.ai_generated?'<div class="info-box amber">This record contains AI-generated research. Check its cited evidence and research date before relying on its conclusions. Referenced files may need to be imported separately.</div>':'')
    +'<article class="page-panel markdown">'+md(d.content)+'</article>';
}
async function renderPortfolio(){
  const p=state.boot.portfolio;
  $('#view').innerHTML='<div class="section-toolbar"><span class="small-text muted">Holdings and watchlist · Values grouped by currency</span><div class="controls">'+button('refresh-quotes','Refresh free quotes','refresh-cw')+button('add-stock','Add stock','plus','','primary')+'</div></div>'
    +'<div class="three-column">'+(Object.keys(p.totals).length?Object.entries(p.totals).map(([currency,value])=>'<div class="connection-card"><span class="small-text muted">'+esc(currency)+' HOLDINGS</span><strong class="portfolio-value">'+money(value,currency)+'</strong><span class="small-text">Saved-price valuation · '+esc(currency)+'</span></div>').join(''):'<div class="connection-card"><span class="small-text muted">YOUR PORTFOLIO</span><strong class="portfolio-value">—</strong><span class="small-text muted">Add a holding and its latest price.</span></div>')+'</div>'
    +'<div class="info-box">Quote provider: <strong>'+esc(state.boot.market_data.provider)+'</strong>. Connect your own free Finnhub key in Profile & Settings for US stock quotes. Without a key, the app tries Stooq daily closes; automated downloads may be blocked. Saved quotes show their source and date. Other markets can use a manual price. Currency totals stay separate.</div>'
    +(p.missing.length?'<div class="info-box amber">Incomplete valuation: '+esc(p.missing.join(', '))+' have no saved price.</div>':'')
    +'<div class="page-panel flush"><div class="table-scroll"><table class="data-table"><thead><tr><th>Stock</th><th>Currency</th><th class="numeric">Shares</th><th class="numeric">Average cost</th><th class="numeric">Saved price</th><th class="numeric">Daily change</th><th>Price source / date</th><th>Manage</th></tr></thead><tbody>'+stockRows(p.stocks,false)+'</tbody></table></div></div>';
}
function renderCalendar(){
  const selected=state.selectedDay||localDay();
  const tasks=state.boot.tasks.filter(t=>localDay(t.due_at)===selected);
  $('#view').innerHTML='<div class="section-toolbar"><span class="small-text muted">Tasks use '+esc(state.boot.preferences.timezone)+' for display.</span><div class="controls"><a class="button" href="/api/calendar.ics">'+icon('download')+'Export calendar</a>'+button('add-task','New task','plus','','primary')+'</div></div><div class="two-column"><section class="page-panel">'+calendarGrid(true)+'</section><section class="page-panel"><h2>'+esc(dateLabel(selected,{weekday:'long',month:'long',day:'numeric'}))+'</h2><div class="task-list">'+taskRows(tasks,100)+'</div></section></div><section class="page-panel"><h2>Upcoming reviews</h2>'+taskRows(state.boot.tasks.filter(t=>!t.done),50)+'</section>';
}
async function renderDigests(){
  const rows=await api('/digests');state.digestRows=rows;
  const current=rows.find(d=>d.id===state.digestId)||rows[0];
  $('#view').innerHTML='<div class="section-toolbar"><span class="small-text muted">Saved briefings, each linked to its evidence.</span>'+button('generate-digest','Create excerpt digest','refresh-cw')+'</div><div class="two-column"><section class="page-panel">'+(current?'<div class="source-meta">'+badge(current.method,current.method.includes('Dot')?'ai':'neutral')+badge(current.day)+'</div><article class="markdown">'+md(current.content)+'</article><h3>Cited library sources</h3><div class="source-meta">'+current.document_ids.map((id,i)=>'<a class="badge" href="#document/'+id+'">Source '+(i+1)+'</a>').join('')+'</div>':empty('Your next briefing starts with a source','Your dot can publish a synthesised digest through its tools. Local excerpt digests are available without an AI API.','upload','Add research','newspaper'))+'</section><section><div class="info-box">Your dot can analyse the library and publish a cited digest. The built-in daily job creates a clearly labelled excerpt briefing from new material; it does not perform AI analysis.</div><div class="digest-list">'+rows.map(d=>'<button class="'+(current?.id===d.id?'active':'')+'" data-action="select-digest" data-id="'+d.id+'"><strong>'+esc(d.title)+'</strong><small>'+esc(d.day)+' · '+esc(d.method)+' · '+d.document_ids.length+' sources</small></button>').join('')+'</div></section></div>';
}
async function renderUploads(){
  const jobs=await api('/jobs');
  $('#view').innerHTML='<div class="page-panel"><h2>Import existing research</h2><p class="small-text muted">Drop a ChatGPT export ZIP, conversations JSON, or your own files. Review conversations before indexing. Original uploads are kept locally; Markdown copies and searchable records are created in the background.</p>'+dropzone()+'<div class="info-box">Supported: text PDFs, Markdown, text, HTML, EML email, CSV, VTT/SRT transcripts and JSON. Scanned PDFs need OCR first. ChatGPT attachments and linked web pages are not guaranteed to be present in an export. Import issues are reported below.</div></div><div class="section-toolbar"><h2>Import & background activity</h2>'+button('reload-jobs','Refresh','refresh-cw','','small')+'</div><section class="page-panel flush">'+(jobs.length?jobs.map(j=>'<div class="job-row"><div><strong>'+esc(({import:'Research import',quotes:'Quote refresh',feed:'Feed refresh',url:'Article retrieval'})[j.kind]||j.kind)+'</strong><p>'+esc(dateLabel(j.created_at,{dateStyle:'short',timeStyle:'short'}))+'</p></div><div>'+badge(j.status,j.status==='complete'?'green':j.status==='failed'?'red':j.status==='partial'?'amber':'neutral')+'</div><div><span>'+j.imported+' saved · '+j.duplicates+' duplicates · '+j.errors.length+' issues</span><div class="progress-bar"><span style="width:'+(j.total?Math.min(100,j.processed/j.total*100):0)+'%"></span></div><p>'+j.processed+' / '+j.total+' processed</p></div><div class="job-actions">'+(['failed','partial'].includes(j.status)?button('retry-job','Retry','refresh-cw',j.id,'small'):'')+(['complete','partial'].includes(j.status)&&['import','url'].includes(j.kind)?button('undo-job','Undo','rotate-ccw',j.id,'small'):'')+(j.errors.length?button('job-issues','Issues','info',j.id,'small'):'')+'</div></div>').join(''):empty('Ready when you are','Imports can be resumed safely; duplicate research is detected.','','','upload'))+'</section>';
  enableDrops();
}
async function renderActivity(){
  const params=new URLSearchParams({limit:100,offset:state.activityOffset||0,q:state.activityQuery||'',actor_filter:state.actorFilter||''});
  const rows=await api('/activity?'+params);
  $('#view').innerHTML='<div class="page-panel flush"><form id="activity-filters" class="filter-bar"><input name="q" value="'+esc(state.activityQuery||'')+'" placeholder="Search actions" aria-label="Search actions"><select name="actor_filter" aria-label="Filter actor">'+['','Owner','Dot','System'].map(x=>'<option value="'+x+'" '+(x===(state.actorFilter||'')?'selected':'')+'>'+(x||'All actors')+'</option>').join('')+'</select><button class="button small" type="submit">Filter</button></form><div class="table-scroll"><table class="data-table"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Details</th></tr></thead><tbody>'+rows.map(a=>'<tr><td class="small-text">'+esc(dateLabel(a.at,{dateStyle:'short',timeStyle:'medium'}))+'</td><td>'+badge(a.actor,a.actor==='Dot'?'ai':'neutral')+'</td><td>'+esc(a.action)+'</td><td><button class="link-button" data-action="activity-details" data-id="'+a.id+'">View record</button></td></tr>').join('')+'</tbody></table></div><div class="pagination"><span>Showing '+rows.length+' actions</span><span>'+button('prev-activity','Previous','chevron-left','','small')+' '+button('next-activity','Next','chevron-right','','small')+'</span></div></div>';
  state.activityRows=rows;
  $('#activity-filters').onsubmit=async e=>{e.preventDefault();const values=formData(e.target);state.activityQuery=values.q;state.actorFilter=values.actor_filter;state.activityOffset=0;await renderActivity();icons();};
}
async function renderConnections(){
  const rows=await api('/sources');state.sourceRows=rows;
  $('#view').innerHTML='<div class="section-toolbar"><span class="small-text muted">Register all your sources in one place.</span>'+button('add-source','Add connection','plus','','primary')+'</div><div class="info-box">Enabled RSS/Atom feeds are checked periodically by the local worker. Web, email and manual connections are source records: your dot imports their content using its authorised tools or you upload files. Adding a connection does not sign in to that service.</div><div class="three-column">'+(rows.length?rows.map(s=>'<article class="connection-card"><div>'+badge(s.kind,'neutral')+' '+badge(s.enabled?'Enabled':'Paused',s.enabled?'green':'neutral')+'</div><h2>'+esc(s.name)+'</h2><p>'+esc(s.url||'Content supplied by you or your dot')+'</p><div>'+s.topics.map(t=>badge(t)).join('')+'</div><p>Last retrieved: '+esc(dateLabel(s.last_fetched))+'</p>'+(s.last_error?'<p class="danger-text">'+esc(s.last_error)+'</p>':'')+'<div class="connection-actions">'+(s.kind==='rss'?button('refresh-source','Refresh','refresh-cw',s.id,'small'):'')+button('edit-source','Edit','pencil',s.id,'small')+button('delete-source','Remove','trash-2',s.id,'small')+'</div></article>').join(''):empty('Connect your first source','Add an RSS feed or register the sources your dot collects from.','add-source','Add connection','link'))+'</div>';
}
function renderSettings(){
  const p=state.boot.preferences;
  $('#view').innerHTML='<section class="page-panel settings-form"><h2>Investor profile & research instructions</h2><p class="small-text muted">A visible, editable reference for you and your dot. This stores explicit app instructions; it does not display your dot’s private internal memory.</p><form id="settings-form" class="form-stack"><label>Research instructions<textarea name="profile" placeholder="Investment objectives, preferred sources, research methodology, thesis criteria, digest preferences…">'+esc(p.profile)+'</textarea></label><div class="form-grid">'+field('Workspace timezone','timezone',p.timezone)+field('Daily excerpt digest','digest_time',p.digest_time,'time')+'</div>'+field('Your dot conversation URL','dot_url',p.dot_url,'url')+'<div class="form-actions"><button class="button primary" type="submit">'+icon('save')+'Save preferences</button></div></form></section><section class="page-panel settings-form"><h2>Connect your actual dot</h2><p class="small-text muted">Use the included local skill and authenticated agent CLI on the connected Mac, or configure the included stdio MCP server in a compatible host. The dashboard and your dot use the same app records and activity log.</p><div class="info-box"><code>.venv/bin/research-desk-agent tools</code><br><code>.venv/bin/research-desk-mcp</code><br>See <strong>DOT_INSTRUCTIONS.md</strong> in the project folder. The agent credential stays in the local data folder and is never displayed here.</div><p class="small-text muted">This app does not embed your personal dot’s ChatGPT conversation. Open your dot in ChatGPT to direct it. No OpenAI API key is required by the app.</p></section><section class="page-panel settings-form"><h2>Your data stays portable</h2><p class="small-text muted">Back up the database, originals, Markdown and local credentials together. Use the documented backup and restore commands in the project README. Backups contain private data; keep them outside Git.</p><div class="settings-footer">'+(state.boot.demo?button('clear-demo','Remove sample data','trash-2'):button('load-demo','Explore sample workspace','eye'))+button('reset-layout','Reset dashboard layout','rotate-ccw')+'</div></section>';
  $('#settings-form').onsubmit=async e=>{e.preventDefault();await api('/preferences',{method:'PUT',body:formData(e.target)});await refresh();toast('Preferences saved.');};
  const section=document.createElement('section');section.className='page-panel settings-form';
  section.innerHTML='<h2>Free stock-price connection</h2><p class="small-text muted">Current provider: <strong>'+esc(state.boot.market_data.provider)+'</strong>. Create your own free personal-use key at <a href="https://finnhub.io/" target="_blank" rel="noopener noreferrer">Finnhub ↗</a>. Coverage and limits depend on your account. The key is saved only on this Mac, never returned through the API or written to the activity log.</p><form id="quote-key-form" class="form-stack">'+field('Finnhub API key','key','','password','required autocomplete="off" minlength="12" maxlength="200"')+'<div class="form-actions">'+(state.boot.market_data.configured?button('remove-quote-key','Remove saved key','trash-2'):'')+'<button class="button primary" type="submit">Save quote connection</button></div></form>';
  $('#view').insertBefore(section,$('#view').children[1]);
  bindForm('#quote-key-form',async data=>{await post('/market-data/key',data);await refresh();toast('Quote connection saved. Refresh your portfolio prices.');});
}

function bindForm(id, handler){
  $(id).onsubmit=async event=>{
    event.preventDefault();
    const submit=event.target.querySelector('[type="submit"]');
    if(submit)submit.disabled=true;
    try{await handler(formData(event.target),event.target);}catch(error){toast(error.message,true);}
    finally{if(submit)submit.disabled=false;}
  };
}
function stockForm(id){
  const s=state.boot.portfolio.stocks.find(x=>x.id===id)||{symbol:'',quote_symbol:'',category:'watchlist',exchange:'US',currency:'USD',shares:0,average_cost:'',notes:''};
  openModal(id?'Edit '+s.symbol:'Add a stock','<form id="stock-form"><div class="form-grid">'+field('Ticker symbol','symbol',s.symbol,'text','required maxlength="20" placeholder="AAPL"')+field('Free quote symbol','quote_symbol',s.quote_symbol,'text','required maxlength="30" placeholder="aapl.us"')+selectField('List','category',s.category,[['watchlist','Watchlist'],['holding','Owned holding']])+field('Exchange','exchange',s.exchange)+field('Currency','currency',s.currency,'text','required pattern="[A-Z]{3}" maxlength="3"')+field('Number of shares','shares',s.shares,'number','min="0" step="any" required')+field('Average cost per share (optional)','average_cost',s.average_cost??'','number','min="0" step="any"')+'<label class="full">Notes<textarea name="notes">'+esc(s.notes)+'</textarea></label></div><p class="form-hint">US stocks use quote symbols such as aapl.us. Other markets can use a saved manual price. Removing a stock retains its action history.</p>'+formActions(id?'Save stock':'Add stock')+'</form>');
  $('[name="symbol"]').addEventListener('input',event=>{
    const quote=$('[name="quote_symbol"]');if(!id)quote.value=event.target.value.toLowerCase()+'.us';
  });
  bindForm('#stock-form',async data=>{
    data.shares=Number(data.shares);data.average_cost=data.average_cost===''?null:Number(data.average_cost);data.currency=data.currency.toUpperCase();
    await api('/stocks'+(id?'/'+id:''),{method:id?'PUT':'POST',body:data});closeModal();await refresh();toast('Stock saved.');
  });
}
function manualPriceForm(id){
  const s=state.boot.portfolio.stocks.find(x=>x.id===id);
  openModal('Set a saved price for '+s.symbol,'<form id="price-form" class="form-stack">'+field('Price in '+s.currency,'price',s.last_price??'','number','required min="0.000001" step="any"')+field('Previous close (optional)','previous_price',s.previous_price??'','number','min="0.000001" step="any"')+field('Price date','as_of',s.price_at?.slice(0,10)||localDay(),'date','required')+'<p class="form-hint">This is labelled as a manual quote. Use the date of the price you entered.</p>'+formActions('Save price')+'</form>');
  bindForm('#price-form',async data=>{await post('/stocks/'+id+'/price',{price:Number(data.price),previous_price:data.previous_price?Number(data.previous_price):null,as_of:data.as_of});closeModal();await refresh();toast('Manual quote saved.');});
}
async function taskForm(id,documentId=''){
  const task=state.boot.tasks.find(t=>t.id===id)||{title:'',due_at:new Date((state.selectedDay||localDay())+'T10:00:00').toISOString(),notes:'',done:false,document_id:documentId||null};
  const localInput=new Date(new Date(task.due_at).getTime()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
  const docs=[...state.boot.library];
  if(task.document_id&&!docs.some(d=>d.id===task.document_id))docs.push(await api('/documents/'+task.document_id));
  openModal(id?'Edit review task':'New review task','<form id="task-form" class="form-stack">'+field('Task','title',task.title,'text','required')+field('When','due_at',localInput,'datetime-local','required')+'<span class="form-hint">Enter time in this browser’s timezone: '+esc(Intl.DateTimeFormat().resolvedOptions().timeZone)+'.</span>'+selectField('Linked research','document_id',task.document_id||'',[['','No linked source'],...docs.map(d=>[d.id,d.title])])+'<label>Notes<textarea name="notes">'+esc(task.notes)+'</textarea></label><label class="checkbox-label"><input type="checkbox" name="done" '+(task.done?'checked':'')+'>Completed</label>'+formActions(id?'Save task':'Add task')+(id?button('delete-task','Remove task','trash-2',id,'danger small'):'')+'</form>');
  bindForm('#task-form',async (data,form)=>{
    await api('/tasks'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{...data,due_at:new Date(data.due_at).toISOString(),done:form.elements.done.checked,document_id:data.document_id||null}});
    closeModal();await refresh();toast('Calendar task saved.');
  });
}
function sourceForm(id){
  const s=state.sourceRows.find(x=>x.id===id)||{name:'',kind:'rss',url:'',topics:[],enabled:true};
  openModal(id?'Edit connection':'Add a source connection','<form id="source-form" class="form-stack">'+field('Source name','name',s.name,'text','required')+selectField('Connection type','kind',s.kind,[['rss','RSS / Atom feed'],['web','Website (collected by your dot)'],['email','Email (upload or dot connection)'],['manual','Manual research source']])+field('Feed or source URL','url',s.url,'url')+field('Topics, separated by commas','topics',s.topics.join(', '))+'<label class="checkbox-label"><input type="checkbox" name="enabled" '+(s.enabled?'checked':'')+'>Enabled</label><p class="form-hint">RSS is retrieved automatically. Other types record the source; your dot or uploaded files supply its content. Source logins are configured separately in ChatGPT.</p>'+formActions(id?'Save connection':'Add connection')+'</form>');
  bindForm('#source-form',async (data,form)=>{await api('/sources'+(id?'/'+id:''),{method:id?'PUT':'POST',body:{...data,topics:tags(data.topics),enabled:form.elements.enabled.checked}});closeModal();await refresh();toast('Connection saved.');});
}
async function documentForm(id){
  const d=id?await api('/documents/'+id):null;
  if(d){
    openModal('Organise this source','<form id="document-form" class="form-stack">'+field('Title','title',d.title,'text','required')+field('Topics, separated by commas','tags',d.tags.join(', '))+field('Tickers, separated by commas','tickers',d.tickers.join(', '))+'<label>Summary<textarea name="summary">'+esc(d.summary)+'</textarea></label>'+formActions()+'</form>');
    bindForm('#document-form',async data=>{await api('/documents/'+id,{method:'PATCH',body:{...data,tags:tags(data.tags),tickers:tags(data.tickers)}});closeModal();await refresh();toast('Source details saved; previous version retained.');});
  }else{
    openModal('New research note','<form id="document-form" class="form-stack">'+field('Title','title','','text','required')+field('Topics, separated by commas','tags')+'<label>Research note<textarea name="content" required placeholder="Write a thesis, research question, or source-backed observation. Markdown is supported."></textarea></label>'+formActions('Save note')+'</form>');
    bindForm('#document-form',async data=>{const result=await post('/documents',{...data,tags:tags(data.tags),kind:'note',source_name:'Personal research'});closeModal();await refresh(false);location.hash='document/'+result.document.id;toast('Research note saved.');});
  }
}
function urlForm(){
  openModal('Save an article from the web','<form id="url-form" class="form-stack">'+field('Article URL','url','','url','required placeholder="https://…"')+field('Source name (optional)','source_name')+'<p class="form-hint">Public web articles only. Signed-in and paywalled pages can be collected by your dot through its authorised browser, then saved to the library.</p>'+formActions('Retrieve article')+'</form>');
  bindForm('#url-form',async data=>{await post('/import-url',data);closeModal();location.hash='uploads';await refresh();toast('Article retrieval queued.');});
}
function enableDrops(){
  $$('.dropzone').forEach(el=>{
    el.addEventListener('dragover',event=>{event.preventDefault();el.classList.add('dragover');});
    el.addEventListener('dragleave',()=>el.classList.remove('dragover'));
    el.addEventListener('drop',event=>{event.preventDefault();el.classList.remove('dragover');state.uploadQueue.push(...event.dataTransfer.files);processUploadQueue().catch(error=>toast(error.message,true));});
  });
}
async function processUploadQueue(){
  if(state.preview||!state.uploadQueue.length)return;
  const file=state.uploadQueue.shift(),form=new FormData();form.append('file',file);
  toast('Reviewing '+file.name+'…');
  try{
    const preview=await api('/imports/preview',{method:'POST',body:form});
    if(!preview.conversation_count){
      await post('/imports',{upload_id:preview.upload_id,include_files:true});
      toast('Import queued for '+file.name+'.');location.hash='uploads';await refresh();
      await processUploadQueue();return;
    }
    state.preview=preview;state.selectedConversations=new Set(preview.conversations.map(x=>x.id));
    openModal('Review your ChatGPT import','<p class="small-text muted">'+esc(file.name)+' · '+number(preview.conversation_count)+' conversations. Only selected conversations will be indexed. The unchanged original archive is retained locally.</p><input id="conversation-filter" class="wide" placeholder="Find research conversations…" aria-label="Filter conversations"><p><label class="checkbox-label small-text"><input id="select-all-conversations" type="checkbox" checked>Select all '+number(preview.conversation_count)+' conversations</label></p><div id="conversation-list" class="import-list"></div><p id="selection-count" class="small-text muted"></p><label class="checkbox-label small-text"><input id="include-import-files" type="checkbox">Also index supported files in the archive ('+preview.files.length+'). Files are not automatically matched to selected conversations.</label><div class="info-box amber">ChatGPT output is saved as AI research. Article links and missing attachments are recorded in the conversation; their original content needs a separate import or retrieval.</div><div class="form-actions">'+button('cancel-import','Cancel')+button('confirm-import','Import selected research','upload','','primary')+'</div>');
    renderConversationList();
    $('#conversation-filter').oninput=renderConversationList;
    $('#select-all-conversations').onchange=event=>{state.selectedConversations=event.target.checked?new Set(preview.conversations.map(x=>x.id)):new Set();renderConversationList();};
  }catch(error){toast(file.name+': '+error.message,true);await processUploadQueue();}
}
function renderConversationList(){
  const query=$('#conversation-filter').value.toLowerCase(),p=state.preview;
  const rows=p.conversations.filter(c=>c.title.toLowerCase().includes(query));
  $('#conversation-list').innerHTML=rows.slice(0,100).map(c=>'<label class="import-item"><input type="checkbox" data-conversation="'+esc(c.id)+'" '+(state.selectedConversations.has(c.id)?'checked':'')+'><span>'+esc(c.title)+'</span><small class="muted">'+esc(dateLabel(c.created_at,{dateStyle:'short'}))+'</small></label>').join('');
  $('#selection-count').textContent=number(state.selectedConversations.size)+' selected · Showing '+Math.min(100,rows.length)+' of '+number(rows.length)+' matches. Filter to find more; selections are retained.';
  $('#select-all-conversations').checked=state.selectedConversations.size===p.conversation_count;
  $$('[data-conversation]').forEach(el=>el.onchange=()=>{el.checked?state.selectedConversations.add(el.dataset.conversation):state.selectedConversations.delete(el.dataset.conversation);$('#selection-count').textContent=number(state.selectedConversations.size)+' selected';$('#select-all-conversations').checked=state.selectedConversations.size===p.conversation_count;});
}
async function handleAction(action,id,el){
  switch(action){
    case 'close-modal':if(state.preview){state.preview=null;closeModal();await processUploadQueue();}else closeModal();break;
    case 'logout':await post('/logout');state.boot=null;$('#login-screen').hidden=false;$('#login-password').value='';break;
    case 'document':location.hash='document/'+id;break;
    case 'upload':$('#file-input').click();break;
    case 'new-note':await documentForm();break;
    case 'edit-document':await documentForm(id);break;
    case 'archive-document':{const d=await api('/documents/'+id);await api('/documents/'+id,{method:'PATCH',body:{archived:!d.archived}});await refresh(false);location.hash='library';toast(d.archived?'Source restored.':'Source archived; original retained.');break;}
    case 'source-versions':{const rows=await api('/documents/'+id+'/versions');openModal('Previous source versions',rows.length?rows.map(r=>{const d=JSON.parse(r.snapshot);return '<details class="page-panel"><summary>'+esc(dateLabel(r.created_at,{dateStyle:'medium',timeStyle:'short'}))+' · '+esc(d.title)+'</summary><div class="markdown">'+md(d.content)+'</div></details>';}).join(''):'<div class="empty-state">This is the first saved version.</div>');break;}
    case 'import-url':urlForm();break;
    case 'add-stock':stockForm();break;
    case 'edit-stock':stockForm(id);break;
    case 'manual-price':manualPriceForm(id);break;
    case 'delete-stock':if(confirm('Remove this stock from your list? Its action history will be retained.')){await api('/stocks/'+id,{method:'DELETE'});await refresh();toast('Stock removed.');}break;
    case 'refresh-quotes':await post('/quotes/refresh');toast('Daily quote refresh queued. Check Imports for results.');await refresh();break;
    case 'remove-quote-key':await api('/market-data/key',{method:'DELETE'});await refresh();toast('Locally saved quote key removed.');break;
    case 'add-task':await taskForm();break;
    case 'edit-task':await taskForm(id);break;
    case 'task-from-source':await taskForm('',id);break;
    case 'toggle-task':{const t=state.boot.tasks.find(t=>t.id===id);await api('/tasks/'+id,{method:'PUT',body:{title:t.title,due_at:t.due_at,done:!t.done,notes:t.notes,document_id:t.document_id}});await refresh();break;}
    case 'delete-task':if(confirm('Remove this calendar task?')){await api('/tasks/'+id,{method:'DELETE'});closeModal();await refresh();toast('Task removed.');}break;
    case 'select-day':state.selectedDay=id;await renderRoute();break;
    case 'prev-month':state.month--;if(state.month<0){state.month=11;state.year--;}await renderRoute();break;
    case 'next-month':state.month++;if(state.month>11){state.month=0;state.year++;}await renderRoute();break;
    case 'generate-digest':await post('/digests/generate');await refresh();toast('Local excerpt digest saved.');break;
    case 'select-digest':state.digestId=id;await renderDigests();break;
    case 'prev-library':state.offset=Math.max(0,state.offset-30);await renderLibrary();break;
    case 'next-library':state.offset+=30;await renderLibrary();break;
    case 'reset-filters':for(const k of ['filter','kind','topic','ticker','source','date_from','date_to'])state[k]='';state.offset=0;await renderLibrary();break;
    case 'prev-activity':state.activityOffset=Math.max(0,(state.activityOffset||0)-100);await renderActivity();break;
    case 'next-activity':state.activityOffset=(state.activityOffset||0)+100;await renderActivity();break;
    case 'activity-details':{const row=state.activityRows.find(r=>r.id===Number(id));openModal(row.action,'<p class="small-text muted">'+esc(row.actor)+' · '+esc(dateLabel(row.at,{dateStyle:'medium',timeStyle:'medium'}))+'</p><pre class="job-errors">'+esc(JSON.stringify(row.details,null,2))+'</pre>');break;}
    case 'edit-layout':{
      if(innerWidth<950){toast('Use a wider window to customise the desktop layout.');break;}
      state.editing=true;$('.grid-stack').classList.add('editing');state.grid.enableMove(true);state.grid.enableResize(true);
      $('.layout-toolbar').innerHTML=button('reset-layout','Reset','rotate-ccw','','small')+button('save-layout','Save layout','check','','small primary');
      toast('Drag a card by its header; resize it from the bottom-right corner.');break;
    }
    case 'save-layout':{
      const layout=state.grid.save(false).map(n=>({id:String(n.id),x:n.x??0,y:n.y??0,w:n.w??n.minW??1,h:n.h??n.minH??1}));
      await api('/layout',{method:'PUT',body:layout});await refresh();toast('Dashboard layout saved.');break;
    }
    case 'reset-layout':await post('/layout/reset');await refresh();toast('Original layout restored.');break;
    case 'add-source':sourceForm();break;
    case 'edit-source':sourceForm(id);break;
    case 'delete-source':if(confirm('Remove this connection? Saved research will stay in your library.')){await api('/sources/'+id,{method:'DELETE'});await refresh();toast('Connection removed.');}break;
    case 'refresh-source':await post('/sources/'+id+'/refresh');await refresh();toast('Feed retrieval queued.');break;
    case 'load-demo':await post('/demo');await refresh();toast('Sample workspace loaded. All sample data is labelled.');break;
    case 'clear-demo':if(confirm('Remove sample research and sample stocks? Your own research will be retained.')){await api('/demo',{method:'DELETE'});await refresh();toast('Sample data removed.');}break;
    case 'reload-jobs':await renderUploads();break;
    case 'retry-job':await post('/jobs/'+id+'/retry');await refresh();toast('Job queued for retry.');break;
    case 'undo-job':if(confirm('Archive new unchanged records from this import? Original uploads, existing revisions and later edits will be retained.')){const result=await post('/jobs/'+id+'/undo');await refresh();toast(result.archived+' records archived.');}break;
    case 'job-issues':{const jobs=await api('/jobs'),job=jobs.find(j=>j.id===id);openModal('Import issues','<pre class="job-errors">'+esc(JSON.stringify(job.errors,null,2))+'</pre>');break;}
    case 'cancel-import':state.preview=null;closeModal();await processUploadQueue();break;
    case 'confirm-import':{
      const p=state.preview;await post('/imports',{upload_id:p.upload_id,selected_ids:state.selectedConversations.size===p.conversation_count?null:[...state.selectedConversations],include_files:$('#include-import-files').checked});
      state.preview=null;closeModal();location.hash='uploads';await refresh();toast('Selected research queued for import.');await processUploadQueue();break;
    }
    default:break;
  }
  icons();
}
document.addEventListener('click',event=>{
  const el=event.target.closest('[data-action]');if(!el)return;
  event.preventDefault();if(el.disabled)return;
  Promise.resolve(handleAction(el.dataset.action,el.dataset.id||'',el)).catch(error=>toast(error.message,true));
});
$('#file-input').addEventListener('change',event=>{
  state.uploadQueue.push(...event.target.files);event.target.value='';
  processUploadQueue().catch(error=>toast(error.message,true));
});
$('#modal').addEventListener('cancel',()=>{state.preview=null;});
$('#global-search').addEventListener('keydown',event=>{
  if(event.key==='Enter'){state.filter=event.target.value;state.offset=0;if(state.route==='library')renderRoute().catch(error=>toast(error.message,true));else location.hash='library';}
});
$('#login-form').onsubmit=async event=>{
  event.preventDefault();const submit=event.target.querySelector('button[type=submit]');submit.disabled=true;
  try{await post('/login',{password:$('#login-password').value});$('#login-password').value='';$('#login-error').textContent='';await refresh();}
  catch(error){$('#login-error').textContent=error.message;}finally{submit.disabled=false;}
};
window.addEventListener('hashchange',()=>renderRoute().catch(error=>toast(error.message,true)));
window.addEventListener('unhandledrejection',event=>{event.preventDefault();toast(event.reason?.message||'The action could not be completed.',true);});
setInterval(async()=>{
  if(!state.boot||$('#modal').open||state.editing)return;
  try{
    if(state.boot.active_jobs>0){
      await refresh(false);
      if(['uploads','connections','portfolio','activity'].includes(state.route))await renderRoute();
      if(!state.boot.active_jobs)toast('Background work finished. Your library is up to date.');
    }
  }catch{/* The next foreground request will show connection or sign-in errors. */}
},4000);
icons();
refresh().catch(error=>{if(!$('#login-screen').hidden)return;toast(error.message,true);});
