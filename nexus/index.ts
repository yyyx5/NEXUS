import { definePluginEntry } from 'openclaw/plugin-sdk/plugin-entry';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';
export default definePluginEntry({id:'local-nexus',name:'Local Nexus',description:'Owner private source-bound structured records; no background model calls.',register(api){
 const root=process.env.NEXUS_ROOT; if(!root)throw new Error('Set NEXUS_ROOT to an isolated Nexus data root');const code=api.rootDir!;
 const settings=JSON.parse(readFileSync(path.join(root,'state/settings.json'),'utf8'));
 const definitions=JSON.parse(readFileSync(path.join(code,'tools.json'),'utf8'));
 const contexts=new Map<string,any>();let child:any=null;let stopped=true;let timer:any=null;let unsub:any=null;
 const eligible=(ctx:any)=>ctx.agentId===settings.agent&&ctx.senderIsOwner===true&&settings.owners[ctx.messageChannel]?.includes(ctx.requesterSenderId);
 api.on('before_tool_call',(event:any,ctx:any)=>{
  if(!definitions.some((d:any)=>d.name===event.toolName)||!ctx.toolCallId)return;
  if(contexts.size>1000)contexts.clear();contexts.set(ctx.toolCallId,ctx);
 });
 const groupInstruction='档案规则：同一次旅行/项目用固定group_id，名称只是别名。先nexus_query group_catalog(name)查档案；同名用日期消歧，不随便新建或合并。新档案用nexus_save主record+group_profile{name,aliases,state,start_date,end_date}，domain=life/work。用户明确说接下来归入/设为当前时在档案卡save/update加context_action=activate；结束时clear或profile.state=closed。当前上下文只限本人本渠道会话，24小时过期；普通聊天不因此自动保存。原话“不属于/不归入/与档案无关”等排除优先，不能因出现名称而关联。记录明确提到档案时指定group_id；省略名字仅在group_context确定且内容属于它时指定group_id、group_relevance=context、匹配domain；工作等无关内容不归入生活旅行。无归属证据保留待归组，别猜。半年后补记用原group_id，事情日期与写入日期分开。查询全部使用group_records并遍历next_cursor，金额用group_summary全组统计，不用一次search代替全组；报价预算承诺分列；possible_financial_without_detail只是候选。';
 const queryInstruction='月度/日期查询用records_by_period或domain_summary_candidates：start含、end不含，整月end必须下月1日。生活domain=life兼容历史生活/旅行，工作domain=work兼容工作。statistics_complete只代表完整SQL统计；returned_count为展开条数，has_more真时有后页，摘要excerpts不是完整原话。报告total_count、undated_count及是否仅展开部分，未确定日期不可猜或当本月事实。trip_costs兼容旧entity_id并与group_summary同组口径，financial_totals仅booked，报价/预算/承诺分开。';
 const completionInstruction='保存回执：按工具user_confirmation说明实际存储、档案、分类及金额状态。verbatim只说原话保存，不能说财务已整理；pending/error不能说完成。文字汇总是快照：金额用group_summary实时统计；查看旧汇总用group_snapshots，needs_update=true要提醒过时。用户明确要求生成/更新汇总时用save/update的summary_for_group，由服务生成版本清单和金额，快照不能作为新交易。检查档案完整性用group_audit并分页，缺关联可核对受控update，疑似费用或重复不能自行新增/合并。Telegram和企业微信同一套规则及数据。duplicate_attachment表示相同图片未重复入账，可查原记录或纠错。图片vision内容属于派生提取，quote仍用真实用户文字；金额/支付/优惠不完整不能猜，原图已归档才作为证据。历史召回先Nexus/Memory/session search找有限候选，Memory摘要只是线索，用绑定source原文核对才引用为原话；未找到不说从未发生，必要时nexus_query archive_history(name=关键词,limit<=3)核对有限本人原始归档SHA及出处，未找到不等于从未说过；禁止加载全Archive。';
 const instruction='Nexus记录规则：用户明确说记一下/帮我记录/生活随手记/工作随手记，使用nexus_save一次批量，第一项kind=record。不要求用户说记一下：本人陈述明确发生的消费、明确要做的待办、确定预约/行程，正常本轮保守调用保存；普通闲聊、提问、假设举例、也许以后做等不主动结构化，Archive-only。明确前缀仍必须保存原话。顶层domain仅life/work/health/unclassified，禁止自行新增personal/finance/task/schedule/travel或其他domain。旅行/冥想/感悟/碎碎念归life，用tags=meditation/reflection/journal/thought及group细分，kind仅用现有record/entity/event/claim。健康就医/症状/用药独立health默认restricted，不因旅行改life；不猜诊断/用途/数值/时间/医学结论。原医院资料/本人自述/医生转述/主观感受/AI解释分清，AI解释不能覆盖原source。用户明确分类优先，其次明显内容、可靠group辅助，拿不准unclassified。life月度总结不得混入work/health/unclassified；健康仅原文明确查询时展开，整体近况仍守敏感健康权限。未分类用unclassified_records分页返回总数/展开数/item_id/时间/has_more，重新分类用update追加revision不复制item。旧旅行底层不批量改写，查询life兼容travel/旅行；新顶层只能用户批准后另行治理。能从明确原话确定日期才填valid_from/time_precision/time_expression，保留原时间表达与Asia/Shanghai；time_expression/due_expression必须摘自用户真实原话连续片段。原话没有时间时valid_from/occurred_date/start_date/due_date留空，消息接收日期不是事情日期；不能把本轮验收备注默认为今天发生，拿不准不猜。金额用minor units，现金券与微信等均为支付组成，一笔消费用完整总额，不拆成多笔。body保留原话，quote必须是当前用户原话的连续片段；若通用record包含转述/混合不确定信息，assertion_kind=unconfirmed、certainty=uncertain；单独转述对象仍为third_party_report、perspective=third_party；可能/听说/主观/计划不能升级确定已发生事实。私人敏感visibility=restricted。只在工具committed=true后说已保存；pending_source说尚未保存等待来源，error说未保存。取消日程先查询定位原schedule，用nexus_update patch.status=deleted，不能创建或追加task；cancelled用回执schedule_state确认，历史可用nexus_search(status=deleted)核对。模糊时间/多目标先列候选，不猜目标；未来安排用nexus_query(template=upcoming_schedules,start/end)，只查有效计划。纠错先nexus_search查询item及revision，再nexus_update；不得另建重复条目。查询仅覆盖已存Nexus，有预算，不能说覆盖全部生活历史。';
 api.on('before_prompt_build',(event:any,ctx:any)=>{
  if(ctx.agentId!==settings.agent||ctx.accountId!==settings.account||!settings.owners[ctx.channel]?.includes(ctx.senderId))return;
  if(ctx.inputProvenance?.kind==='internal_system')return;
  const raw=event.currentUserMessage??event.prompt??'';
  const explicit=/(?:^|\n)\s*(?:记一下|帮我记录|生活随手记|工作随手记)[，,:：\s]/.test(raw);
  const correction=/(刚才|上一条).*(不是|改为|改成|纠正)/.test(raw);
  return{prependSystemContext:instruction+groupInstruction+completionInstruction+queryInstruction,...(explicit||correction?{toolsAllow:definitions.map((d:any)=>d.name),appendContext:'本轮是Nexus记录/纠错请求，只调用Nexus固定工具完成，禁止exec、写Markdown或检查部署。工具不可用或失败时直接说明未保存，不做系统维护。'}:{})};
 });
 api.registerTool((factory:any)=>{
  if(!eligible(factory))return null;
  return definitions.map((d:any)=>({name:d.name,label:d.name,description:d.description,parameters:d.parameters,
   async execute(callId:string,args:any){
    const host=contexts.get(callId);contexts.delete(callId);
    const req=host?.requester;
    const ctx={agentId:host?.agentId??factory.agentId,sessionKey:host?.sessionKey??factory.sessionKey,sessionId:host?.sessionId??factory.sessionId,toolCallId:host?.toolCallId??callId,runId:host?.runId,channel:req?.channel??factory.messageChannel,accountId:req?.accountId??factory.agentAccountId,requesterSenderId:req?.senderId??factory.requesterSenderId,senderIsOwner:req?.senderIsOwner??factory.senderIsOwner,nativeChannelId:factory.nativeChannelId};
    const result=await new Promise((resolve)=>{
     let output='';let finished=false;const proc=spawn(process.env.NEXUS_PYTHON??'python3',[path.join(code,'service.py'),'call','--root',root],{stdio:['pipe','pipe','ignore'],env:{NEXUS_ZSTD_LIBRARY:process.env.NEXUS_ZSTD_LIBRARY,PATH:process.env.PATH??'/usr/bin:/bin',LANG:'en_US.UTF-8',PYTHONDONTWRITEBYTECODE:'1'}});
     const finish=(value:any)=>{if(finished)return;finished=true;clearTimeout(timeout);resolve(value);};
     const timeout=setTimeout(()=>{proc.kill('SIGTERM');finish({status:'error',committed:false,reason:'nexus_timeout',message:'保存状态未确认，可重试或查询；正常聊天可继续。'});},5000);
     proc.stdout.on('data',(buf)=>{output+=buf.toString();if(output.length>16000){proc.kill();finish({status:'error',committed:false,reason:'result_budget'});}});
     proc.on('error',()=>finish({status:'error',committed:false,reason:'service_unavailable'}));proc.on('exit',()=>{try{finish(JSON.parse(output));}catch{finish({status:'error',committed:false,reason:'service_failed'});}});
     proc.stdin.on('error',()=>{});proc.stdin.end(JSON.stringify({tool:d.name,args,ctx})+'\n');
    });
    return{content:[{type:'text',text:JSON.stringify(result)}],details:result};
   }
  }));
 },{names:definitions.map((d:any)=>d.name)});
 const launch=()=>{if(stopped)return;child=spawn(process.env.NEXUS_PYTHON??'python3',[path.join(code,'service.py'),'worker','--root',root],{stdio:['pipe','ignore','ignore'],env:{NEXUS_ZSTD_LIBRARY:process.env.NEXUS_ZSTD_LIBRARY,PATH:process.env.PATH??'/usr/bin:/bin',LANG:'en_US.UTF-8',PYTHONDONTWRITEBYTECODE:'1'}});child.stdin.on('error',()=>{});child.on('error',()=>api.logger.warn('Nexus unavailable; normal chat continues'));child.on('exit',()=>{child=null;if(!stopped)timer=setTimeout(launch,5000);});};
 api.registerService({id:'local-nexus-worker',start(){stopped=false;launch();unsub=api.runtime.events.onSessionTranscriptUpdate((e:any)=>{if(e.target.agentId!==settings.agent||!child?.stdin?.writable||child.stdin.writableLength>65536)return;try{child.stdin.write('{}\n');}catch{}});},stop(){stopped=true;unsub?.();if(timer)clearTimeout(timer);child?.kill('SIGTERM');}});
}});
