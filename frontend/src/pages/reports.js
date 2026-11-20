import {jobs,reports} from '../api/entities.js';
import {download} from '../api/client.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';

export async function reportPage(){
 const [list,deliveries,allJobs,groups]=await Promise.all([reports.list(),reports.deliveries(),jobs.list(),reports.groups()]);workspace.reports=list;
 const approved=allJobs.filter(j=>j.approved&&j.status==='completed'),isAdmin=session.user.role==='admin';
 const jobOptions=approved.map(j=>'<option value="'+j.id+'">'+esc(j.name)+'</option>').join('');
 const groupChoices=groups.map(g=>'<label class="check"><input type="checkbox" name="groups" value="'+esc(g.name)+'" '+((g.leaders.length)?'checked':'')+'><span>'+esc(g.name)+(g.leaders.length?' · 组长 '+esc(g.leaders.map(l=>l.name).join('、')):' · 暂无组长')+'</span></label>').join('');
 return heading('05 / DISTRIBUTION','定时分发与归档','把批准后的结果交付到各收件组的本地收件箱。落档时冻结收件组并生成待签记录；负责人可向原收件组补发更正版。','<button class="button" id="refresh-reports">刷新收件箱 ↻</button>')+'<div class="report-grid"><section class="panel"><div class="section-title"><h2>创建分发计划</h2></div><form id="report-form"><label>简报名称<input name="name" required minlength="2" value="日间业务复核简报"></label><label>已批准分析<select name="job_id" required>'+jobOptions+'</select></label><label>业务接收组标签<input name="destination" value="各窑班 · 本地收件箱" required></label><fieldset class="group-picker"><legend>分发给哪些收件组（每组独立签收）</legend>'+(groupChoices||'<p class="hint">还没有收件组。</p>')+'</fieldset><div class="parameter-grid"><label>分发周期<select name="interval_seconds"><option value="86400">每日</option><option value="604800">每周</option><option value="60">每分钟（验收）</option></select></label><label>首次执行<select name="delay_seconds"><option value="0">立即</option><option value="60">1 分钟后</option><option value="3600">1 小时后</option></select></label></div><button type="submit" class="primary" '+(isAdmin&&approved.length?'':'disabled')+'>保存分发计划</button></form><p class="hint">由后台 worker 按到期时间生成文件。仅负责人可创建或暂停；收件组决定落档后生成的待签记录。</p></section><section><div class="section-title"><h2>运行中的计划</h2><span>'+list.filter(r=>r.enabled).length+' 条已启用</span></div><div class="schedule-list">'+list.map(r=>'<article><div><strong>'+esc(r.name)+'</strong><p>'+esc(r.destination)+'</p><small>下次 '+date(r.next_run)+' · 周期 '+r.interval_seconds+' 秒</small></div><div class="schedule-actions"><button class="button small" data-toggle="'+r.id+'" '+(isAdmin?'':'disabled')+'>'+(r.enabled?'暂停':'启用')+'</button><button class="text-button" data-correct="'+r.id+'" '+(isAdmin&&approved.length?'':'disabled')+'>补发更正版…</button></div></article>').join('')+'</div><form id="correct-form" class="correction" hidden><div class="section-title"><h2>向原收件组补发更正版</h2><button type="button" class="text-button" id="cancel-correct">取消</button></div><p class="hint" id="correct-target"></p><label>更正依据（已批准分析）<select name="job_id" required>'+jobOptions+'</select></label><label>更正说明<input name="note" maxlength="500" placeholder="例如：修正 11 月 3 日夜班统计口径"></label><button type="submit" class="primary">落档更正版并重建待签记录</button></form><section class="panel inbox"><div class="section-title"><h2>本地收件箱</h2><span>'+deliveries.length+' 份归档</span></div>'+deliveries.map(d=>'<div class="delivery"><div><strong>'+esc(d.filename)+'</strong><p>'+esc(d.destination)+' · '+date(d.created_at)+(d.version?' · v'+d.version+(d.channel==='correction'?' 更正':''):'')+'</p><small>SHA256 '+esc(d.checksum.slice(0,24))+'…</small></div><div><button class="text-button" data-download="'+d.id+'" data-format="csv">CSV ↓</button><button class="text-button" data-download="'+d.id+'" data-format="json">JSON ↓</button></div></div>').join('')+(!deliveries.length?'<p class="empty">计划执行后，文件会出现在此处。等待片刻后刷新。</p>':'')+'<p class="hint"><a class="text-link" href="#/inbox">前往班组收件箱查看待签与签收进度 ↗</a></p></section></section></div>';
}
export function bindReports(refresh){
 document.querySelector('#refresh-reports').onclick=refresh;
 submit(document.querySelector('#report-form'),async f=>{
  await reports.create({name:f.get('name'),job_id:Number(f.get('job_id')),destination:f.get('destination'),groups:f.getAll('groups'),interval_seconds:Number(f.get('interval_seconds')),delay_seconds:Number(f.get('delay_seconds'))});
  notify('计划已保存，后台将按到期时间归档');await refresh();
 });
 document.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{try{await reports.toggle(b.dataset.toggle);await refresh();}catch(e){notify(e.message,true);}});
 document.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>download(b.dataset.download,b.dataset.format).catch(e=>notify(e.message,true)));
 const correct=document.querySelector('#correct-form');
 document.querySelectorAll('[data-correct]').forEach(b=>b.onclick=()=>{
  const plan=workspace.reports.find(r=>String(r.id)===b.dataset.correct);
  correct.dataset.report=b.dataset.correct;correct.hidden=false;
  document.querySelector('#correct-target').textContent='计划：'+(plan?.name||'')+' · '+((plan?.destination)||'')+'。更正版会发给该计划当前版的原收件组，旧版已签凭证保留在原版次。';
  correct.scrollIntoView({behavior:'smooth',block:'center'});
 });
 document.querySelector('#cancel-correct').onclick=()=>{correct.hidden=true;correct.dataset.report='';};
 submit(correct,async f=>{
  if(!correct.dataset.report)return;
  await reports.correction(correct.dataset.report,{job_id:Number(f.get('job_id')),note:f.get('note')||''});
  notify('更正版已向原收件组落档，待签记录已重建');correct.hidden=true;await refresh();
 });
}
