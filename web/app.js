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
  // 聊天开始：隐藏居中的欢迎卡片 + 恢复消息流布局
  const wc=document.getElementById('chat-welcome');
  if(wc){ wc.style.display='none'; scroll.style.justifyContent='flex-start'; scroll.style.alignItems='stretch'; }
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
  ['status','clean','stats','ontology','decisions','writing','code','skill','config','setup','monitor','logs','remote','issue'].forEach(id=>{
    const el=document.getElementById('ws-'+id);
    if(el) el.style.display = (id===ws)?'block':'none';
  });
}

// ===== 导航折叠（点击展开/收起，多组可同时展开）=====
function initNavCollapse(){
  const groups=document.querySelectorAll('.ng');
  groups.forEach((g)=>{
    const lbl=g.querySelector('.lbl');
    if(!lbl) return;
    // 标题加箭头
    if(!lbl.querySelector('.arrow')) lbl.insertAdjacentHTML('beforeend','<span class="arrow">▶</span>');
    // 默认全部展开（多级能力可见）
    g.classList.add('open');
    // 点击独立切换（不收起其他组）
    lbl.addEventListener('click',(e)=>{
      e.stopPropagation();
      const isOpen=g.classList.contains('open');
      if(isOpen){ g.classList.remove('open'); g.classList.add('closed'); }
      else{ g.classList.remove('closed'); g.classList.add('open'); }
    });
  });
}
initNavCollapse();
// 导航点击：工作台=对话区; 数据模块=数据工作区面板; 其余=右侧面板
document.querySelectorAll('.ni').forEach(n=>n.addEventListener('click',()=>{
  document.querySelectorAll('.ni').forEach(x=>x.classList.remove('on'));n.classList.add('on');
  const cap=n.dataset.cap;
  if(cap==='chat'){ 
    document.querySelector('.app').classList.remove('writing');
    showWorkspace('status'); input.placeholder='自然语言指挥，AI路由全部套件'; input.focus(); return; }
  // 写作 → 主区 Canvas 模式（方向B）
  if(cap==='writing'){
    document.querySelector('.app').classList.add('writing');
    showWorkspace('writing');   // 显示右侧写作辅助面板
    return;
  }
  // 非写作能力 → 移除 Canvas 模式（回到三栏对话布局）
  document.querySelector('.app').classList.remove('writing');
  // 数据模块 + 工作区 → 右侧面板
  if(['clean','stats','ontology','decisions','code','skill','config','setup','monitor','logs','remote','issue'].includes(cap)){
    showWorkspace(cap);
    // 数据工作区：恢复已选文件显示（不自动执行）
    if(['clean','stats','ontology','decisions'].includes(cap)){
      const sel=dsSelected[cap];
      const box=document.getElementById('browse-'+cap);
      if(sel&&box){
        const files=sel.split(';').filter(Boolean);
        const fnames=files.map(p=>esc(p.split(/[\\\\\\\\\\\\/]/).pop()));
        box.innerHTML=files.length>1
          ? `<div class="ds-file">📄 ${fnames[0]}</div><div style="font-size:10px;color:var(--mute);margin-top:4px">+${files.length-1} 个文件</div>`
          : `<div class="ds-file">📄 ${fnames[0]}</div>`;
      }
      if(cap==='stats'&&sel) loadColumns('stats', sel);
      return;
    }
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
  const sources=dsSelected['clean']||'';
  if(!sources){out.innerHTML='⚠️ 请先选择数据文件';return;}
  const csvs=sources.split(';').map(s=>s.trim()).filter(Boolean);
  // 多文件 → 合并清洗（后端 csvs）
  const res=await api('/api/clean',{method:'POST',body:JSON.stringify(csvs.length>1?{csvs:csvs}:dsBody(csvs[0]))});
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
  const sources=dsSelected['stats']||'';
  if(!sources){out.innerHTML='⚠️ 请先选择数据文件';return;}
  const selCol=document.querySelector('input[name="stats-col"]:checked');
  const col=selCol?selCol.value:null;
  const csvs=sources.split(';').map(s=>s.trim()).filter(Boolean);
  const body = csvs.length>1 ? {csvs:csvs,col:col} : {...dsBody(csvs[0]),col};
  const res=await api('/api/stats',{method:'POST',body:JSON.stringify(body)});
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

// ===== 本体建模工作区（企业级多实体 + 多文件）=====
async function runOntoDS(){
  const out=document.getElementById('onto-result');
  const graph=document.getElementById('onto-graph');
  out.innerHTML='⏳ 建模中…'; graph.innerHTML='';
  const sources=dsSelected['ontology']||'';
  if(!sources){out.innerHTML='⚠️ 请先选择数据文件';return;}
  // 支持多文件（分号分隔）→ 企业级多表本体
  const csvs=sources.split(';').map(s=>s.trim()).filter(Boolean);
  const body = csvs.length===1 ? {...dsBody(csvs[0])} : {csvs:csvs};
  const res=await api(csvs.length>1?'/api/ontology-multi':'/api/ontology',{method:'POST',body:JSON.stringify(body)});
  if(res.error){out.innerHTML='❌ '+res.error;return;}
  if(csvs.length>1){
    // 企业级多实体
    out.innerHTML=`<b>🏭 企业本体 ${res.entities.length} 实体 · ${res.triples} 关系</b><br>
      <span style="color:var(--mute)">${(res.entities||[]).join(' · ')}</span><br>
      <span style="font-size:11px;color:var(--mute)">${res.nodes} 节点 · ${res.edges} 关联边</span>`;
    drawOntoGraph(res.model||res);
  } else {
    out.innerHTML=`<b>${res.entities.length} 实体 · ${res.triples} 关系</b><br>${(res.entities||[]).join(' · ')}`;
    drawOntoGraph(res.model||res.entities);
  }
}
// ===== 企业决策工作区（规则引擎→行动清单）=====
async function runDecisionsDS(){
  const out=document.getElementById('decisions-result');
  out.innerHTML='⏳ 生成决策中…';
  const sources=dsSelected['decisions']||'';
  if(!sources){out.innerHTML='⚠️ 请先选择数据文件';return;}
  const csvs=sources.split(';').map(s=>s.trim()).filter(Boolean);
  const res=await api('/api/decisions',{method:'POST',body:JSON.stringify({csvs:csvs})});
  if(res.error){out.innerHTML='❌ '+res.error;return;}
  const ds=res.decisions||[];
  const levelColor={告急:'#e74c3c',预警:'#e8890c',建议:'#3b6ef6'};
  out.innerHTML=`<div style="margin-bottom:8px"><b style="font-size:13px">🧭 企业决策建议</b><span style="font-size:11px;color:var(--mute);margin-left:8px">${res.total} 条 · 确定性规则 · 可解释</span></div>
    ${ds.length?ds.map(d=>`<div style="border-left:3px solid ${levelColor[d.level]||'#3b6ef6'};background:#f8fafc;border-radius:6px;padding:8px;margin-bottom:6px">
      <div style="font-size:12px"><b>[${d.level}] ${d.action}</b> <span style="color:var(--mute)">${d.module}·${d.name} · ${d.entity}</span></div>
      <div style="font-size:11px;color:var(--mute);margin-top:3px">${esc(d.reason)}</div>
    </div>`).join(''):'<div style="color:var(--green);font-size:12px">✅ 未触发任何决策规则，运营正常</div>'}`;
}
// 企业级本体可视化（ECharts 力导向网络图，融合 SME 方式）
const ONTO_COLORS = ['#2f6bff','#27ae60','#f39c12','#e74c3c','#8e44ad','#16a085','#e67e22','#1abc9c','#c0392b','#7f8c8d'];
function drawOntoGraph(model){
  const el=document.getElementById('onto-graph');
  if(!model || !model.graph || !model.graph.nodes || typeof echarts==='undefined'){
    // 回退：单文件/无graph时显示实体名
    const ents = (model&&model.entities)||(Array.isArray(model)?model:[]);
    el.innerHTML=ents.length?`<div style="font-size:11px;color:var(--mute)">实体：${ents.join(' · ')}</div>`:'';
    return;
  }
  const nodes=model.graph.nodes, edges=model.graph.edges||[];
  const grp={};
  Object.values(nodes).forEach(n=>{ (grp[n.entity]=grp[n.entity]||[]).push(n); });
  const entityList=Object.keys(grp);
  const colorOf=et=>ONTO_COLORS[entityList.indexOf(et)%ONTO_COLORS.length];
  // 三层结构: 企业hub → 实体类节点 → 实例节点
  const idSet=new Set(Object.values(nodes).map(n=>n.entity+':'+n.id));
  // 实例节点（连到对应实体类）
  const data=Object.values(nodes).map(n=>({
    id:n.entity+':'+n.id,
    name:String(n.id).split(':').pop().slice(0,10),
    category:entityList.indexOf(n.entity)+1,  // 分类索引偏移(0=企业)
    symbolSize:n.entity==='Category'?16:10,
    itemStyle:{color:colorOf(n.entity)},
    tooltip:{formatter:`<b>${n.entity}</b> ${n.id}<br/>${Object.entries(n.data||{}).slice(0,3).map(([k,v])=>`${k}: ${v}`).join('<br/>')}`}
  }));
  // 实体类节点（每实体一个，连到企业hub）
  entityList.forEach(et=>{
    data.push({id:'__cls__'+et, name:et, category:entityList.indexOf(et)+1,
      symbolSize:26, symbol:'roundRect',
      itemStyle:{color:colorOf(et),opacity:0.85},
      label:{show:true,fontSize:11,fontWeight:'bold',color:colorOf(et)}});
  });
  // 企业 hub
  data.push({id:'__hub__',name:'企业',category:0,symbolSize:64,itemStyle:{color:'#2f6bff'},
    label:{show:true,fontSize:15,fontWeight:'bold',color:'#fff'}});
  // 边: 企业→实体类 + 实体类→实例 + 原关系边
  const links=[];
  entityList.forEach(et=>{
    links.push({source:'__hub__',target:'__cls__'+et,lineStyle:{color:'#2f6bff',opacity:0.6,width:2},label:{show:false}});
    (grp[et]||[]).forEach(n=>{
      links.push({source:'__cls__'+et,target:et+':'+n.id,lineStyle:{color:colorOf(et),opacity:0.35,width:1},label:{show:false}});
    });
  });
  // 原跨实体关系边
  edges.forEach(e=>{
    if(idSet.has(e.from)&&idSet.has(e.to)) links.push({source:e.from,target:e.to,
      lineStyle:{color:'#ff8c1a',opacity:0.8,width:1.5},label:{show:false}});
  });
  el.innerHTML=`<div id="ontchart" style="height:480px;width:100%"></div>
    <div style="padding:6px 2px;font-size:11px;color:var(--mute)">${Object.keys(nodes).length} 实例 · ${entityList.length} 实体类 · ${edges.length} 跨实体关系 · 拖动缩放 · 悬停看详情</div>
    <div style="padding:2px">${entityList.map(et=>`<span style="display:inline-block;margin-right:12px;font-size:11px;color:var(--dim)"><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${colorOf(et)};margin-right:4px"></i>${et}</span>`).join('')}</div>`;
  if(window._ontChart) window._ontChart.dispose();
  const chart=echarts.init(document.getElementById('ontchart'));
  window._ontChart=chart;
  chart.setOption({
    tooltip:{show:true},
    animationDuration:800,
    series:[{type:'graph', layout:'force', roam:true,
      force:{repulsion:250, edgeLength:[50,110], gravity:0.15, friction:0.6},
      label:{show:true,position:'right',fontSize:9,color:'#1a2233'},
      edgeSymbol:['none','arrow'], edgeSymbolSize:[0,5],
      categories:[{name:'企业',itemStyle:{color:'#2f6bff'}},
        ...entityList.map(et=>({name:et,itemStyle:{color:colorOf(et)}}))],
      data:data, links:links,
      lineStyle:{opacity:0.6,width:1.5,curveness:0.1},
      emphasis:{focus:'adjacency',label:{show:true,fontSize:11,fontWeight:'bold'}}}]
  });
  return '';
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
// ===== 写作画布（主区，方向B）=====
let wcStyle = 'report';
function wcStyleChange(){ wcStyle = document.getElementById('wc-style').value; }
function wcPickStyle(el, st){
  document.querySelectorAll('.style-card').forEach(x=>x.classList.remove('on'));
  el.classList.add('on');
  wcStyle = st;
  const sel = document.getElementById('wc-style');
  sel.value = st;
}
function wcClear(){ document.getElementById('wc-edit').value=''; document.getElementById('wc-result').innerHTML=''; }

// 方案模板 → 填入主题和要点
function wcTpl(kind){
  const t = document.getElementById('wc-topic');
  const p = document.getElementById('wc-points');
  const m = {
    delivery: ['工厂数据采集与分析系统交付方案','需求分析,系统架构,部署计划,验收标准,培训交接'],
    deploy: ['AI 推理环境部署方案','环境检查,模型部署,服务启动,验证,故障处理'],
    diagnostic: ['设备运行诊断报告','数据采集,异常识别,根因分析,处置建议'],
    report: ['车间运行数据周报','产量,能耗,设备状态,异常,趋势'],
  }[kind] || [];
  t.value = m[0]||''; p.value = m[1]||'';
  // 用模板内容直接生成
  wcGenerate();
}

// ===== 部署（真实部署：检查→启动Ollama→验证）=====
async function runDeploy(){
  const out = document.getElementById('setup-result');
  out.innerHTML = '⏳ 部署中…（检查环境 → 启动 Ollama → 验证模型）';
  const res = await api('/api/deploy');
  const steps = res.steps || res.logs || [];
  out.innerHTML = (res.ok?'✅ 部署成功':'⚠️ 部署完成（有告警）') + '<br>'
    + (Array.isArray(steps)?steps.map(s=>esc(s)).join('<br>') : esc(JSON.stringify(res)));
}

// 生成方案（从主题 + 要点，走 /api/gen 文档生成）
async function wcGenerate(){
  const topic = document.getElementById('wc-topic').value.trim();
  const points = document.getElementById('wc-points').value.trim();
  const edit = document.getElementById('wc-edit');
  const out = document.getElementById('wc-result');
  const base = topic || (points? points.split(',')[0] : '');
  if(!base){ out.innerHTML='<div class="wc-check-card">⚠️ 请先输入写作主题</div>'; return; }
  out.innerHTML='<div class="wc-check-card">⏳ 正在生成方案（本地模型，稍候）…</div>';
  try{
    // 用 gen 文档生成（kind=guide），把主题+要点拼进去
    const prompt = (topic?('主题：'+topic+'。'):'') + (points?('要点：'+points+'。'):'') + '请写一份结构完整的方案文档（含背景、目标、方案、步骤、预期效果）。';
    const res = await api('/api/gen',{method:'POST',body:JSON.stringify({kind:'guide',topic:prompt})});
    if(res.output){ edit.value = res.output; out.innerHTML='<div class="wc-check-card" style="color:var(--green)">✅ 已生成方案，可在编辑区继续修改</div>'; }
    else out.innerHTML='<div class="wc-check-card">⚠️ 生成失败：'+(res.error||'无输出')+'</div>';
  }catch(e){ out.innerHTML='<div class="wc-check-card">⚠️ 生成出错：'+esc(e.message||e)+'</div>'; }
}

// 六维自检（走 /api/writing scan）
async function wcCheck(){
  const text = document.getElementById('wc-edit').value.trim();
  const out = document.getElementById('wr-result');
  if(!text){ out.innerHTML='<div class="wc-check-card">⚠️ 请先写内容</div>'; return; }
  out.innerHTML='<div class="wc-check-card">⏳ 检查中…</div>';
  const res = await api('/api/writing',{method:'POST',body:JSON.stringify({text})});
  const st = res.dimension_status||{};
  out.innerHTML=`<div class="wc-check-card"><div class="c-title">${res.passed?'✅ 通过':'⚠️ 需修正'}</div>`
    +`<div>${res.total_issues} 处提示，${res.fail_count} 处必修</div>`
    +`<div style="margin-top:6px">${Object.entries(st).map(([d,s])=>`<span style="display:inline-block;padding:2px 8px;border-radius:12px;margin:2px;background:${s==='pass'?'rgba(21,128,61,.1)':s==='fail'?'rgba(220,38,38,.1)':'rgba(217,119,6,.1)'};color:${s==='pass'?'var(--green)':s==='fail'?'var(--red)':'var(--orange)'};font-size:12px">${d}:${s}</span>`).join('')}</div>`
    +(res.issues&&res.issues.length?`<div style="margin-top:8px">${res.issues.map(i=>`<div class="c-detail"><span style="color:${i.severity==='fail'?'var(--red)':'var(--orange)'}">[${i.dim}]</span> ${esc(i.msg)}</div>`).join('')}</div>`:'')+'</div>';
}

// 按风格改写（走 /api/writing rewrite）
async function wcRewrite(){
  const text = document.getElementById('wc-edit').value.trim();
  const out = document.getElementById('wc-result');
  if(!text){ out.innerHTML='<div class="wc-check-card">⚠️ 请先写内容</div>'; return; }
  out.innerHTML='<div class="wc-check-card">⏳ 按「'+wcStyle+'」风格改写中…</div>';
  const res = await api('/api/writing',{method:'POST',body:JSON.stringify({text, action:'rewrite', style:wcStyle})});
  if(res.rewritten){ document.getElementById('wc-edit').value = res.rewritten; out.innerHTML='<div class="wc-check-card" style="color:var(--green)">✅ 已按「'+wcStyle+'」风格改写</div>'; }
  else out.innerHTML='<div class="wc-check-card">⚠️ 改写失败：'+(res.error||'无输出')+'</div>';
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
let dsMulti=[];  // 多选文件数组（Ctrl/Shift）
let dsSelected={clean:'',stats:'',ontology:'',decisions:''};  // 每工作区独立选中文件
function openDsModal(mod){
  dsModalTarget=mod; dsSelectedSource=''; dsMulti=[];
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
  (res.files||[]).forEach(f=>{html+=`<div class="ds-item file" onclick="dsSelectFile(this.dataset.p, event)" data-p="${f.path}">📄 ${f.name}</div>`;});
  box.innerHTML=html||'<div style="color:var(--mute)">此目录无数据文件</div>';
}
function dsSelectFile(path, evt){
  evt = evt || window.event;
  if(!dsMulti) dsMulti=[];  // 已选文件数组
  if(evt && (evt.ctrlKey || evt.metaKey || evt.shiftKey)){
    // Ctrl/Shift 多选：切换当前文件选中状态
    const i=dsMulti.indexOf(path);
    if(i>=0) dsMulti.splice(i,1); else dsMulti.push(path);
  } else {
    // 单选：清空后选当前
    dsMulti=[path];
  }
  // 更新列表高亮
  document.querySelectorAll('.ds-item.file').forEach(el=>{
    const p=el.dataset.p;
    el.classList.toggle('selected', dsMulti.includes(p));
  });
  dsSelectedSource = dsMulti.join(';');
  const info=document.getElementById('ds-selected-info');
  if(dsMulti.length>1) info.textContent=`✅ 已选 ${dsMulti.length} 个文件（Ctrl+点击可继续多选）`;
  else info.textContent=`✅ 已选文件：${dsMulti[0]||''}`;
  document.getElementById('ds-confirm').disabled = dsMulti.length===0;
}
function dsConfirm(){
  if(!dsSelectedSource)return;
  // 清洗/分析/本体：同类型(文件)可累积多选；数据库表是单一数据源(替换)
  const cur=dsSelected[dsModalTarget];
  const isRdbms = dsSelectedSource.startsWith('rdbms::') || dsSelectedSource.includes('::');
  const curIsRdbms = (cur||'').startsWith('rdbms::') || (cur||'').includes('::');
  if(isRdbms || curIsRdbms){
    // 数据库源：单一替换
    dsSelected[dsModalTarget] = dsSelectedSource;
  } else {
    // 文件：分号累积多选
    dsSelected[dsModalTarget] = cur ? cur+';'+dsSelectedSource : dsSelectedSource;
  }
  // 收缩卡片：简洁显示已选数据源，主体让给执行区
  const box=document.getElementById('browse-'+dsModalTarget);
  const sel=dsSelected[dsModalTarget];
  let label;
  if(sel.startsWith('rdbms::')){
    const parts=sel.split('::');
    label=`<span class="ds-pill">🗄️ ${parts[6]||parts[1]}</span>`;  // 表名
  } else if(sel.includes('::')){
    label=`<span class="ds-pill">🗄️ ${sel.split('::')[1]}</span>`;  // sqlite表
  } else {
    const files=sel.split(';').filter(Boolean);
    const fnames=files.map(p=>esc(p.split(/[\\\\\\/]/).pop()));
    label=files.length>1
      ? `<span class="ds-pill">📄 ${fnames[0]}</span><span class="ds-pill">+${files.length-1}</span>`
      : `<span class="ds-pill">📄 ${fnames[0]}</span>`;
  }
  box.innerHTML=label;
  // 收缩 ds-card（隐藏图标/箭头/标题，只留简洁状态行）
  const card=box.closest('.ds-card');
  if(card){
    card.classList.add('collapsed');
    const icon=card.querySelector('.ds-card-icon'), title=card.querySelector('.ds-card-title'), arrow=card.querySelector('.ds-card-arrow');
    if(icon) icon.style.display='none';
    if(title) title.style.display='none';
    if(arrow) arrow.style.display='none';
  }
  closeDsModal();
  // 选择数据源后加载列（分析需要选列）
  if(dsModalTarget==='stats'){
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
  // 支持多文件（分号分隔 → csvs 数组）
  let body;
  if(source.includes(';')){
    const csvs=source.split(';').map(s=>s.trim()).filter(Boolean);
    body={csvs:csvs};
  } else if(source.includes('::')){
    const [db,table]=source.split('::');
    body={db,table};
  } else {
    body={csv:source};
  }
  const res=await api('/api/datasource-columns',{method:'POST',body:JSON.stringify(body)});
  if(res.error){box.innerHTML='❌ '+res.error;return;}
  // 默认选中第一个数值列（避免选中非数值列如timestamp导致分析失败）
  const firstNumIdx = (res.columns||[]).findIndex(c => (res.types[c]==='float'||res.types[c]==='integer'));
  const defaultIdx = firstNumIdx >= 0 ? firstNumIdx : 0;
  box.innerHTML='<b>选择分析列：</b> '+(res.columns||[]).map((c,i)=>
    `<label style="margin-right:10px;font-size:12px"><input type="radio" name="${mod}-col" value="${c}" ${i===defaultIdx?'checked':''} onchange="if(this.checked&&this.name==='stats-col')runStatsDS()"> ${c} <span style="color:var(--mute)">(${res.types[c]})</span></label>`).join('')
    +`<div style="color:var(--mute);font-size:11px;margin-top:4px">共 ${res.total_rows} 行</div>`;
  // 默认列自动触发分析（仅 stats 且已选文件）
  if(mod==='stats' && dsSelected['stats']) runStatsDS();
}
let _dsDbType='sqlite';
function dsDbType(t){
  _dsDbType=t;
  document.querySelectorAll('.dbtab').forEach(b=>b.classList.remove('pri'));
  const btn=document.querySelector(`.dbtab[data-t="${t}"]`); if(btn) btn.classList.add('pri');
  document.getElementById('db-f-sqlite').style.display = t==='sqlite'?'block':'none';
  document.getElementById('db-f-mysql').style.display = t==='sqlite'?'none':'block';
  document.getElementById('ds-db-result').innerHTML='';
}
async function dsConnectDb(){
  const out=document.getElementById('ds-db-result');
  out.innerHTML='⏳ 连接测试中…';
  if(_dsDbType==='sqlite'){
    const db=document.getElementById('ds-db-path').value.trim();
    if(!db){out.innerHTML='⚠️ 请输入数据库文件路径';return;}
    const res=await api('/api/db-connect',{method:'POST',body:JSON.stringify({db})});
    if(!res.ok){out.innerHTML='❌ '+res.error;return;}
    out.innerHTML='✅ 连接成功，表：<br>'+(res.tables||[]).map(t=>
      `<div class="ds-item file" onclick="dsSelectTable('${db}','${t}')">🗄️ ${t}</div>`).join('');
  } else {
    // MySQL/Postgres 企业数据库
    const host=document.getElementById('rmdb-host').value.trim();
    const user=document.getElementById('rmdb-user').value.trim();
    const dbn=document.getElementById('rmdb-db').value.trim();
    if(!host||!user||!dbn){out.innerHTML='⚠️ 请填写主机/用户名/数据库名';return;}
    const port=document.getElementById('rmdb-port').value.trim();
    const pass=document.getElementById('rmdb-pass').value;
    const res=await api('/api/rdbms-connect',{method:'POST',body:JSON.stringify({
      type:_dsDbType,host,user,password:pass,db:dbn,port:port||undefined})});
    if(!res.ok){out.innerHTML='❌ '+res.error;return;}
    out.innerHTML='✅ 连接成功，表：<br>'+(res.tables||[]).map(t=>
      `<div class="ds-item file" onclick="dsSelectRdbmsTable('${_dsDbType}','${host}','${user}','${encodeURIComponent(pass)}','${dbn}','${t}')">🗄️ ${t}</div>`).join('');
  }
}
function dsSelectRdbmsTable(type,host,user,pass,db,table){
  // 存为企业数据库数据源（供清洗/分析/本体用）
  dsSelectedSource='rdbms::'+type+'::'+host+'::'+user+'::'+pass+'::'+db+'::'+table;
  document.getElementById('ds-selected-info').textContent=`✅ 已选 ${type} 表：${table}`;
  document.getElementById('ds-confirm').disabled=false;
}
function dsSelectTable(db,table){
  dsSelectedSource=db+'::'+table;
  document.getElementById('ds-selected-info').textContent=`✅ 已选数据库表：${table}`;
  document.getElementById('ds-confirm').disabled=false;
}

// ===== 运维工作区（FDE 现场能力）=====
// 环境监控
async function runMonitor(){
  const out=document.getElementById('monitor-result');
  out.innerHTML='⏳ 采集资源…';
  const r=await api('/api/monitor');
  if(r.error){out.innerHTML='❌ '+r.error;return;}
  const cpu=r.cpu||{}, mem=r.memory||{}, proc=r.processes||{}, disk=r.disk||{};
  const bar=(p)=>`<div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;margin-top:4px"><div style="width:${Math.min(100,p||0)}%;height:100%;background:${(p||0)>85?'#e74c3c':(p||0)>70?'#e8890c':'var(--green)'};border-radius:4px"></div></div>`;
  out.innerHTML=`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
      <div style="background:#f8fafc;border:1px solid var(--border);border-radius:10px;padding:12px">
        <div style="font-size:11px;color:var(--mute)">CPU 使用率</div>
        <div style="font-size:24px;font-weight:700;color:var(--blue)">${cpu.percent??'—'}%</div>
        ${bar(cpu.percent)}
        <div style="font-size:10px;color:var(--mute);margin-top:4px">${cpu.cores||'?'} 核</div>
      </div>
      <div style="background:#f8fafc;border:1px solid var(--border);border-radius:10px;padding:12px">
        <div style="font-size:11px;color:var(--mute)">内存使用率</div>
        <div style="font-size:24px;font-weight:700;color:var(--orange)">${mem.percent??'—'}%</div>
        ${bar(mem.percent)}
      </div>
    </div>
    <div style="font-size:11px;color:var(--mute)">磁盘：${(disk.parts||[]).map(p=>`${p.mount} ${p.percent}%`).join(' · ')||'—'}</div>
    <div style="font-size:11px;color:var(--mute);margin-top:6px">进程：${proc.count||'?'} 个 · Top: ${(proc.top||[]).slice(0,4).map(p=>p.name).join(' / ')}</div>`;
}
// 日志诊断
async function runLogs(level){
  const out=document.getElementById('logs-result');
  out.innerHTML='⏳ 加载日志…';
  const q=level?`?level=${level}`:'';
  const r=await api('/api/logs'+q);
  if(r.error){out.innerHTML='❌ '+r.error;return;}
  const logs=r.logs||[];
  const color={INFO:'var(--blue)',WARN:'var(--orange)',ERROR:'var(--red)'};
  out.innerHTML=logs.length?logs.map(l=>`<div style="white-space:pre-wrap"><span style="color:${color[l.level]||'var(--text)'}">[${l.level}]</span> ${esc(l.msg)}</div>`).join('')
    :'<div style="color:var(--mute)">暂无日志</div>';
}
// 远程运维
async function runRemote(action){
  const out=document.getElementById('remote-result');
  const host=document.getElementById('rm-host').value.trim();
  if(!host){out.innerHTML='⚠️ 请输入主机';return;}
  out.innerHTML='⏳ '+({test:'测试连接',exec:'执行命令',logs:'获取日志'}[action]||'执行')+'…';
  const body={action,host,user:document.getElementById('rm-user').value.trim()||undefined};
  if(action!=='test') body.cmd=document.getElementById('rm-cmd').value.trim();
  const r=await api('/api/remote',{method:'POST',body:JSON.stringify(body)});
  if(r.error){out.innerHTML='❌ '+r.error;return;}
  out.innerHTML=action==='test'
    ? `<div style="color:${r.ok?'var(--green)':'var(--red)'};font-weight:600">${r.ok?'✅ 连接成功':'❌ 连接失败'} ${r.host||''}</div>${r.error?`<div style="color:var(--red)">${esc(r.error)}</div>`:''}`
    : `<div style="font-size:11px;color:var(--mute);margin-bottom:6px">${esc(r.command||'')} → 退出码 ${r.exit_code}</div><pre style="white-space:pre-wrap">${esc(r.stdout||r.error||'')}</pre>`;
}
// 工单
async function runIssueNew(){
  const out=document.getElementById('issue-result');
  const problem=document.getElementById('is-problem').value.trim();
  if(!problem){out.innerHTML='⚠️ 请输入问题描述';return;}
  const severity=document.getElementById('is-severity').value;
  out.innerHTML='⏳ 创建工单…';
  const r=await api('/api/task',{method:'POST',body:JSON.stringify({cmd:'new_issue',problem,severity})});
  if(r.error){out.innerHTML='❌ '+r.error;return;}
  out.innerHTML=`<div style="background:#f8fafc;border:1px solid var(--border);border-radius:10px;padding:12px">
    <div style="font-weight:600">📝 工单 #${esc(r.id||'')}</div>
    <div style="font-size:12px;color:var(--mute);margin-top:4px">triage: <b style="color:var(--blue)">${esc(r.triage||'')}</b> · 严重度: ${esc(r.severity||'')}</div>
    <div style="font-size:11px;margin-top:6px">${esc(r.problem||'')}</div>
  </div>`;
  document.getElementById('is-problem').value='';
}
async function runIssueList(){
  const out=document.getElementById('issue-result');
  out.innerHTML='⏳ 加载工单…';
  const r=await api('/api/task?cmd=list_issues');
  if(r.error){out.innerHTML='❌ '+r.error;return;}
  const issues=r.issues||[];
  const stateColor={open:'var(--red)',diagnosed:'var(--orange)',resolved:'var(--green)'};
  out.innerHTML=issues.length?issues.map(i=>`<div style="background:#f8fafc;border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:6px">
    <div style="font-size:12px"><b>#${esc(i.id||'')}</b> <span style="color:var(--mute)">${esc(i.triage||'')}</span> <span style="color:${stateColor[i.state]||'var(--text)'}">[${esc(i.state||'')}]</span></div>
    <div style="font-size:11px;color:var(--mute);margin-top:3px">${esc(i.problem||'')}</div>
  </div>`).join(''):'<div style="color:var(--green)">✅ 无未关闭工单</div>';
}

