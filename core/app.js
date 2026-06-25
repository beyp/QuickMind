// QuickMind Web App
var QM = {};

(function() {

var API = window.location.origin;
var curCat = null, curStatus = '', curSearch = '', curView = 'list';
var curTaskId = null, addPrio = 'normal', editPrio = 'normal', editStatus = 'todo';
var addDays = [], editDays = [], cats = [], searchTimer = null, aiSugs = [];

function apiFetch(path, opts) {
  opts = opts || {};
  return fetch(API + path, {
    method: opts.m || 'GET',
    headers: {'Content-Type':'application/json'},
    body: opts.b ? JSON.stringify(opts.b) : undefined
  }).then(function(r) {
    if (!r.ok) return r.json().then(function(e) { throw new Error(e.detail || r.statusText); });
    return r.json();
  });
}

function toast(msg, type) {
  var el = document.getElementById('toast-msg');
  el.innerHTML = msg;
  el.className = 'toast show ' + (type || 'ok');
  setTimeout(function() { el.classList.remove('show'); }, 3000);
}

function esc(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'<').replace(/>/g,'>');
}

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}

function fmtDateInput(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset()*60000).toISOString().slice(0,16);
}

function g(id) { return document.getElementById(id); }

function sortKey(t) {
  if (t.status === 'done') return [99,0];
  var now = new Date(), rem = t.reminder ? new Date(t.reminder) : null;
  var pc = {urgent:4,high:3,normal:2,low:1}, p = 5-(pc[t.priority]||2);
  if (rem) {
    if (rem < now) return [0,p];
    var d = (rem-now)/86400000;
    if (d < 1) return [1,p]; if (d < 7) return [2,p,d]; return [3,p,d];
  }
  return [4,p];
}

function dlBadge(t) {
  if (!t.reminder) return '';
  var now = new Date(), rem = new Date(t.reminder);
  var d = Math.floor((rem-now)/86400000);
  if (rem < now && t.status !== 'done') return '<span class="badge b-late">EN RETARD</span>';
  if (d === 0) return '<span class="badge b-today">AUJOURD HUI</span>';
  if (d === 1) return '<span class="badge b-tmw">DEMAIN</span>';
  if (d <= 7)  return '<span class="badge b-soon">J-'+d+'</span>';
  return '';
}

function catColor(n) {
  var c = cats.find(function(x){return x.name===n;});
  return c ? c.color : 'var(--text3)';
}

// ── Init ─────────────────────────────────────────────────────────────────────
function init() {
  Promise.all([loadHealth(), loadCats()]).then(function() {
    buildDayPicker('add'); buildDayPicker('edit');
    loadTasks();
    setInterval(loadHealth, 30000);
    setInterval(function(){if(curView==='list')loadTasks();}, 60000);
  });
}

function loadHealth() {
  return apiFetch('/health').then(function(d) {
    g('sb-dot').classList.add('on');
    g('sb-status').textContent = d.tasks + ' tache(s)';
    g('task-count').textContent = d.tasks + ' taches actives';
  }).catch(function() {
    g('sb-dot').classList.remove('on');
    g('sb-status').textContent = 'Hors ligne';
  });
}

function loadCats() {
  return apiFetch('/categories').then(function(c) {
    cats = c; buildSidebar(); buildCatSelects();
  }).catch(function(){});
}

function buildSidebar() {
  var nav = g('sb-nav');
  nav.innerHTML = '<div class="nav-section">Categories</div>';
  var a = document.createElement('div');
  a.className = 'nav-item' + (curCat===null?' active':'');
  a.id = 'nav-all';
  a.innerHTML = '&#128194; <span>Toutes les taches</span><span class="nav-count" id="nav-count-all">0</span>';
  a.onclick = function(){selCat(null,a);};
  nav.appendChild(a);
  cats.forEach(function(c) {
    var i = document.createElement('div');
    i.className = 'nav-item'+(curCat===c.id?' active':'');
    i.innerHTML = '<span class="nav-dot" style="background:'+c.color+'"></span><span>'+esc(c.name)+'</span>';
    i.onclick = (function(ct,el){return function(){selCat(ct.id,el);};})(c,i);
    nav.appendChild(i);
  });
}

function buildCatSelects() {
  var opts = '<option value="">Aucune</option>' + cats.map(function(c){return '<option value="'+esc(c.name)+'">'+esc(c.name)+'</option>';}).join('');
  g('add-cat').innerHTML = opts;
  g('edit-cat').innerHTML = opts;
}

