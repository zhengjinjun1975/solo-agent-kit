// SoloAgentKit 应用逻辑 (从 index.html 拆分, P2-7)

// ===== 常量 =====
const INTENT_NAME = {chat:'对话',clean:'数据清洗',stats:'数据分析',ontology:'本体建模',memory_search:'记忆检索',writing:'写作检查',code_overview:'代码库理解',gen:'生成',setup:'部署',config:'配置',skill:'技能'};

// ===== API =====
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});return r.json();}

// ===== 对话发送（AI 原生：前端把意图+参数传给后端 agent 路由）=====
const input=document.getElementById('chat-input'), scroll=document.getElementById('chat-scroll');
function addMsg(text,cls,intent){scroll.insertAdjacentHTML('beforeend',`<div class="msg ${cls}">${intent?`<div class="intent">⚡ <b>${intent}</b></div>`:''}${esc(text)}</div>`);scroll.scrollTop=scroll.scrollHeight;}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function pretty(o){return JSON.stringify(o,null,2).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
// 各意图 → 友好可读的一句话结果（替代裸 JSON）
function fmtResult(intent, res){
  switch(intent){
    case 'clean': {
      const r=res.report||{}; const out=res.summary||`清洗完成 ${res.input}→${res.output} 行`;
      let line=`✅ ${out}`;
      if(r.dropped_dup)line+=`，去重 ${r.dropped_dup} 行`;
      if(r.dropped_outlier)line+=`，剔除异常 ${r.dropped_outlier} 行`;
      if(r.filled_missing)line+=`，补缺失 ${r.filled_missing} 处`;
      return line;
    }
    case 'stats': {
      const d=res.describe||{};
      let line=`📊 列「${res.column}」：均值 ${d.mean}，中位数 ${d.median}，标准差 ${d.std}`;
      if(res.anomalies&&res.anomalies.length)line+=`，⚠️ 检测到 ${res.anomalies.length} 个异常点`;
      else line+=`，无异常`;
      const cc=res.control_chart||{};
      if(cc.out_of_control&&cc.out_of_control.length)line+=`，控制图 ${cc.out_of_control.length} 点越限`;
      return line;
    }
    case 'ontology': return `🧬 本体建模完成：${res.entities.length} 个实体，${res.triples} 条关系。实体：${(res.entities||[]).join(', ')}`;
    case 'memory_search': {
      const n=(res.results||[]).length;
      if(!n)return '🔍 记忆库无相关条目';
      return `🔍 找到 ${n} 条相关记忆：\n`+(res.results||[]).map(r=>`  · ${r.text}`).join('\n');
    }
    case 'skill': {
      const s=res.skills||[];
      return s.length?`🎯 已有 ${s.length} 个技能：${s.join(', ')}`:'🎯 暂无技能，用「沉淀技能：X」添加';
    }
    case 'writing': return res.passed?`✍️ 写作检查通过（${res.total_issues} 处提示）`:`✍️ 检查发现 ${res.fail_count} 处需修正`;
    case 'code_overview': return `📁 代码库：${res.indexed} 文件，${res.symbols} 符号。核心模块：${(res.overview?.top_core_modules||[]).map(m=>m.file).join(', ')}`;
    case 'gen': return res.output||res.error||'生成完成';
    case 'setup': {
      const c=res.checks||{};
      let line=`🔧 部署检查 ${res.all_ok?'✅ 全部就绪':'⚠️ 有项未就绪'}\n`;
      line+=`  · Python ${c.python?.version||'?'}\n`;
      line+=`  · Ollama ${c.ollama?.ok?'✅ '+((c.ollama.models||[]).join(', ')):'❌ 未运行'}\n`;
      line+=`  · 配置 ${c.config?.ok?'✅':'❌'}\n`;
      line+=`  · 记忆 ${c.memory?.facts||0} 条事实`;
      return line;
    }
    case 'config': {
      if(!res.configured)return `⚠️ ${res.hint||'未配置'}`;
      const l=res.local||{},r=res.remote||{},e=res.embed||{};
      return `⚙️ 模型配置：\n  · 本地 ${l.type}(${l.model||'?'})\n  · 远端 ${r.type?`${r.model}（key从环境变量读）`:'未配置'}\n  · 嵌入 ${e.model||'?'}`;
    }
    case 'capabilities': {
      const f=res.capabilities?.factory||{},p=res.capabilities?.personal||{};
      return `🧩 能力清单：\n  · 工厂套件：${Object.keys(f).join(', ')}\n  · 个人套件：${Object.keys(p).join(', ')}`;
    }
    case 'task': return `📌 已创建任务「${res.goal}」，状态 ${res.state}`;
    default: return res.suggestion||JSON.stringify(res);
  }
}
function addData(msg,cls,o,intent){
  const friendly=fmtResult(intent,o);
  scroll.insertAdjacentHTML('beforeend',
    `<div class="msg ${cls}">${intent?`<div class="intent">⚡ <b>${INTENT_NAME[intent]||intent}</b></div>`:''}<div style="white-space:pre-wrap;line-height:1.8">${esc(friendly)}</div><div class="data" style="display:none">${pretty(o)}</div><div class="detail-toggle" style="font-size:10px;color:var(--mute);cursor:pointer;margin-top:6px" onclick="this.previousElementSibling.style.display=this.previousElementSibling.style.display==='none'?'block':'none'">🔍 查看原始数据</div></div>`);
  scroll.scrollTop=scroll.scrollHeight;
}

async function send(){
  const text=input.value.trim(); if(!text)return;
  addMsg(text,'user'); input.value='';
  addMsg('⏳ 处理中…','ai','');
  const loading=scroll.lastElementChild;
  try{
    // 提取 csv/col 参数（若任务提到文件）
    const csvMatch=text.match(/[\w\-/\\:]+\.csv/);
    const colMatch=text.match(/(?:分析|看|查)\s+(\w+)/);
    const res=await api('/api/agent',{method:'POST',body:JSON.stringify({task:text,csv:csvMatch?csvMatch[0]:null,col:colMatch?colMatch[1]:null})});
    loading.remove();
    if(res.intent==='chat'&&res.suggestion){addMsg(res.suggestion,'ai','chat');}
    else{
      let brief={};
      if(res.intent==='clean')brief.summary=res.summary,brief.report=res.report;
      else if(res.intent==='stats')brief.column=res.column,brief.describe=res.describe,brief.anomalies=res.anomalies,brief.control_chart=res.control_chart;
      else if(res.intent==='ontology')brief.entities=res.entities,brief.triples=res.triples;
      else if(res.intent==='memory_search')brief.results=res.results;
      else if(res.intent==='writing')brief=res;
      else if(res.intent==='code_overview')brief.indexed=res.indexed,brief.overview=res.overview;
      else if(res.intent==='setup'){brief.checks=res.checks,brief.all_ok=res.all_ok;}
      else if(res.intent==='config'){if(res.configured){brief.configured=res.configured;for(const k of ['local','remote','embed'])if(res[k])brief[k]=res[k];}else brief.hint=res.hint;}
      else brief=res;
      addData('完成', 'ai', brief, res.intent);
    }
    loadOverview();
  }catch(e){loading.remove();addMsg('请求失败: '+e.message,'ai','error');}
}
document.getElementById('btn-send').addEventListener('click',send);
input.addEventListener('keydown',e=>{if(e.key==='Enter')send();});
document.getElementById('btn-clear').addEventListener('click',()=>{scroll.innerHTML='';});
document.querySelectorAll('.qc').forEach(q=>q.addEventListener('click',()=>{input.value=q.dataset.q;send();}));

// ===== 导航：每个按钮绑定确定性专用API(不走LLM路由,秒回可靠) =====
// 各模块的执行映射：cap → {fn: 专用执行函数}
async function runClean(csv){ return api('/api/clean',{method:'POST',body:JSON.stringify({csv:csv})}); }
async function runStats(csv, col){ return api('/api/stats?csv='+encodeURIComponent(csv)+(col?'&col='+encodeURIComponent(col):'')); }
async function runOnto(csv, entity, id){ return api('/api/ontology',{method:'POST',body:JSON.stringify({csv:csv,entity:entity||'equip',id:id||'id'})}); }
async function runMemory(){ return api('/api/memory-search?q='+encodeURIComponent('最近')); }
async function runSkill(){ return api('/api/skills'); }
async function runCode(){ return api('/api/code-overview?dir='+encodeURIComponent('solo')); }
async function runSetup(){ return api('/api/setup'); }
async function runConfig(){ return api('/api/config'); }

// 专用执行器（确定性模块，非LLM）
const NAV_EXEC = {
  clean: {intent:'clean', label:'数据清洗', needsData:true},
  stats: {intent:'stats', label:'数据分析', needsData:true},
  ontology:{intent:'ontology', label:'本体建模', needsData:true},
  memory: {fn: runMemory, intent:'memory_search', label:'记忆'},
  skill:  {fn: runSkill, intent:'skill', label:'技能'},
  code:   {fn: runCode, intent:'code_overview', label:'代码库'},
  setup:  {fn: runSetup, intent:'setup', label:'部署'},
  config: {fn: runConfig, intent:'config', label:'配置'},
};

// 执行专用能力并友好显示（确定性, 秒回）
async function execCap(cap){
  const ex=NAV_EXEC[cap]; if(!ex) return;
  // 数据类模块：需先激活(选择数据源)
  if(ex.needsData){ return selectDataSource(cap, ex); }
  addMsg(ex.label,'user');
  addMsg('⏳ 处理中…','ai','');
  const loading=scroll.lastElementChild;
  try{
    const res=await ex.fn();
    loading.remove();
    addData('完成','ai',res,ex.intent);
  }catch(e){
    loading.remove();
    addMsg('❌ 请求失败: '+e.message,'ai','error');
  }
}

// 数据源激活：选择数据文件 → 执行对应模块
async function selectDataSource(cap, ex){
  // 默认示例数据路径
  const defaults={
    clean:'examples/data/factory_sensor.csv',
    stats:'examples/data/factory_sensor.csv',
    ontology:'examples/data/factory_equipment.csv'
  };
  let csv=prompt(`${ex.label} — 输入 CSV 数据文件路径：`, defaults[cap]);
  if(csv===null||csv.trim()==='')return;
  addMsg(`${ex.label}（数据：${csv}）`,'user');
  addMsg('⏳ 处理中…','ai','');
  const loading=scroll.lastElementChild;
  try{
    let res;
    if(cap==='clean') res=await runClean(csv);
    else if(cap==='stats'){
      const col=prompt('选择要分析的数值列（留空自动检测）：','');
      res=await runStats(csv, col||null);
    }else if(cap==='ontology'){
      const ent=prompt('实体名（留空默认）：','equip');
      const idc=prompt('主键列（留空默认id）：','id');
      res=await runOnto(csv, ent, idc);
    }
    loading.remove();
    addData('完成','ai',res,ex.intent);
  }catch(e){
    loading.remove();
    addMsg('❌ 请求失败: '+e.message+'（检查数据文件路径）','ai','error');
  }
}

// ===== 工作区切换：导航点击在右侧渲染对应工作区 =====
function showWorkspace(ws){
  ['status','clean','stats','ontology','writing','code','skill','config','setup'].forEach(id=>{
    const el=document.getElementById('ws-'+id);
    if(el) el.style.display = (id===ws)?'block':'none';
  });
}
// 导航点击：工作台=对话区; 数据模块=数据工作区面板; 其余=右侧面板
document.querySelectorAll('.ni').forEach(n=>n.addEventListener('click',()=>{
  document.querySelectorAll('.ni').forEach(x=>x.classList.remove('on'));n.classList.add('on');
  const cap=n.dataset.cap;
  if(cap==='chat'){ showWorkspace('status'); input.placeholder='自然语言指挥，AI路由全部套件'; input.focus(); return; }
  // 数据模块 + 工作区 → 右侧面板
  if(['clean','stats','ontology','writing','code','skill','config','setup'].includes(cap)){
    showWorkspace(cap);
    if(cap==='clean'){/* 面板自带 */} 
    if(cap==='stats')runStatsDS();
    if(cap==='ontology')runOntoDS();
    if(cap==='skill')loadSkillPanel();
    if(cap==='config')loadConfigPanel();
    if(cap==='setup')loadSetupPanel();
    if(cap==='code')runCodeOverview();
    return;
  }
  input.placeholder='输入任务…';
}));

// ===== 文件浏览→选择→确认 流程 =====
async function browseFile(mod){
  const box=document.getElementById('browse-'+mod);
  box.innerHTML='⏳ 加载文件列表…';
  const res=await api('/api/browse');
  const files=res.files||[];
  box.innerHTML='<div style="color:var(--mute);margin-bottom:4px">选择数据文件：</div>'
    + files.map(f=>`<div onclick="selectFile('${mod}','${f.path}')" style="padding:4px 8px;cursor:pointer;border-radius:6px;background:rgba(59,110,246,.06);margin-bottom:3px">📄 ${f.name} <span style="color:var(--mute)">(${f.path})</span></div>`).join('')
    || '<div style="color:var(--mute)">项目内暂无数据文件</div>';
}
function selectFile(mod, path){
  document.getElementById('ds-'+mod+'-path').value=path;
  document.getElementById('browse-'+mod).innerHTML=`✅ 已选择：${path}`;
}

// ===== 数据源 → 请求体（支持 csv 或 db::table 数据库表）=====
function dsBody(source){
  if(source.includes('::')){
    const [db,table]=source.split('::');
    return {db,table};
  }
  return {csv:source};
}

// ===== 数据清洗工作区（动态列 + 数据源）=====
async function runCleanDS(){
  const out=document.getElementById('clean-result');
  const prev=document.getElementById('clean-preview');
  out.innerHTML='⏳ 清洗中…'; prev.innerHTML='';
  const source=document.getElementById('ds-clean-path').value.trim();
  if(!source){out.innerHTML='⚠️ 请先浏览选择数据文件';return;}
  // 清洗=整表处理（去重/缺失/异常全列），不选列
  const res=await api('/api/clean',{method:'POST',body:JSON.stringify(dsBody(source))});
  if(res.error){out.innerHTML='❌ '+res.error;return;}
  const r=res.report||{};
  out.innerHTML=`<b>清洗完成 ${res.input}→${res.output} 行</b><br>
    · 去重 ${r.dropped_dup||0} · 剔异常 ${r.dropped_outlier||0} · 补缺失 ${r.filled_missing||0}`;
  if(res.sample&&res.sample.length){
    prev.innerHTML='<b>清洗后数据预览（前5行）：</b><br>'+renderTable(res.sample);
  }
}

// ===== 数据分析工作区（动态列 + 数据源）=====
async function runStatsDS(){
  const out=document.getElementById('stats-result');
  const chart=document.getElementById('stats-chart');
  out.innerHTML='⏳ 分析中…'; chart.innerHTML='';
  const source=document.getElementById('ds-stats-path').value.trim();
  if(!source){out.innerHTML='⚠️ 请先浏览选择数据文件';return;}
  const selCol=document.querySelector('input[name="stats-col"]:checked');
  const col=selCol?selCol.value:null;
  const body=dsBody(source);
  const res=await api('/api/stats',{method:'POST',body:JSON.stringify({...body,col})});
  if(res.error){out.innerHTML='❌ '+res.error;return;}
  const d=res.describe||{}, cc=res.control_chart||{};
  // 报表式指标卡片（常规数据工具表达）
  const metric=(label,val,color)=>`<div style="flex:1;min-width:70px;background:#f8fafc;border:1px solid var(--border);border-radius:10px;padding:8px;text-align:center"><div style="font-size:10px;color:var(--mute)">${label}</div><div style="font-size:16px;font-weight:700;color:${color};margin-top:2px">${val}</div></div>`;
  out.innerHTML=`<div style="margin-bottom:8px"><b style="font-size:13px">📊 分析报告 — ${res.column}</b><span style="font-size:11px;color:var(--mute);margin-left:8px">共 ${d.count} 个样本</span></div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
      ${metric('均值', d.mean, 'var(--blue)')}
      ${metric('中位数', d.median, 'var(--blue)')}
      ${metric('标准差', d.std, 'var(--blue)')}
      ${metric('最小值', d.min, 'var(--green)')}
      ${metric('最大值', d.max, 'var(--orange)')}
    </div>
    <div style="font-size:11px;color:var(--mute)">⚠️ ${(res.anomalies||[]).length} 异常点 · 📈 控制图 ${(cc.out_of_control||[]).length} 点越限</div>`;
  chart.innerHTML=drawControlChart(res.column, cc);
}

// SPC 控制图 SVG
function drawControlChart(col, cc){
  if(!cc||cc.ucl===undefined)return'';
  const W=280,H=100,P=12;
  const mean=cc.mean,ucl=cc.ucl,lcl=cc.lcl;
  const pts=cc.points||[];
  const all=[...pts.map(p=>p.value),mean,ucl,lcl];
  const lo=Math.min(...all), hi=Math.max(...all);
  const range=(hi-lo)||1;
  const y=v=>P+(H-2*P)*(1-(v-lo)/(range*1.15));
  const x=i=>P+(pts.length>1?(i*(W-2*P)/(pts.length-1)):(W/2));
  // 数据点折线
  let line='', dots='';
  if(pts.length>1){
    line=pts.map((p,i)=>`${i?'L':'M'}${x(p.index).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
    dots=pts.map(p=>`<circle cx="${x(p.index).toFixed(1)}" cy="${y(p.value).toFixed(1)}" r="2" fill="#2f5ef0"/>`).join('');
  }
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <line x1="${P}" y1="${y(mean)}" x2="${W-P}" y2="${y(mean)}" stroke="#3b6ef6" stroke-width="1.2" stroke-dasharray="4,3"/>
    <line x1="${P}" y1="${y(ucl)}" x2="${W-P}" y2="${y(ucl)}" stroke="#dc2626" stroke-width="1"/>
    <line x1="${P}" y1="${y(lcl)}" x2="${W-P}" y2="${y(lcl)}" stroke="#dc2626" stroke-width="1"/>
    <text x="${W-4}" y="${y(ucl)-2}" fill="#dc2626" font-size="7" text-anchor="end">UCL ${ucl}</text>
    <text x="${W-4}" y="${y(lcl)+8}" fill="#dc2626" font-size="7" text-anchor="end">LCL ${lcl}</text>
    <text x="2" y="${y(mean)-2}" fill="#3b6ef6" font-size="7">μ ${mean}</text>
    ${line?`<path d="${line}" fill="none" stroke="#2f5ef0" stroke-width="1.5" opacity="0.7"/>`:''}
    ${dots}
    ${(cc.out_of_control||[]).map(o=>`<circle cx="${x(o.index).toFixed(1)}" cy="${y(o.value).toFixed(1)}" r="4" fill="#dc2626"/>`).join('')}
  </svg>`;
}

// ===== 本体建模工作区（动态数据源 + SVG 关系图）=====
async function runOntoDS(){
  const out=document.getElementById('onto-result');
  const graph=document.getElementById('onto-graph');
  out.innerHTML='⏳ 建模中…'; graph.innerHTML='';
  const source=document.getElementById('ds-onto-path').value.trim();
  if(!source){out.innerHTML='⚠️ 请先浏览选择数据文件';return;}
  const res=await api('/api/ontology',{method:'POST',body:JSON.stringify({...dsBody(source)})});
  if(res.error){out.innerHTML='❌ '+res.error;return;}
  out.innerHTML=`<b>${res.entities.length} 实体 · ${res.triples} 关系</b><br>${(res.entities||[]).join(' · ')}`;
  graph.innerHTML=drawOntoGraph(res.entities||[]);
}
function drawOntoGraph(entities){
  // 简单网格布局实体节点
  const cols=Math.min(entities.length,4),cw=70,ch=50;
  return `<svg width="${cols*cw}" height="${Math.ceil(entities.length/cols)*ch}" viewBox="0 0 ${cols*cw} ${Math.ceil(entities.length/cols)*ch}">
    ${entities.map((e,i)=>{const x=(i%cols)*cw+5,y=Math.floor(i/cols)*ch+5;
      return `<rect x="${x}" y="${y}" width="${cw-10}" height="${ch-10}" rx="8" fill="#e6edff" stroke="#3b6ef6" stroke-width="1"/><text x="${x+(cw-10)/2}" y="${y+(ch-10)/2+3}" text-anchor="middle" fill="#2f5ef0" font-size="9">${e}</text>`;}).join('')}
  </svg>`;
}
// 渲染数据表格(清洗预览)
function renderTable(rows){
  if(!rows||!rows.length)return'';
  const cols=Object.keys(rows[0]).slice(0,6);
  const head=cols.map(c=>`<th style="padding:2px 6px;text-align:left;border-bottom:1px solid var(--border);color:var(--mute)">${esc(c)}</th>`).join('');
  const body=rows.map(r=>`<tr>${cols.map(c=>`<td style="padding:2px 6px">${esc(r[c]??'')}</td>`).join('')}</tr>`).join('');
  return `<table style="border-collapse:collapse;width:100%;font-size:10px"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

// ===== 写作工作区 =====
async function runWritingCheck(){
  const text=document.getElementById('wr-text').value.trim();
  const out=document.getElementById('wr-result');
  if(!text){out.textContent='请先输入文本';return;}
  out.textContent='⏳ 检查中…';
  const res=await api('/api/writing',{method:'POST',body:JSON.stringify({text})});
  const st=res.dimension_status||{};
  out.innerHTML=`<b>${res.passed?'✅ 通过':'⚠️ 需修正'}</b>（${res.total_issues} 处提示，${res.fail_count} 处必修）<br>`
    +Object.entries(st).map(([d,s])=>`${d}: <span style="color:${s==='pass'?'var(--green)':s==='fail'?'var(--red)':'var(--orange)'}">${s}</span>`).join(' · ')
    +(res.issues&&res.issues.length?`<br><br>${res.issues.map(i=>`<span style="color:${i.severity==='fail'?'var(--red)':'var(--orange)'}">[${i.dim}]</span> ${i.msg}`).join('<br>')}`:'');
}

// ===== 代码工作区 =====
async function runCodeOverview(){
  const out=document.getElementById('code-result');
  out.textContent='⏳ 分析中…';
  const res=await api('/api/code-overview?dir='+encodeURIComponent('solo'));
  const ov=res.overview||{};
  out.innerHTML=`📁 ${res.indexed} 文件，${res.symbols} 符号<br>核心模块：${(ov.top_core_modules||[]).map(m=>m.file).join(', ')||'—'}<br>目录：${Object.entries(ov.files_by_dir||{}).map(([d,n])=>`${d}(${n})`).join(' · ')}`;
}
async function runCodeGen(){
  const prompt=document.getElementById('code-prompt').value.trim();
  const out=document.getElementById('gen-result');
  if(!prompt){out.textContent='请描述要生成的代码';return;}
  out.textContent='⏳ 生成中（本地模型，稍候）…';
  const res=await api('/api/gen',{method:'POST',body:JSON.stringify({kind:'code',topic:prompt})});
  out.textContent=res.output||res.error||'完成';
}

// ===== 技能工作区 =====
async function loadSkillPanel(){
  const res=await api('/api/skills');
  const el=document.getElementById('skill-list');
  const sk=res.skills||[];
  if(!sk.length){el.innerHTML='<div class="stat" style="color:var(--mute)">暂无技能，添加一个可复用经验</div>';return;}
  // 列表式展示每个技能
  el.innerHTML=sk.map(s=>`
    <div style="border:1px solid var(--border);border-radius:10px;padding:10px;margin-bottom:8px;background:#fff">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <b style="font-size:13px;color:var(--blue)">🎯 ${esc(s.name)}</b>
        <span style="font-size:10px;color:var(--mute)">v${s.version||1} · ${(s.ts||'').slice(0,10)}</span>
      </div>
      ${s.trigger&&s.trigger.length?`<div style="font-size:11px;color:var(--mute);margin-top:5px">触发词：${s.trigger.map(esc).join(' · ')}</div>`:''}
      ${s.steps&&s.steps.length?`<div style="font-size:11px;margin-top:4px"><span style="color:var(--mute)">步骤：</span><br>${s.steps.map((st,i)=>`<span style="color:var(--dim)">${i+1}. ${esc(st)}</span>`).join('<br>')}</div>`:''}
    </div>`).join('');
}
async function addSkill(){
  const name=document.getElementById('sk-name').value.trim();
  const trig=document.getElementById('sk-trigger').value.split(',').map(x=>x.trim()).filter(Boolean);
  const steps=document.getElementById('sk-steps').value.split('\n').map(x=>x.trim()).filter(Boolean);
  if(!name||!steps.length){alert('技能名和步骤必填');return;}
  const res=await api('/api/skill-add',{method:'POST',body:JSON.stringify({name,trigger:trig,steps})});
  document.getElementById('sk-name').value='';document.getElementById('sk-trigger').value='';document.getElementById('sk-steps').value='';
  loadSkillPanel(); loadOverview();
}

// ===== 配置工作区 =====
async function loadConfigPanel(){
  const res=await api('/api/config');
  const el=document.getElementById('config-result');
  if(!res.configured){el.textContent=res.hint||'未配置';return;}
  const p=res.config?.provider||{};
  let html='⚙️ 模型分层配置：';
  for(const [tier,meta] of Object.entries(p)){
    html+=`\n【${tier}】\n`;
    for(const [k,v] of Object.entries(meta))html+=`  ${k}: ${v}\n`;
  }
  el.textContent=html;
}

// ===== 部署工作区 =====
async function loadSetupPanel(){
  const res=await api('/api/setup');
  const el=document.getElementById('setup-result');
  const c=res.checks||{};
  el.innerHTML=`<b>部署检查 ${res.all_ok?'✅ 全部就绪':'⚠️ 有项未就绪'}</b><br>`
    +`· Python ${c.python?.version||'?'} ${c.python?.ok?'✅':'❌'}<br>`
    +`· Ollama ${c.ollama?.ok?'✅ '+(c.ollama.models||[]).join(', '):'❌ 未运行'}<br>`
    +`· 配置 ${c.config?.ok?'✅':'❌'}<br>`
    +`· 记忆 ${c.memory?.facts||0} 条事实`;
}

async function loadOverview(){
  try{const m=await api('/api/memory'),s=await api('/api/skills');
    document.getElementById('s-facts').textContent=m.facts||0;
    document.getElementById('s-skills').textContent=(s.skills||[]).length;
    document.getElementById('s-api').textContent='在线';document.getElementById('s-api').style.color='var(--green)';
  }catch(e){document.getElementById('s-api').textContent='离线';document.getElementById('s-api').style.color='var(--red)';}
}
loadOverview();

// ===== 数据源选择 Modal（文件浏览 + 数据库对接）=====
let dsModalTarget='', dsCurrentDir='', dsSelectedSource='';
function openDsModal(mod){
  dsModalTarget=mod; dsSelectedSource='';
  document.getElementById('ds-modal').style.display='flex';
  document.getElementById('ds-selected-info').textContent='';
  browseDir('');
}
function closeDsModal(){document.getElementById('ds-modal').style.display='none';}
async function browseDir(dir){
  dsCurrentDir=dir;
  const box=document.getElementById('ds-file-list');
  box.innerHTML='⏳ 加载…';
  const res=await api('/api/browse?dir='+encodeURIComponent(dir));
  let html='';
  // 盘符导航（硬盘级）
  if(res.drives&&res.drives.length) html+=`<div style="font-size:11px;color:var(--mute);margin-bottom:4px">💽 硬盘：</div>`+(res.drives||[]).map(d=>`<div class="ds-item dir" onclick="browseDir(this.dataset.p)" data-p="${d.path}">💽 ${d.name}</div>`).join('');
  // 上级目录
  if(res.parent) html+=`<div class="ds-item dir" onclick="browseDir(this.dataset.p)" data-p="${res.parent}">📁 .. (上级)</div>`;
  (res.dirs||[]).forEach(d=>{html+=`<div class="ds-item dir" onclick="browseDir(this.dataset.p)" data-p="${d.path}">📁 ${d.name}</div>`;});
  (res.files||[]).forEach(f=>{html+=`<div class="ds-item file" onclick="dsSelectFile(this.dataset.p)" data-p="${f.path}">📄 ${f.name}</div>`;});
  box.innerHTML=html||'<div style="color:var(--mute)">此目录无数据文件</div>';
}
function dsSelectFile(path){
  dsSelectedSource=path;
  document.getElementById('ds-selected-info').textContent='✅ 已选文件：'+path;
  document.getElementById('ds-confirm').disabled=false;
}
function dsConfirm(){
  if(!dsSelectedSource)return;
  const map={clean:'ds-clean-path',stats:'ds-stats-path',ontology:'ds-onto-path'};
  document.getElementById(map[dsModalTarget]).value=dsSelectedSource;
  document.getElementById('browse-'+dsModalTarget).innerHTML=`✅ 已选择：${dsSelectedSource}`;
  closeDsModal();
  // 选择数据源后加载列（清洗/分析需要选列）
  if(dsModalTarget==='clean'||dsModalTarget==='stats'){
    loadColumns(dsModalTarget, dsSelectedSource);
  }
}
// 动态加载列（清洗/分析选列）
async function loadColumns(mod, source){
  const box=document.getElementById(mod+'-cols');
  if(!box)return;
  // 清洗=整表处理(不选列); 只有分析需要选数值列
  if(mod==='clean'){ box.innerHTML=''; return; }
  box.innerHTML='⏳ 检测列…';
  const body = source.includes('::')
    ? (()=>{const [db,table]=source.split('::');return {db,table};})()
    : {csv:source};
  const res=await api('/api/datasource-columns',{method:'POST',body:JSON.stringify(body)});
  if(res.error){box.innerHTML='❌ '+res.error;return;}
  // 默认选中第一个数值列（避免选中非数值列如timestamp导致分析失败）
  const firstNumIdx = (res.columns||[]).findIndex(c => (res.types[c]==='float'||res.types[c]==='integer'));
  const defaultIdx = firstNumIdx >= 0 ? firstNumIdx : 0;
  box.innerHTML='<b>选择分析列：</b> '+(res.columns||[]).map((c,i)=>
    `<label style="margin-right:10px;font-size:12px"><input type="radio" name="${mod}-col" value="${c}" ${i===defaultIdx?'checked':''}> ${c} <span style="color:var(--mute)">(${res.types[c]})</span></label>`).join('')
    +`<div style="color:var(--mute);font-size:11px;margin-top:4px">共 ${res.total_rows} 行</div>`;
}
async function dsConnectDb(){
  const out=document.getElementById('ds-db-result');
  out.innerHTML='⏳ 连接测试中…';
  const db=document.getElementById('ds-db-path').value.trim();
  if(!db){out.innerHTML='⚠️ 请输入数据库文件路径';return;}
  const res=await api('/api/db-connect',{method:'POST',body:JSON.stringify({db})});
  if(!res.ok){out.innerHTML='❌ '+res.error;return;}
  out.innerHTML='✅ 连接成功，表：<br>'+(res.tables||[]).map(t=>
    `<div class="ds-item file" onclick="dsSelectTable('${db}','${t}')">🗄️ ${t}</div>`).join('');
}
function dsSelectTable(db,table){
  dsSelectedSource=db+'::'+table;
  document.getElementById('ds-selected-info').textContent=`✅ 已选数据库表：${table}`;
  document.getElementById('ds-confirm').disabled=false;
}

