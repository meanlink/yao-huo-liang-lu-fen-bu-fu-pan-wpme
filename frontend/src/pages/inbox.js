import {briefings} from '../api/entities.js';
import {heading} from '../components/common/shell.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';

const signStatus=s=>s==='signed'?'<span class="sign-state signed">已签收</span>':'<span class="sign-state pending">待签收</span>';

function groupRow(group,mine,deliveryId,detail=false){
 const owned=mine.find(m=>m.group===group.group&&m.is_leader);
 const signed=group.status==='signed';
 return '<li class="sign-row"><div><strong>'+esc(group.group)+'</strong>'+signStatus(group.status)+'</div><p>'+(signed
   ?'签收人 '+esc(group.signed_by_name||group.signed_by)+' · '+date(group.signed_at)+' · 实读 v'+esc(group.read_version)+(group.note?' · '+esc(group.note):'')
   :(detail?'未签收 · 该版未产生已读凭证':'待本组组长签收 · 凭证将记录实际读到的版次 v'+esc(group.version)))+'</p>'
   +(owned&&!signed&&!detail?'<form class="sign-form" data-sign="'+esc(group.id)+'" data-delivery="'+esc(deliveryId)+'" data-group="'+esc(group.group)+'"><label>签收备注（可选）<input name="note" maxlength="500" placeholder="例如：已在班前会宣读"></label><button type="submit" class="primary small">以「'+esc(owned.group)+'」组长身份签收 v'+esc(group.version)+'</button></form>'
   :(owned||detail?'':'<p class="hint">仅本组组长可签收；其他成员请联系组长。</p>'))+'</li>';
}

export async function inboxPage(){
 const data=await briefings.inbox(),mine=data.mine;
 const body=data.briefings.map(b=>{
  const cur=b.current;
  return '<section class="panel briefing"><div class="section-title"><h2>'+esc(b.report_name)+'</h2><span>'+(b.current_version?('当前版 v'+b.current_version+' · 已签 '+b.signed_count+'/'+b.group_count):'尚未落档')+'</span></div>'
   +'<div class="handover '+(b.handover_complete?'done':'open')+'">'+(b.handover_complete?'✓ 当前版已收齐各组签收，交接完成。':'当前版尚未收齐签收，交接未完成。')+'</div>'
   +(cur?'<div class="version-current"><p class="eyebrow">CURRENT VERSION · v'+esc(cur.version)+'</p><p>归档 '+date(cur.archived_at)+' · '+(cur.channel==='correction'?'更正补发':'计划分发')+(cur.supersedes_delivery_id?'（更正，替代第 '+(cur.version-1)+' 版）':'')+' · 收件组 '+cur.groups.length+' 个</p>'+(cur.note?'<p class="hint">'+esc(cur.note)+'</p>':'')+'<ul class="sign-list">'+cur.groups.map(g=>groupRow(g,mine,cur.delivery_id)).join('')+'</ul></div>':'<p class="empty">计划执行落档后，这里会按收件组生成待签记录。</p>')
   +'<details class="history" '+(b.history.length>1?'':'hidden')+'><summary>历版凭证（'+b.history.length+' 版）</summary>'+b.history.map(v=>'<article class="version-history"><div class="section-title"><h3>v'+esc(v.version)+'</h3><span>'+(v.channel==='correction'?'更正补发':'计划分发')+' · '+date(v.archived_at)+'</span></div><p class="hint">'+(v.supersedes_delivery_id?'替代前版 · ':'')+'SHA256 '+esc(v.checksum.slice(0,20))+'… · '+esc(v.filename)+'</p><ul class="sign-list">'+v.groups.map(g=>groupRow(g,mine,v.delivery_id,true)).join('')+'</ul></article>').join('')+'</details>'
   +'</section>';
 }).join('');
 return heading('06 / HANDOVER','班组收件箱','落档后按收件组生成待签记录；组长只签本组，凭证记录实际读到的版次。当前版收齐各组签收才算交接完成。','<button class="button" id="refresh-inbox">刷新收件箱 ↻</button>')
  +'<p class="hint">我的收件组：'+(mine.length?mine.map(m=>esc(m.group)+(m.is_leader?'（组长）':'（成员）')).join('、'):'未加入任何收件组，仅可查看进度。')+'</p>'
  +(body||'<div class="empty">还没有分发计划。请先到分发档案创建计划。</div>');
}

export function bindInbox(refresh){
 document.querySelector('#refresh-inbox').onclick=refresh;
 document.querySelectorAll('[data-sign]').forEach(form=>submit(form,async f=>{
  const group=form.dataset.group;
  await briefings.sign(form.dataset.delivery,{group,note:f.get('note')||''});
  notify('「'+group+'」已签收，凭证记录实读版次');await refresh();
 }));
}