// ── Navigation ───────────────────────────────────────────────────────────────
function selCat(id, item) {
  curCat = id;
  document.querySelectorAll('.nav-item').forEach(function(i){i.classList.remove('active');});
  item.classList.add('active');
  var c = cats.find(function(x){return x.id===id;});
  g('view-title').textContent = c ? c.name : 'Toutes les taches';
  loadTasks();
}

function switchView(v, item) {
  curView = v;
  g('view-list').style.display   = v==='list'?'block':'none';
  g('view-kanban').style.display = v==='kanban'?'block':'none';
  g('view-add').style.display    = v==='add'?'block':'none';
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  if (item) item.classList.add('active');
  if (v==='list') loadTasks();
  if (v==='kanban') loadKanban();
}

function setStatus(s, item) {
  curStatus = s;
  document.querySelectorAll('.filter-chip').forEach(function(b){b.classList.remove('active');});
  if (item) item.classList.add('active');
  loadTasks();
}

function doSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function(){curSearch=g('search-input').value;loadTasks();}, 300);
}

// ── Tasks ────────────────────────────────────────────────────────────────────
var SL = {todo:'A faire',in_progress:'En cours',done:'Termine'};
var SBC = {todo:'b-todo',in_progress:'b-wip',done:'b-done'};
var PRIO_ICON = {urgent:'&#128308;',high:'&#128992;',normal:'&#9898;',low:'&#128309;'};
var PRIO_CLASS = {urgent:'purg',high:'phig',normal:'pnor',low:'plow'};
var RECUR = {daily:'Quotidien',weekly:'Hebdo',monthly:'Mensuel',yearly:'Annuel',custom:'Perso'};
var DAYS_FR = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
var DAYS_EN = ['mon','tue','wed','thu','fri','sat','sun'];
var GI = {
  0:['En retard','var(--red)'], 1:['Aujourd hui','var(--orange)'],
  2:['Cette semaine','var(--yellow)'], 3:['Prochainement','var(--blue)'],
  4:['Sans echeance','var(--text3)'], 99:['Terminees','var(--green)']
};

function loadTasks() {
  if (curView !== 'list') return;
  var out = g('tasks-output');
  out.innerHTML = '<div class="empty"><div class="empty-icon">&#8987;</div><div class="empty-text">Chargement...</div></div>';
  var url = '/tasks?include_archived=false';
  if (curCat != null) url += '&category_id=' + curCat;
  if (curStatus) url += '&status=' + curStatus;
  apiFetch(url).then(function(tasks) {
    if (curSearch) {
      var k = curSearch.toLowerCase();
      tasks = tasks.filter(function(t){return(t.title||'').toLowerCase().indexOf(k)>=0||(t.description||'').toLowerCase().indexOf(k)>=0;});
    }
    tasks.sort(function(a,b){var ka=sortKey(a),kb=sortKey(b);for(var i=0;i<Math.max(ka.length,kb.length);i++){var d=(ka[i]||0)-(kb[i]||0);if(d!==0)return d;}return 0;});
    var cnt = g('nav-count-all'); if(cnt) cnt.textContent = tasks.length;
    if (!tasks.length) {
      out.innerHTML = '<div class="empty"><div class="empty-icon">&#127881;</div><div class="empty-text">'+(curCat!=null?'Aucune tache dans cette categorie':'Aucune tache !')+'</div><div class="empty-sub">'+(curCat!=null?'Les taches sans categorie sont dans Toutes':'Cliquez + Nouvelle pour commencer')+'</div></div>';
      return;
    }
    var groups = {};
    tasks.forEach(function(t){var k=sortKey(t)[0];if(!groups[k])groups[k]=[];groups[k].push(t);});
    var html = '';
    [0,1,2,3,4,99].forEach(function(gk){
      var gr=groups[gk]; if(!gr||!gr.length) return;
      var info=GI[gk];
      html += '<div class="group-hdr"><div class="group-line" style="background:'+info[1]+'"></div><span class="group-label" style="color:'+info[1]+';background:'+info[1]+'22">'+info[0]+'</span><div class="group-line" style="background:'+info[1]+'"></div></div>';
      gr.forEach(function(t){html+=renderCard(t);});
    });
    out.innerHTML = html;
  }).catch(function(e){out.innerHTML='<div class="empty"><div class="empty-text">Erreur: '+esc(e.message)+'</div></div>';});
}

