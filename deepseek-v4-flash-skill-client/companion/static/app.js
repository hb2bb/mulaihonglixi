'use strict';
const BASE = location.pathname.startsWith('/demo') ? '/demo' : '';
const $ = (q) => document.querySelector(q);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {token:'',cards:[],conversations:[],jobs:[],cardId:localStorage.getItem('qy-card'),conversationId:localStorage.getItem('qy-conversation'),view:'chat',messages:[],busy:false,designBusy:false,design:null,debug:null};
const kindNames = {fact:'稳定事实',preference:'偏好',boundary:'重要边界',relationship:'关系与约定',event:'共同经历'};
let toastTimer;
function toast(text) { $('#toast').textContent=text; $('#toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),4500); }
function errorBox(id,text) { $(id).textContent=text || ''; $(id).classList.toggle('hidden',!text); }
async function api(path,body) {
  const response=await fetch(BASE+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Local-Token':state.token},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || '请求失败');
  return data;
}
function card() { return state.cards.find(c=>c.id===state.cardId); }
function conversation() { return state.conversations.find(c=>c.id===state.conversationId); }
function initial(c) { return (c?.name || '新').slice(-1); }
function rememberSelection() { localStorage.setItem('qy-card',state.cardId || ''); localStorage.setItem('qy-conversation',state.conversationId || ''); }
async function refresh() {
  const snapshot=await api('/api/bootstrap'); Object.assign(state,snapshot);
  if(!card()) state.cardId=state.cards[0]?.id;
  if(!conversation() || conversation().card_id!==state.cardId) state.conversationId=state.conversations.find(c=>c.card_id===state.cardId)?.id;
  rememberSelection(); renderSidebar(); renderHeader();
}
function renderSidebar() {
  $('#card-list').innerHTML=state.cards.map(c=>`<button class="person-row ${c.id===state.cardId?'selected':''}" data-card="${c.id}"><div class="avatar">${esc(initial(c))}</div><div><strong>${esc(c.name)}</strong><small>${c.memory_count} 条记忆 · 独立空间</small></div></button>`).join('');
  $('#conversation-list').innerHTML=state.conversations.filter(c=>c.card_id===state.cardId).map(c=>`<div class="conversation-row ${c.id===state.conversationId?'selected':''}"><button data-conversation="${c.id}">${c.trial?'◇ ':'◌ '}${esc(c.title)}</button><button class="delete-conv" data-delete-conversation="${c.id}" title="删除对话及其来源记忆">×</button></div>`).join('');
}
function renderHeader() {
  const c=card(); $('#header-name').textContent=c?.name || '创建你的第一个人物'; $('#header-avatar').textContent=initial(c);
  $('#header-status').textContent=conversation()?.trial?'独立试聊 · 不写入记忆':`${c?.mood || '独立记忆'} · 本地保存`;
  $('#trial-banner').classList.toggle('hidden',!conversation()?.trial);
  $('#composer-note').textContent=conversation()?.trial?'这段试聊不会写入正式记忆。':state.ready?'这次对话，会被好好记住。':'先在设置中连接 DeepSeek，再开始聊天。';
  $('#send-button').disabled=state.busy || !state.conversationId;
  $('#chat-input').placeholder=c?`有什么想和${c.name}说的？`:'先创建一个人物…';
}
async function chooseCard(id) {
  state.cardId=id; state.conversationId=state.conversations.find(c=>c.card_id===id && !c.trial)?.id || state.conversations.find(c=>c.card_id===id)?.id;
  if(!state.conversationId) { const r=await api('/api/conversation/create',{card_id:id}); state.conversationId=r.conversation.id; await refresh(); }
  state.debug=null; rememberSelection(); renderSidebar(); renderHeader(); await showView('chat');
}
async function loadMessages() {
  if(!state.conversationId) {state.messages=[]; renderMessages();return;}
  const cid=state.conversationId;
  const data=await api('/api/messages?id='+cid);
  if(state.conversationId!==cid) return;
  state.messages=data.messages;
  const last=[...state.messages].reverse().find(m=>m.role==='assistant' && m.debug && m.debug!=='{}');
  state.debug=last?JSON.parse(last.debug):null;
  renderMessages();
}
function renderMessages() {
  const c=card();
  if(!state.messages.length) {
    $('#messages').innerHTML=`<div class="welcome"><div class="avatar large">${esc(initial(c))}</div><div class="tiny">A LITTLE SPACE, JUST FOR YOU</div><h2>${esc(c?.name || '从一段新的相遇开始')}</h2><p>${esc(c?.tagline || '创建一个有独特性格的人物，开始你们的故事。')}</p><div class="welcome-chips"><button class="chip" data-starter="今天想和你聊聊天">今天想和你聊聊天</button><button class="chip" data-starter="说说你最近感兴趣的事？">聊聊你的兴趣</button><button class="chip" data-starter="我们慢慢了解彼此吧">慢慢了解彼此</button></div></div>`;
  } else {
    $('#messages').innerHTML=state.messages.map(m=>`<div class="message ${m.role} ${m.status==='failed'?'failed':''}">${m.role==='assistant'?`<div class="avatar">${esc(initial(c))}</div>`:''}<div class="message-content">${messageBubbles(m)}<div class="message-meta">${esc(new Date(m.created).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}))}${m.forgotten?' · 已排除记忆召回':''}</div>${m.status==='failed'?`<button class="retry" data-retry="${m.id}">发送失败 · 点击重试</button>`:''}</div></div>`).join('');
  }
  if(state.busy && state.busyCid===state.conversationId) $('#messages').insertAdjacentHTML('beforeend',`<div class="message"><div class="avatar">${esc(initial(c))}</div><div class="bubble typing">正在想怎么回应你…</div></div>`);
  $('#messages').scrollTop=$('#messages').scrollHeight;
}
async function showView(view) {
  state.view=view;
  document.querySelectorAll('.view').forEach(el=>el.classList.toggle('hidden',el.id!==view+'-view'));
  document.querySelectorAll('.nav[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  if(view==='chat') await loadMessages();
  if(view==='library') renderLibrary();
  if(view==='memory') await renderMemories();
  if(view==='designer') await ensureDesigner();
}
async function send(content,requestId) {
  if(state.busy) return;
  content=content.trim(); if(!content || !state.conversationId) return;
  if(!state.ready) {openSettings();return;}
  const cid=state.conversationId;
  state.busy=true; state.busyCid=cid; errorBox('#chat-error',''); $('#chat-input').value='';
  if(!requestId) {requestId=crypto.randomUUID();state.messages.push({id:-1,role:'user',content,created:new Date().toISOString(),status:'pending'});}
  renderHeader();renderMessages();
  try {
    const result=await api('/api/chat',{conversation_id:cid,content,request_id:requestId});
    if(state.conversationId===cid) state.debug=result.debug;
  } catch(e) { errorBox('#chat-error',e.message); }
  finally {state.busy=false;await refresh();if(state.view==='chat')await loadMessages();renderHeader();$('#chat-input').focus();}
}
function renderLibrary() {
  $('#library-grid').innerHTML=state.cards.map(c=>`<article class="character-card"><div class="avatar">${esc(initial(c))}</div><h2>${esc(c.name)}<span class="badge">v${c.version}</span></h2><p>${esc(c.tagline)}</p><div class="card-count">${esc(c.gender || '未设定')} · ${c.memory_count} 条记忆 · ${state.conversations.filter(v=>v.card_id===c.id).length} 段对话</div><div class="card-actions"><button class="primary" data-card="${c.id}">开始聊天</button><button class="quiet" data-card-memories="${c.id}">记忆 · ${c.memory_count}</button><button class="quiet" data-edit="${c.id}">编辑</button><button class="quiet" data-copy="${c.id}">复制</button><button class="quiet danger" data-delete-card="${c.id}">删除</button></div></article>`).join('') || '<div class="empty-state">还没有人物。定制一位，或从岑野夏开始。</div>';
}
function modal(title,html) { $('#modal-title').textContent=title;$('#modal-body').innerHTML=html;if(!$('#modal').open)$('#modal').showModal(); }
function closeModal() {$('#modal').close();}
function field(name,label,value='',rows=0,hint='') {return `<label class="field"><span>${esc(label)}</span>${rows?`<textarea name="${name}" rows="${rows}">${esc(value)}</textarea>`:`<input name="${name}" value="${esc(value)}">`}${hint?`<small>${esc(hint)}</small>`:''}</label>`;}
async function editCard(c,fromDraft=false) {
  modal(c.id?'编辑人物设定':'保存人物草稿',`<p class="notice">核心设定始终参与回复，完整背景先核对再按话题精选；正式聊天会自动补充缺失的虚构背景，试聊不保存。修改会保留旧版本；复制人物不会复制记忆。</p><form id="card-form">${field('name','人物名称',c.name)}${field('gender','性别（男／女／自定义）',c.gender || '未设定')}${field('tagline','一句话介绍',c.tagline)}${field('core','核心人格 · 始终生效',c.core,7)}${field('style','聊天风格 · 随人物独立保存',c.style || '',4,'可写表达节奏、幽默、主动程度、如何关心与处理分歧。留空时根据核心人格自然推导，不套统一风格。')}<button type="button" class="quiet" id="generate-style">根据人物卡生成聊天风格</button>${field('details','人生与工作档案 · 可编辑自动补充设定',c.details,5)}${field('rules','聊天表达与边界',c.rules,4)}${field('relationship','关系起点与称呼',c.relationship,3)}<div id="card-error" class="error hidden"></div><div class="form-actions">${c.id?'<button type="button" class="quiet" id="versions-button">历史版本</button>':''}<button class="primary" type="submit">${c.id?'保存修改':'保存并开始聊天'}</button></div></form>`);
  $('#card-form').onsubmit=async e=>{
    e.preventDefault();const button=e.submitter;button.disabled=true;
    try{const data=Object.fromEntries(new FormData(e.target));if(c.id){data.id=c.id;data.version=c.version;}
      const result=await api('/api/card/save',data);closeModal();await refresh();if(fromDraft) toast('人物已保存，试聊记录不会带入正式对话');else toast('人物已保存');await chooseCard(result.card.id);
    }catch(err){errorBox('#card-error',err.message);}finally{button.disabled=false;}
  };
  $('#generate-style').onclick=async e=>{
    const button=e.currentTarget,form=$('#card-form'),save=form.querySelector('[type=submit]');
    button.disabled=true;save.disabled=true;button.textContent='正在理解人物…';errorBox('#card-error','');
    try {
      const result=await api('/api/card/style',Object.fromEntries(new FormData(form)));
      if($('#card-form')===form && $('#modal').open){form.elements.style.value=result.style;toast('风格已生成，可编辑后保存。');}
    } catch(err) {if($('#card-form')===form)errorBox('#card-error',err.message);}
    finally {button.disabled=false;save.disabled=false;button.textContent='根据人物卡生成聊天风格';}
  };
  if(c.id) $('#versions-button').onclick=async()=>{
    const {versions}=await api('/api/versions?id='+c.id);
    modal('人物历史版本',`<p class="notice">恢复旧设定会生成新版本，不回滚聊天或记忆。</p>${versions.map(v=>`<div class="memory-card"><strong>版本 ${v.version}</strong><p class="text-small">${esc(new Date(v.created).toLocaleString())}</p><button class="quiet" data-restore-version="${v.id}">恢复这个版本</button></div>`).join('') || '<p class="text-small">尚无历史版本。</p>'}`);
    $('#modal-body').onclick=async e=>{const id=e.target.dataset.restoreVersion;if(!id)return;const old=JSON.parse(versions.find(v=>v.id===id).data);await editCard({...old,version:c.version});};
  };
}
async function renderMemories() {
  if(!card()){ $('#memory-list').innerHTML='<div class="empty-state">先选择一个人物。</div>';return; }
  const selected=state.cardId;
  const data=await api('/api/memories?id='+selected);
  if(selected!==state.cardId)return;
  $('#memory-title').textContent=`${card().name}记住的点滴`;
  const jobs=state.jobs.filter(j=>j.card_id===selected);
  const pending=jobs.filter(j=>j.status!=='failed').length,failed=jobs.filter(j=>j.status==='failed').length;
  $('#memory-status').textContent=`共 ${data.memories.length} 条记忆${pending?` · ${pending} 项正在整理`:''}${failed?` · ${failed} 项整理失败，可重试`:''}。聊天记录已在本地保存。`;
  const query=$('#memory-search').value.trim().toLowerCase();
  const filtered=data.memories.filter(m=>m.text.toLowerCase().includes(query) || (kindNames[m.kind] || '').includes(query));
  $('#memory-list').innerHTML=filtered.map(m=>{
    const source=JSON.parse(m.source_ids).map(id=>data.sources[id]).filter(Boolean);
    return `<article class="memory-card"><span class="tag">${esc(kindNames[m.kind] || m.kind)}</span><p>${esc(m.text)}</p><div class="memory-meta">更新于 ${esc(new Date(m.updated).toLocaleString())} · ${source.length?'来自你的聊天':'手动记录'}</div>${source.length?`<details class="text-small"><summary>查看来源</summary>${source.map(s=>`<p>${esc(s.content)}</p>`).join('')}</details>`:''}<div class="memory-actions"><button class="quiet" data-edit-memory="${m.id}">更正</button><button class="quiet danger" data-delete-memory="${m.id}">删除</button></div></article>`;
  }).join('') || '<div class="empty-state"><div class="empty-symbol">◈</div>还没有长期记忆。<br>认真聊过的偏好、约定与重要事情，会慢慢留在这里。</div>';
  state.memories=data.memories;
  if(query && !filtered.length) $('#memory-list').innerHTML='<div class="empty-state">没有匹配的记忆。</div>';
  if(failed) $('#memory-status').textContent+=' '+jobs.filter(j=>j.status==='failed').map(j=>j.error).join(' ');
}
function editMemory(m={}) {
  if(!card())return;
  const cid=state.cardId;
  modal(m.id?'更正记忆':'添加记忆',`<form id="memory-form"><label class="field"><span>类型</span><select name="kind">${Object.entries(kindNames).map(([k,v])=>`<option value="${k}" ${m.kind===k?'selected':''}>${v}</option>`).join('')}</select></label>${field('text','记住什么',m.text || '',5)}<p class="notice">更正后旧来源将退出召回，避免旧信息重新出现。聊天记录本身仍可查看。</p><div id="memory-error" class="error hidden"></div><div class="form-actions"><button class="primary">保存记忆</button></div></form>`);
  $('#memory-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/memory/save',{...Object.fromEntries(new FormData(e.target)),card_id:cid,...(m.id?{id:m.id}:{})});closeModal();await refresh();await renderMemories();}catch(err){errorBox('#memory-error',err.message);}};
}
async function ensureDesigner(reset=false) {
  if(reset){state.design=null;localStorage.removeItem('qy-design');}
  if(!state.design) {
    const saved=localStorage.getItem('qy-design');
    if(saved){try{state.design=await api('/api/design?id='+saved);}catch{localStorage.removeItem('qy-design');}}
    if(!state.design) state.design=await api('/api/design',{});
    localStorage.setItem('qy-design',state.design.id);
  }
  renderDesigner();
}
function renderDesigner() {
  const d=state.design;if(!d)return;
  $('#design-progress').textContent=`已聊 ${d.history.filter(m=>m.role==='user').length} 个回答`;
  $('#design-messages').innerHTML=d.history.map(m=>`<div class="design-message ${m.role}">${esc(m.content)}</div>`).join('');
  if(state.designBusy)$('#design-messages').insertAdjacentHTML('beforeend','<div class="design-message typing">正在整理你的想法…</div>');
  $('#design-messages').scrollTop=$('#design-messages').scrollHeight;
  $('#design-options').innerHTML=(d.options||[]).map(x=>`<button class="chip" data-option="${esc(x)}" ${state.designBusy?'disabled':''}>${esc(x)}</button>`).join('');
  $('#design-send').disabled=state.designBusy;$('#generate-now').disabled=state.designBusy;
  const draft=d.draft;
  $('#draft-panel').classList.toggle('ready',!!draft);
  $('#draft-panel').innerHTML=draft?`<div class="avatar">${esc(initial(draft))}</div><h3>${esc(draft.name)}</h3><p>${esc(draft.gender || '未设定')} · ${esc(draft.tagline)}</p><div class="draft-core">${esc(draft.core)}</div>${draft.style?`<div class="draft-core">聊天风格：${esc(draft.style)}</div>`:''}<p class="text-small">关系起点：${esc(draft.relationship)}</p><div class="card-actions"><button class="primary" id="save-draft">编辑并保存</button><button class="quiet" id="try-draft">先试聊一下</button></div><p class="text-small">不满意的地方，直接告诉左侧向导即可。</p>`:'<div class="empty-symbol">✧</div><h3>TA 的轮廓，慢慢清晰</h3><p>回答几个问题后，人物草稿会出现在这里。你可以试聊，再调整。</p>';
  if(draft){$('#save-draft').onclick=()=>editCard(draft,true);$('#try-draft').onclick=async()=>{
    const r=await api('/api/card/save',{...draft,name:draft.name+' · 试作'});
    const c=await api('/api/conversation/create',{card_id:r.card.id,title:'人格试聊',trial:true});
    await refresh();state.cardId=r.card.id;state.conversationId=c.conversation.id;rememberSelection();renderSidebar();renderHeader();await showView('chat');toast('试作已创建，不读取或写入正式记忆；可返回定制继续调整');
  };}
}
async function designSend(content) {
  if(state.designBusy || !content.trim())return;
  if(!state.ready){openSettings();return;}
  state.designBusy=true;errorBox('#design-error','');$('#design-input').value='';renderDesigner();
  try{state.design=await api('/api/design',{id:state.design.id,content});}
  catch(e){errorBox('#design-error',e.message);$('#design-input').value=content;}
  finally{state.designBusy=false;renderDesigner();}
}
function openSettings() {
  const w=state.weather || {};
  modal('本地设置',`<p class="notice">聊天、人物与记忆保存在本机。调用 DeepSeek 时，本轮消息和选中的上下文会发送给 API；本应用不另建云端存储。</p><form id="settings-form">${field('api_key','DeepSeek API Key','',0,state.secure_key_storage?'留空保留当前连接。Key 使用 Android Keystore 加密保存在本机，不进入备份。':'留空保留当前连接。新输入的 Key 仅驻留本次服务内存，不进入备份；重启后需重填，或使用已有 .env 配置。')}${field('model','模型名称',state.model)}<label class="checkbox"><input type="checkbox" name="selection_enabled" ${state.selection_enabled?'checked':''}>候选较多或需要回忆时，启用模型精选</label><div class="form-actions"><button type="button" class="quiet" id="test-key">测试当前连接</button><button class="primary">保存设置</button></div><div id="settings-error" class="error hidden"></div></form><section class="section-line"><h3>天气 · 可选联网功能</h3><p class="text-small">默认关闭。启用后仅向 Open-Meteo 发送你填写的经纬度，每30分钟刷新；不会读取设备定位。</p><form id="weather-form"><label class="checkbox"><input type="checkbox" name="enabled" ${w.enabled?'checked':''}>启用天气</label>${field('city','城市名称',w.city || '')}<div class="inline-fields">${field('latitude','纬度',w.latitude ?? '')}${field('longitude','经度',w.longitude ?? '')}</div><button class="quiet" type="submit">保存天气设置</button></form></section><section class="section-line"><h3>数据与备份</h3><p class="text-small">${esc(state.database)}</p><p class="text-small">导出包含人物、聊天和记忆，不包含 API Key。导入会创建独立副本，不覆盖已有数据。</p><div class="settings-actions"><button class="quiet" id="export-data">导出本地备份</button><button class="quiet" id="import-data">导入备份</button><input id="import-file" class="hidden" type="file" accept="application/json,.json"></div></section>`);
  const key=$('#settings-form [name=api_key]');key.type='password';key.autocomplete='off';
  $('#settings-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings',{api_key:key.value,model:$('#settings-form [name=model]').value,selection_enabled:$('#settings-form [name=selection_enabled]').checked});await refresh();key.value='';toast('设置已保存');}catch(err){errorBox('#settings-error',err.message);}};
  $('#test-key').onclick=async e=>{e.target.disabled=true;try{await api('/api/test-key',{});toast('DeepSeek 连接成功');}catch(err){errorBox('#settings-error',err.message);}finally{e.target.disabled=false;}};
  $('#weather-form').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));data.enabled=$('#weather-form [name=enabled]').checked;try{await api('/api/weather',data);await refresh();toast('天气设置已保存');}catch(err){toast(err.message);}};
  $('#export-data').onclick=async()=>{const data=await api('/api/export');if(window.QiyuBackup){window.QiyuBackup.save(JSON.stringify(data));return;}const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='栖语备份-'+new Date().toISOString().slice(0,10)+'.json';a.click();URL.revokeObjectURL(url);};
  $('#import-data').onclick=()=>$('#import-file').click();
  $('#import-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>32000000)throw new Error('备份超过32MB');const data=JSON.parse(await file.text());const r=await api('/api/import',data);await refresh();toast(`已导入 ${r.count} 个人物副本`);if(state.view==='library')renderLibrary();}catch(err){toast(err.message);}};
}
function showDebug() {
  const d=state.debug;
  modal('本轮 · 信息精选',!d?'<p class="notice">发送一条消息后，这里会展示相关信息的检索与精选结果。核心人物设定和近期对话始终保留。</p>':`<div class="debug-list"><p>路径：${esc({skip:'简单消息，跳过检索',local:'本地检索',model:'DeepSeek 精选'}[d.mode] || d.mode)} · 最近 ${d.recent_count} 条消息</p><p>耗时 ${d.seconds} 秒 · 输入约 ${d.input_chars} 字符 · 人物 v${d.card_version}</p>${d.warning?`<p class="notice">${esc(d.warning)}</p>`:''}<p class="text-small">时间：${esc(d.time)}。这里只展示证据与结果，不展示内部提示。</p><details><summary>回复质量检查 · ${d.quality?.attempts || 1} 份候选</summary><pre>${esc(JSON.stringify(d.quality || {},null,2))}</pre></details><h3>最终选中 ${(d.selected||[]).length} 条</h3>${(d.selected||[]).map(c=>`<details><summary>${esc(c.kind)} · ${esc(c.id)}</summary><pre>${esc(c.text)}</pre></details>`).join('')}<details><summary>全部候选 ${(d.candidates||[]).length} 条</summary>${(d.candidates||[]).map(c=>`<p>${esc(c.id)} · 相关度 ${c.score}</p><pre>${esc(c.text)}</pre>`).join('')}</details></div>`);
}
$('#close-modal').onclick=()=>{closeModal();$('#modal-body').onclick=null;};
$('#modal').addEventListener('close',()=>{$('#modal-body').onclick=null;});
$('#chat-form').onsubmit=e=>{e.preventDefault();void send($('#chat-input').value);};
$('#chat-input').addEventListener('keydown',e=>{if(e.key==='Enter' && !e.shiftKey && !e.isComposing){e.preventDefault();void send(e.target.value);}});
$('#design-form').onsubmit=e=>{e.preventDefault();void designSend($('#design-input').value);};
$('#generate-now').onclick=()=>designSend('请根据已有回答生成完整人物卡；未明确的细节由你合理创作。');
$('#design-history').onclick=async()=>{
 const {designs}=await api('/api/designs');
 modal('定制草稿',designs.map(d=>`<div class="conversation-row"><button data-design-id="${d.id}">${esc(d.name)} · ${esc(new Date(d.created).toLocaleDateString())}</button></div>`).join('') || '<p class="text-small">还没有草稿。</p>');
 $('#modal-body').onclick=async e=>{const id=e.target.closest('[data-design-id]')?.dataset.designId;if(!id)return;state.design=await api('/api/design?id='+id);localStorage.setItem('qy-design',id);closeModal();renderDesigner();};
};
$('#restart-design').onclick=()=>{if(!state.designBusy && confirm('开始一份新定制？已有定制仍保存在本地备份中。'))void ensureDesigner(true);};
$('#settings-button').onclick=openSettings;
$('#emoji-button').onclick=()=>{
 const emojis=['🙂','😊','😄','😂','🥹','🥰','😘','😉','😎','🤔','🙃','🥲','😭','😮','😅','😴','🫠','🤗','😤','🙈','👍','👏','🤝','🫶','❤️','💜','✨','🎉','🌻','☕','🍋','🚲'];
 const input=$('#chat-input'),start=input.selectionStart,end=input.selectionEnd;
 modal('选一个表情',`<div class="emoji-grid">${emojis.map(e=>`<button type="button" class="emoji-choice" data-emoji="${e}" aria-label="${e}">${e}</button>`).join('')}</div><p class="text-small">插入输入框后再发送。也可以直接使用系统表情键盘。</p>`);
 $('#modal-body').onclick=e=>{const chosen=e.target.closest('[data-emoji]')?.dataset.emoji;if(!chosen)return;input.setRangeText(chosen,start,end,'end');closeModal();input.focus();};
};
$('#memory-search').oninput=()=>void renderMemories();
$('#manual-create').onclick=()=>editCard({name:'',tagline:'',core:'',details:'',rules:'',relationship:''});
$('#conversations-button').onclick=()=>{
 if(!card())return;
 const rows=state.conversations.filter(c=>c.card_id===state.cardId);
 modal('与'+card().name+'的对话',`<p class="notice">正式对话共享这个人物的长期记忆；试聊独立，不写入记忆。</p><div class="settings-actions"><button class="primary" id="dialog-new-chat">＋ 新对话</button><button class="quiet" id="dialog-new-trial">◇ 独立试聊</button></div>${rows.map(c=>`<div class="conversation-row"><button data-pick-conversation="${c.id}">${c.trial?'◇ ':''}${esc(c.title)}</button></div>`).join('')}`);
 $('#dialog-new-chat').onclick=async()=>{closeModal();$('#new-conversation').click();};
 $('#dialog-new-trial').onclick=async()=>{const r=await api('/api/conversation/create',{card_id:state.cardId,title:'独立试聊',trial:true});state.conversationId=r.conversation.id;closeModal();await refresh();await showView('chat');};
 $('#modal-body').onclick=async e=>{const id=e.target.closest('[data-pick-conversation]')?.dataset.pickConversation;if(!id)return;state.conversationId=id;closeModal();rememberSelection();renderSidebar();renderHeader();await showView('chat');};
};
$('#create-person').onclick=$('#library-create').onclick=()=>showView('designer');
$('#memory-button').onclick=()=>showView('memory');
$('#edit-current').onclick=()=>card() && editCard(card());
$('#debug-button').onclick=showDebug;
$('#new-conversation').onclick=async()=>{if(!card())return;const r=await api('/api/conversation/create',{card_id:state.cardId});state.conversationId=r.conversation.id;await refresh();await showView('chat');};
$('#restore-template').onclick=async()=>{const r=await api('/api/card/default',{});await refresh();await chooseCard(r.card.id);};
$('#add-memory').onclick=()=>editMemory();
$('#retry-jobs').onclick=async()=>{if(!card())return;await api('/api/jobs/retry',{card_id:state.cardId});await refresh();await renderMemories();toast('失败任务已重新排队');};
$('#reset-memory').onclick=async()=>{if(!card() || !confirm('清空此人物全部长期记忆，并将旧聊天退出记忆召回？聊天仍可查看，其他人物不受影响。'))return;await api('/api/memory/reset',{card_id:state.cardId});await refresh();await renderMemories();};
document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  try {
    if(b.dataset.view) await showView(b.dataset.view);
    if(b.dataset.card) await chooseCard(b.dataset.card);
    if(b.dataset.conversation){state.conversationId=b.dataset.conversation;state.debug=null;rememberSelection();renderSidebar();renderHeader();await showView('chat');}
    if(b.dataset.deleteConversation && confirm('删除这段对话及其提取的记忆？此操作不能撤销。')){await api('/api/conversation/delete',{id:b.dataset.deleteConversation});await refresh();await loadMessages();}
    if(b.dataset.starter){$('#chat-input').value=b.dataset.starter;$('#chat-input').focus();}
    if(b.dataset.retry){const m=state.messages.find(m=>String(m.id)===b.dataset.retry);await send(m.content,m.request_id);}
    if(b.dataset.cardMemories){state.cardId=b.dataset.cardMemories;state.conversationId=state.conversations.find(c=>c.card_id===state.cardId)?.id;rememberSelection();renderSidebar();renderHeader();await showView('memory');}
    if(b.dataset.edit) await editCard(state.cards.find(c=>c.id===b.dataset.edit));
    if(b.dataset.copy){const r=await api('/api/card/copy',{id:b.dataset.copy});await refresh();renderLibrary();toast('已复制设定，记忆从空白开始');}
    if(b.dataset.deleteCard && confirm('删除这个人物及全部聊天、记忆和历史版本？此操作不能撤销，建议先备份。')){await api('/api/card/delete',{id:b.dataset.deleteCard});await refresh();renderLibrary();}
    if(b.dataset.editMemory) editMemory(state.memories.find(m=>m.id===b.dataset.editMemory));
    if(b.dataset.deleteMemory && confirm('删除此记忆并排除其旧来源，避免再次被记住？')){await api('/api/memory/delete',{id:b.dataset.deleteMemory,card_id:state.cardId});await refresh();await renderMemories();}
    if(b.dataset.option) await designSend(b.dataset.option);
  }catch(err){toast(err.message);}
});
window.addEventListener('unhandledrejection',e=>{toast(e.reason?.message || '操作失败，请重试');e.preventDefault();});
(async()=>{try{await refresh();await showView('chat');}catch(e){errorBox('#chat-error','本地服务尚未连接：'+e.message);}})();
setInterval(async()=>{if(document.hidden || state.busy || state.designBusy)return;try{await refresh();if(state.view==='memory')await renderMemories();}catch{/* Retry on next poll. */}},6000);

function messageBubbles(message) {
  const content = String(message.content || '');
  const parts = content.trim().split(/\n\s*\n/).filter(Boolean);
  const shortSequence = message.role === 'assistant' && parts.length > 1 && parts.length <= 3 &&
    Array.from(content).length <= 180 && parts.every(part => Array.from(part).length <= 80);
  return (shortSequence ? parts : [content]).map(part => `<div class="bubble">${esc(part)}</div>`).join('');
}