function renderCard(t) {
  var pc = PRIO_CLASS[t.priority]||'pnor'; if(t.status==='done') pc='pdone';
  var sb = '<span class="badge '+(SBC[t.status]||'b-todo')+'">'+(SL[t.status]||t.status)+'</span>';
  var db = dlBadge(t);
  var rb = (t.recurrence&&t.recurrence!=='') ? '<span class="badge b-rec">'+(RECUR[t.recurrence]||t.recurrence)+'</span>' : '';
  var meta='';
  if(t.category) meta+='<span class="tc-cat"><span class="tc-cat-dot" style="background:'+catColor(t.category)+'"></span>'+esc(t.category)+'</span>';
  if(t.reminder) {
    var now=new Date(),rem=new Date(t.reminder),rcls='reminder-badge';
    if(rem<now&&t.status!=='done') rcls+=' late';
    else if((rem-now)/86400000<1) rcls+=' today';
    else if((rem-now)/86400000<7) rcls+=' soon';
    meta+='<span class="'+rcls+'">&#9200; '+fmtDate(t.reminder)+'</span>';
  }
  if(t.recurrence&&t.recurrence!=='') meta+='<span style="font-size:.72em;color:var(--purple)">&#128260; '+(RECUR[t.recurrence]||t.recurrence)+'</span>';
  var desc = t.description ? '<div class="tc-desc">'+esc(t.description.substring(0,120))+'</div>' : '';
  var prog='';
  if(t.subtask_count>0){var pct=Math.round(t.subtask_done/t.subtask_count*100),pcolor=t.subtask_done===t.subtask_count?'var(--green)':'var(--blue)';prog='<div class="tc-progress"><div class="progress-track"><div class="progress-fill" style="width:'+pct+'%;background:'+pcolor+'"></div></div><div class="progress-text">'+t.subtask_done+'/'+t.subtask_count+'</div></div>';}
  return '<div class="task-card '+pc+'" onclick="QM.openEdit('+t.id+')"><div class="tc-main"><div class="tc-prio">'+PRIO_ICON[t.priority]+'</div><div class="tc-body"><div class="tc-row1"><div class="tc-title">'+esc(t.title)+'</div><div class="tc-badges">'+db+sb+'</div></div>'+desc+'<div class="tc-meta">'+meta+'</div>'+prog+'</div></div></div>';
}

// ── Kanban ───────────────────────────────────────────────────────────────────
function loadKanban() {
  var board = g('kanban-board');
  board.innerHTML = '<div class="empty"><div class="empty-icon">&#8987;</div><div class="empty-text">Chargement...</div></div>';
  apiFetch('/tasks').then(function(tasks) {
    if(curCat!=null){var c=cats.find(function(x){return x.id===curCat;});if(c)tasks=tasks.filter(function(t){return t.category===c.name;});}
    board.innerHTML = '';
    var KCOLS = [['todo','A faire','var(--text3)'],['in_progress','En cours','var(--orange)'],['done','Termine','var(--green)']];
    KCOLS.forEach(function(col){
      var s=col[0],lbl=col[1],cl=col[2];
      var ts=tasks.filter(function(t){return t.status===s;});
      var ce=document.createElement('div'); ce.className='k-col';
      ce.innerHTML='<div class="k-col-hdr"><span class="k-col-title" style="color:'+cl+'">'+lbl+'</span><span class="k-col-count">'+ts.length+'</span></div><div class="k-col-body" id="kb-'+s+'"></div>';
      board.appendChild(ce);
      var body=ce.querySelector('.k-col-body');
      ts.forEach(function(t){
        var card=document.createElement('div'); card.className='task-card '+(PRIO_CLASS[t.priority]||'pnor'); card.style.marginBottom='6px';
        var prevS = s==='done' ? 'in_progress' : 'todo';
        var nextS = s==='todo' ? 'in_progress' : 'done';
        var prevBtn = s!=='todo' ? '<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();QM.moveTask('+t.id+',\''+prevS+'\')">&#8592;</button>' : '';
        var nextBtn = s!=='done' ? '<button class="btn btn-primary btn-sm" onclick="event.stopPropagation();QM.moveTask('+t.id+',\''+nextS+'\')">&#8594;</button>' : '';
        var prog=''; if(t.subtask_count>0){var pct=Math.round(t.subtask_done/t.subtask_count*100);prog='<div class="tc-progress" style="margin-top:4px"><div class="progress-track"><div class="progress-fill" style="width:'+pct+'%;background:'+(t.subtask_done===t.subtask_count?'var(--green)':'var(--blue)')+'"></div></div><div class="progress-text">'+t.subtask_done+'/'+t.subtask_count+'</div></div>';}
        card.innerHTML='<div class="tc-main"><div class="tc-prio">'+(PRIO_ICON[t.priority]||'')+'</div><div class="tc-body"><div class="tc-title">'+esc(t.title)+'</div><div class="tc-meta" style="margin-top:3px">'+(t.category?'<span>'+esc(t.category)+'</span>':'')+dlBadge(t)+'</div>'+prog+'<div style="display:flex;gap:4px;margin-top:6px">'+prevBtn+nextBtn+'<button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="event.stopPropagation();QM.openEdit('+t.id+')">&#9998;</button></div></div></div>';
        card.onclick=function(){QM.openEdit(t.id);}; body.appendChild(card);
      });
    });
  }).catch(function(e){board.innerHTML='<div class="empty"><div class="empty-text">Erreur: '+esc(e.message)+'</div></div>';});
}

function moveTask(id, status) {
  apiFetch('/task/'+id, {m:'PUT',b:{status:status}}).then(function(){loadKanban();loadTasks();});
}

// ── Accordion ────────────────────────────────────────────────────────────────
function toggleAcc(id) {
  var body=g(id+'-body'), arrow=g(id+'-arrow');
  var open=body.classList.toggle('open');
  if(arrow) arrow.classList.toggle('open',open);
}
function openAcc(id) {
  var body=g(id+'-body'), arrow=g(id+'-arrow');
  if(body&&!body.classList.contains('open')){body.classList.add('open');if(arrow)arrow.classList.add('open');}
}

// ── Prio / Status ────────────────────────────────────────────────────────────
function setPrio(prefix, val, btn) {
  if(prefix==='add') addPrio=val; else editPrio=val;
  g(prefix+'-prio-seg').querySelectorAll('.seg-btn').forEach(function(b){b.classList.remove('active');});
  btn.classList.add('active');
}
function setStatus2(val, btn) {
  editStatus=val;
  g('edit-status-seg').querySelectorAll('.seg-btn').forEach(function(b){b.classList.remove('active');});
  btn.classList.add('active');
}

// ── Days ─────────────────────────────────────────────────────────────────────
function buildDayPicker(prefix) {
  var c=g(prefix+'-days-picker'); if(!c) return; c.innerHTML='';
  DAYS_FR.forEach(function(lbl,i){
    var b=document.createElement('button'); b.className='day-btn'; b.textContent=lbl; b.dataset.d=DAYS_EN[i];
    b.onclick=(function(d,btn){return function(){btn.classList.toggle('active');var arr=prefix==='add'?addDays:editDays,x=arr.indexOf(d);if(x>=0)arr.splice(x,1);else arr.push(d);};})(DAYS_EN[i],b);
    c.appendChild(b);
  });
}
function toggleDays(prefix) {
  var v=g(prefix+'-recur').value, w=g(prefix+'-days-wrap');
  if(w) w.style.display=v==='custom'?'block':'none';
}
function clearReminder() { g('edit-reminder').value=''; }

// ── Edit ──────────────────────────────────────────────────────────────────────
function openEdit(id) {
  curTaskId=id;
  apiFetch('/task/'+id).then(function(t){
    g('edit-modal-title').textContent=t.title;
    g('edit-title').value=t.title||''; g('edit-desc').value=t.description||'';
    var sel=g('edit-cat'); for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===t.category){sel.selectedIndex=i;break;}}
    editPrio=t.priority||'normal';
    var pmap={low:'Basse',normal:'Normal',high:'Haute',urgent:'Urgent'};
    g('edit-prio-seg').querySelectorAll('.seg-btn').forEach(function(b){b.classList.toggle('active',b.textContent.trim()===(pmap[editPrio]||'Normal'));});
    editStatus=t.status||'todo';
    var smap={todo:'A faire',in_progress:'En cours',done:'Termine'};
    g('edit-status-seg').querySelectorAll('.seg-btn').forEach(function(b){b.classList.toggle('active',b.textContent.trim()===smap[editStatus]);});
    g('edit-reminder').value=t.reminder?fmtDateInput(t.reminder):'';
    var rb=g('acc-remind-badge'); if(rb) rb.textContent=t.reminder?fmtDate(t.reminder):'';
    g('edit-recur').value=t.recurrence||''; editDays=[];
    if(t.recurrence==='custom'&&t.recurrence_days){try{editDays=JSON.parse(t.recurrence_days);}catch(e){}}
    toggleDays('edit');
    g('edit-days-picker').querySelectorAll('.day-btn').forEach(function(b){b.classList.toggle('active',editDays.indexOf(b.dataset.d)>=0);});
    if(t.reminder||(t.recurrence&&t.recurrence!=='')) openAcc('acc-remind');
    renderSubs(t.subtasks||[]);
    if(t.subtasks&&t.subtasks.length>0) openAcc('acc-subs');
    g('edit-overlay').classList.add('open'); g('edit-title').focus();
  }).catch(function(e){toast('Erreur: '+e.message,'err');});
}

function closeEdit() {
  g('edit-overlay').classList.remove('open'); curTaskId=null; loadTasks(); if(curView==='kanban')loadKanban();
}
function overlayClose(id,e){if(e.target===g(id)){g(id).classList.remove('open');if(id==='edit-overlay'){curTaskId=null;loadTasks();}}}

function saveEdit() {
  if(!curTaskId) return;
  var ti=g('edit-title').value.trim(); if(!ti){toast('Titre obligatoire !','err');return;}
  var rv=g('edit-reminder').value, rec=g('edit-recur').value;
  apiFetch('/task/'+curTaskId,{m:'PUT',b:{title:ti,description:g('edit-desc').value,category:g('edit-cat').value,priority:editPrio,status:editStatus}})
  .then(function(){return apiFetch('/task/'+curTaskId+'/reminder',{m:'PUT',b:{reminder:rv?rv+':00':null}});})
  .then(function(){return apiFetch('/task/'+curTaskId+'/recurrence',{m:'PUT',b:{recurrence:rec||'none',recurrence_days:rec==='custom'?JSON.stringify(editDays):null}});})
  .then(function(){toast('Mise a jour !','ok');closeEdit();})
  .catch(function(e){toast('Erreur: '+e.message,'err');});
}

// ── Create ───────────────────────────────────────────────────────────────────
function createTask() {
  var ti=g('add-title').value.trim(), msg=g('add-msg'); if(!ti){msg.textContent='Titre obligatoire !';return;}
  var rv=g('add-reminder').value, rec=g('add-recur').value;
  apiFetch('/task',{m:'POST',b:{title:ti,description:g('add-desc').value,category:g('add-cat').value,priority:addPrio,reminder:rv?rv+':00':null}})
  .then(function(t){if(rec)return apiFetch('/task/'+t.id+'/recurrence',{m:'PUT',b:{recurrence:rec,recurrence_days:rec==='custom'?JSON.stringify(addDays):null}}).then(function(){return t;});return t;})
  .then(function(){toast('Tache creee !','ok');g('add-title').value='';g('add-desc').value='';g('add-reminder').value='';g('add-recur').value='';addPrio='normal';g('add-prio-seg').querySelectorAll('.seg-btn').forEach(function(b,i){b.classList.toggle('active',i===1);});msg.textContent='';switchView('list');})
  .catch(function(e){msg.textContent='Erreur: '+e.message;});
}
function openNew(){switchView('add');document.querySelectorAll('.tab').forEach(function(t,i){t.classList.toggle('active',i===2);});}

// ── Delete/Archive ───────────────────────────────────────────────────────────
function deleteTask(){if(!curTaskId||!confirm('Supprimer ?'))return;apiFetch('/task/'+curTaskId,{m:'DELETE'}).then(function(){toast('Supprimee','ok');closeEdit();}).catch(function(e){toast(e.message,'err');});}
function archiveTask(){if(!curTaskId)return;apiFetch('/task/'+curTaskId+'/archive',{m:'POST'}).then(function(){toast('Archivee','ok');closeEdit();}).catch(function(e){toast(e.message,'err');});}
function archDone(){if(!confirm('Archiver les terminees ?'))return;apiFetch('/tasks/archive-done',{m:'POST'}).then(function(d){toast(d.archived+' archivee(s)','ok');loadTasks();}).catch(function(e){toast(e.message,'err');});}
function delDone(){if(!confirm('Supprimer les terminees ?'))return;apiFetch('/tasks/delete-done',{m:'DELETE'}).then(function(d){toast(d.deleted+' supprimee(s)','ok');loadTasks();}).catch(function(e){toast(e.message,'err');});}

// ── Archives ──────────────────────────────────────────────────────────────────
function openArchives(){
  g('arch-overlay').classList.add('open');
  var body=g('arch-body'); body.innerHTML='<div class="empty"><div class="empty-icon">&#8987;</div></div>';
  apiFetch('/tasks/archived').then(function(tasks){
    if(!tasks.length){body.innerHTML='<div class="empty"><div class="empty-icon">&#128239;</div><div class="empty-text">Aucune tache archivee</div></div>';return;}
    body.innerHTML=tasks.map(function(t){return '<div style="display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg3);border-radius:var(--radius2);margin-bottom:6px"><div style="flex:1"><div style="font-weight:600;font-size:.88em">'+esc(t.title)+'</div><div style="font-size:.72em;color:var(--text3)">'+esc(t.category||'')+(t.updated?' — '+new Date(t.updated).toLocaleDateString('fr-FR'):'')+'</div></div><button class="btn btn-success btn-sm" onclick="QM.restoreTask('+t.id+')">Restaurer</button><button class="btn btn-danger btn-sm" onclick="QM.deleteArchived('+t.id+')">X</button></div>';}).join('');
  }).catch(function(e){body.innerHTML='<div class="empty"><div class="empty-text">Erreur: '+esc(e.message)+'</div></div>';});
}
function closeArchives(){g('arch-overlay').classList.remove('open');}
function restoreTask(id){apiFetch('/task/'+id+'/unarchive',{m:'POST'}).then(function(){toast('Restauree !','ok');openArchives();loadTasks();});}
function deleteArchived(id){if(!confirm('Supprimer ?'))return;apiFetch('/task/'+id,{m:'DELETE'}).then(function(){toast('Supprimee','ok');openArchives();});}

// ── Subtasks ─────────────────────────────────────────────────────────────────
function renderSubs(subs){
  var listEl=g('subs-list'),pbWrap=g('subs-progress-wrap'),pbFill=g('subs-prog-fill'),pbText=g('subs-prog-text'),badge=g('subs-count-badge');
  var done=subs.filter(function(s){return s.done;}).length,tot=subs.length;
  if(tot>0){var pct=Math.round(done/tot*100);pbFill.style.width=pct+'%';pbFill.style.background=done===tot?'var(--green)':'var(--blue)';pbText.textContent=done+'/'+tot;pbWrap.style.display='block';badge.textContent=done+'/'+tot;}
  else{pbWrap.style.display='none';badge.textContent='';}
  listEl.innerHTML=tot?subs.map(function(s){return '<div class="sub-item"><input type="checkbox" class="sub-cb"'+(s.done?' checked':'')+' onchange="QM.toggleSub('+s.id+')"><span class="sub-text'+(s.done?' done':'')+'">'+esc(s.title)+'</span><button class="sub-del" onclick="QM.deleteSub('+s.id+')">X</button></div>';}).join(''):'<div style="color:var(--text3);font-size:.82em;padding:4px 0">Aucune sous-tache.</div>';
}
function toggleSub(sid){if(!curTaskId)return;apiFetch('/task/'+curTaskId+'/subtask/'+sid+'/toggle',{m:'POST'}).then(function(){apiFetch('/task/'+curTaskId).then(function(t){renderSubs(t.subtasks||[]);});});}
function deleteSub(sid){if(!curTaskId)return;apiFetch('/task/'+curTaskId+'/subtask/'+sid,{m:'DELETE'}).then(function(){apiFetch('/task/'+curTaskId).then(function(t){renderSubs(t.subtasks||[]);});});}
function addSub(){if(!curTaskId)return;var inp=g('new-sub-input'),ti=inp.value.trim();if(!ti)return;apiFetch('/task/'+curTaskId+'/subtask',{m:'POST',b:{title:ti}}).then(function(){inp.value='';apiFetch('/task/'+curTaskId).then(function(t){renderSubs(t.subtasks||[]);});}).catch(function(){toast('Limite 10 sous-taches','err');});}
function genSubsAI(){if(!curTaskId)return;var tt=g('edit-title').value,td=g('edit-desc').value,st=g('subs-ai-status');st.textContent='Generation...';g('subs-ai-box').style.display='none';apiFetch('/task/'+curTaskId+'/subtasks/ai',{m:'POST',b:{task_title:tt,task_desc:td}}).then(function(d){aiSugs=d.suggestions||[];if(!aiSugs.length){st.textContent='Aucune suggestion.';return;}st.textContent='';g('subs-ai-list').innerHTML=aiSugs.map(function(s,i){return '<div class="ai-sug-item"><input type="checkbox" id="aisg'+i+'" checked style="accent-color:var(--purple)"><label for="aisg'+i+'" class="ai-sug-label">'+esc(s)+'</label></div>';}).join('');g('subs-ai-box').style.display='block';openAcc('acc-subs');}).catch(function(e){st.textContent='Erreur: '+e.message;});}
function addAISubs(){var p=[];for(var i=0;i<aiSugs.length;i++){var cb=g('aisg'+i);if(cb&&cb.checked){(function(t){p.push(apiFetch('/task/'+curTaskId+'/subtask',{m:'POST',b:{title:t}}).catch(function(){}));})(aiSugs[i]);}}Promise.all(p).then(function(){g('subs-ai-box').style.display='none';g('subs-ai-status').textContent='';apiFetch('/task/'+curTaskId).then(function(t){renderSubs(t.subtasks||[]);});});}

// ── AI ───────────────────────────────────────────────────────────────────────
function openAI(){g('ai-overlay').classList.add('open');}
function closeAI(){g('ai-overlay').classList.remove('open');}
function sendAI(){var tx=g('ai-prompt').value.trim(),res=g('ai-result');if(!tx)return;res.style.display='block';res.textContent='Mistral analyse...';apiFetch('/task/ai',{m:'POST',b:{text:tx}}).then(function(d){res.textContent=d.result;loadTasks();toast('IA traitee !','ok');}).catch(function(e){res.textContent='Erreur: '+e.message;});}

// ── Keyboard ─────────────────────────────────────────────────────────────────
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){closeEdit();closeArchives();closeAI();}
  if((e.ctrlKey||e.metaKey)&&e.key==='n'){e.preventDefault();openNew();}
});

// ── Export ───────────────────────────────────────────────────────────────────

// ── Groq Vision UI ────────────────────────────────────────────────────────────
var pastedImageB64  = null;
var pastedImageMime = "image/png";

function checkGroqStatus() {
  apiFetch("/groq/status").then(function(d) {
    var b = g("groq-status-badge");
    if (!b) return;
    if (d.available) {
      b.textContent = "Groq connecte";
      b.style.color = "var(--green)";
    } else if (!d.has_key) {
      b.textContent = "GROQ_API_KEY manquante dans .env";
      b.style.color = "var(--red)";
    } else {
      b.textContent = "Groq inaccessible";
      b.style.color = "var(--orange)";
    }
  }).catch(function() {
    var b = g("groq-status-badge");
    if (b) { b.textContent = "Erreur"; b.style.color = "var(--red)"; }
  });
}

function openVision() {
  g("vision-overlay").classList.add("open");
  checkGroqStatus();
  pastedImageB64  = null;
  pastedImageMime = "image/png";
  g("vision-img-preview").innerHTML = "";
  g("vision-img-status").textContent = "Coller image Ctrl+V ou cliquer pour choisir";
  g("vision-img-status").style.color  = "var(--text3)";
  g("vision-result").style.display    = "none";
  var vcat = g("vision-cat");
  if (vcat) {
    var opts = '<option value="">Auto (IA choisit)</option>' +
      cats.map(function(c) { return '<option value="' + c.name + '">' + c.name + '</option>'; }).join("");
    vcat.innerHTML = opts;
  }
}

function closeVision() {
  g("vision-overlay").classList.remove("open");
}

document.addEventListener("paste", function(e) {
  if (!g("vision-overlay").classList.contains("open")) return;
  var items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (var i = 0; i < items.length; i++) {
    if (items[i].type.indexOf("image") !== -1) {
      var blob   = items[i].getAsFile();
      var mime   = items[i].type || "image/png";
      var reader = new FileReader();
      reader.onload = (function(m) {
        return function(ev) {
          var dataUrl     = ev.target.result;
          pastedImageB64  = dataUrl.split(",")[1];
          pastedImageMime = m;
          g("vision-img-preview").innerHTML =
            '<img src="' + dataUrl + '" style="max-width:100%;max-height:200px;border-radius:8px;border:1px solid var(--border2)">';
          g("vision-img-status").textContent = "Image prete";
          g("vision-img-status").style.color  = "var(--green)";
        };
      })(mime);
      reader.readAsDataURL(blob);
      e.preventDefault();
      return;
    }
  }
});

function visionChooseFile() {
  var inp = document.createElement("input");
  inp.type   = "file";
  inp.accept = "image/*";
  inp.onchange = function(e) {
    var file = e.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function(ev) {
      var dataUrl     = ev.target.result;
      pastedImageB64  = dataUrl.split(",")[1];
      pastedImageMime = file.type || "image/png";
      g("vision-img-preview").innerHTML =
        '<img src="' + dataUrl + '" style="max-width:100%;max-height:200px;border-radius:8px;border:1px solid var(--border2)">';
      g("vision-img-status").textContent = "Image : " + file.name;
      g("vision-img-status").style.color  = "var(--green)";
    };
    reader.readAsDataURL(file);
  };
  inp.click();
}

function clearVisionImage() {
  pastedImageB64  = null;
  pastedImageMime = "image/png";
  g("vision-img-preview").innerHTML  = "";
  g("vision-img-status").textContent = "Coller image Ctrl+V ou cliquer pour choisir";
  g("vision-img-status").style.color  = "var(--text3)";
}

function sendVision() {
  var prompt = g("vision-prompt").value.trim();
  var defCat = g("vision-cat")     ? g("vision-cat").value     : "";
  var defRem = g("vision-reminder") ? g("vision-reminder").value : "";
  var resEl  = g("vision-result");
  var btn    = g("vision-send-btn");
  if (!prompt) { toast("Decrivez ce que vous voulez faire", "err"); return; }
  btn.textContent = "Analyse en cours...";
  btn.disabled    = true;
  resEl.style.display = "none";
  apiFetch("/tasks/vision", {
    m: "POST",
    b: {
      prompt:           prompt,
      image_b64:        pastedImageB64 || null,
      image_mime:       pastedImageMime,
      default_category: defCat,
      default_reminder: defRem ? defRem + ":00" : null
    }
  }).then(function(d) {
    btn.textContent = "Analyser et creer les taches";
    btn.disabled    = false;
    var html = '<div style="font-size:.85em;color:var(--text2);margin-bottom:10px;padding:8px;background:var(--bg4);border-radius:6px"><strong>Analyse :</strong> ' + esc(d.analysis) + '</div>';
    if (d.tasks && d.tasks.length > 0) {
      html += '<div style="font-weight:600;font-size:.88em;color:var(--green);margin-bottom:8px">' + d.tasks_created + ' tache(s) creee(s) !</div>';
      d.tasks.forEach(function(t) {
        html += '<div style="padding:8px 10px;background:var(--bg4);border-radius:6px;margin-bottom:6px;border-left:3px solid var(--blue)">';
        html += '<div style="font-weight:600;font-size:.88em">' + esc(t.title) + '</div>';
        html += '<div style="font-size:.75em;color:var(--text3);margin-top:2px">' +
          (t.category ? t.category + " | " : "") + t.priority +
          (t.reminder ? " | " + new Date(t.reminder).toLocaleString("fr-FR", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}) : "") +
          '</div>';
        if (t.subtasks && t.subtasks.length > 0) {
          html += '<div style="margin-top:5px">';
          t.subtasks.forEach(function(s) {
            html += '<div style="font-size:.78em;color:var(--text3)">&#9658; ' + esc(s.title) + '</div>';
          });
          html += '</div>';
        }
        html += '</div>';
      });
    } else {
      html += '<div style="color:var(--orange);font-size:.85em">Aucune tache generee. Reformulez votre demande.</div>';
    }
    resEl.innerHTML     = html;
    resEl.style.display = "block";
    loadTasks();
  }).catch(function(e) {
    btn.textContent = "Analyser et creer les taches";
    btn.disabled    = false;
    toast("Erreur Groq : " + e.message, "err");
  });
}

QM.openVision       = openVision;
QM.closeVision      = closeVision;
QM.sendVision       = sendVision;
QM.visionChooseFile = visionChooseFile;
QM.clearVisionImage = clearVisionImage;


// ── Statut moteur IA ─────────────────────────────────────────────────────────
function checkAIStatus() {
  apiFetch("/ai/status").then(function(d) {
    var badge = g("ai-engine-badge");
    if (!badge) return;
    if (d.active !== "none") {
      badge.textContent = "IA : " + d.active;
      badge.style.color = d.groq ? "var(--green)" : "var(--orange)";
      badge.title = d.groq
        ? "Groq " + d.groq_model + " (rapide)"
        : "Ollama/Mistral (local)";
    } else {
      badge.textContent = "IA : aucun moteur";
      badge.style.color = "var(--red)";
    }
  }).catch(function() {});
}
QM.checkAIStatus = checkAIStatus;

QM.selCat=selCat; QM.switchView=switchView; QM.setStatus=setStatus; QM.doSearch=doSearch;
QM.openNew=openNew; QM.openAI=openAI; QM.closeAI=closeAI; QM.sendAI=sendAI;
QM.archDone=archDone; QM.delDone=delDone; QM.openArchives=openArchives; QM.closeArchives=closeArchives;
QM.openEdit=openEdit; QM.closeEdit=closeEdit; QM.saveEdit=saveEdit; QM.overlayClose=overlayClose;
QM.deleteTask=deleteTask; QM.archiveTask=archiveTask;
QM.restoreTask=restoreTask; QM.deleteArchived=deleteArchived;
QM.setPrio=setPrio; QM.setStatus2=setStatus2; QM.toggleDays=toggleDays; QM.clearReminder=clearReminder;
QM.toggleAcc=toggleAcc; QM.buildDayPicker=buildDayPicker;
QM.toggleSub=toggleSub; QM.deleteSub=deleteSub; QM.addSub=addSub;
QM.genSubsAI=genSubsAI; QM.addAISubs=addAISubs; QM.moveTask=moveTask; QM.createTask=createTask;

// Auto-init
init();

})();