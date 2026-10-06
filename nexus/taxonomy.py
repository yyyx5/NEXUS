"""Stable four-domain governance; legacy values are read compatibly."""
import re,json
from binding import Denied
ALIASES={'life':('life','生活','旅行','travel'),'work':('work','工作'),'health':('health','健康'),'unclassified':('unclassified','uncategorized','unknown','未分类')}
CANONICAL={v:k for k,vs in ALIASES.items() for v in vs if v!='personal'}
HEALTH=re.compile(r'健康|体检|就医|检验|检查报告|症状|用药|医生|头疼|头痛|腹痛|肚子痛|疼痛|血压|血糖|心率|体温|发热|咳嗽|服药|挂号|看病|health',re.I)
class Taxonomy:
 def domain_filter(self,domain):
  d=CANONICAL.get(domain)
  if not d:raise ValueError('unknown domain; use life/work/health/unclassified')
  values=[v for v in ALIASES[d] if v!='personal']
  return 'r.domain IN ('+','.join('?' for _ in values)+')',values
 def health_intent(self,raw):return bool(HEALTH.search(raw))
 def visibility_sql(self,alias='r',health=False):
  return "("+alias+".visibility='private' AND "+alias+".domain NOT IN ('health','健康'))" if not health else "("+alias+".visibility='private' AND "+alias+".domain NOT IN ('health','健康') OR "+alias+".domain IN ('health','健康') AND "+alias+".visibility IN ('private','restricted'))"
 def insert_revision(self,p,evidence,**kwargs):
  p=dict(p);old=self.head(kwargs['item_id']) if kwargs.get('item_id') else None;value=p.get('domain','unclassified')
  # A routine correction does not rewrite a historical travel domain.
  if not old or value!=old['domain']:
   if value not in CANONICAL:raise ValueError('AI may not create a top-level domain')
   p['domain']=CANONICAL[value]
  if CANONICAL.get(value)=='health':p['visibility']='restricted'
  return super().insert_revision(p,evidence,**kwargs)
 def filtered_search(self,args):
  # Shared bounded search handles compatibility aliases and explicit health privacy.
  domain=args.get('domain');health=CANONICAL.get(domain)=='health'
  if health and not getattr(self,'_health_access',False):raise Denied('explicit_health_request_required')
  limit=args.get('limit',10)
  if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20 or len(args.get('text',''))>200:raise ValueError('search budget')
  where=[self.visibility_sql(health=health),'r.status=?'];params=[args.get('status','active')]
  if params[0] not in ('active','review','deleted'):raise ValueError('status invalid')
  if domain:clause,values=self.domain_filter(domain);where.append(clause);params.extend(values)
  for key,op in [('start','>='),('end','<')]:
   if args.get(key):where.append('r.valid_from'+op+'?');params.append(args[key])
  if args.get('text'):where.append('instr(r.title||r.body,?)>0');params.append(args['text'])
  if args.get('tag'):where.append('exists(select 1 from json_each(r.tags_json) where value=?)');params.append(args['tag'])
  if args.get('entity'):where.append('exists(select 1 from relation where revision_id=r.revision_id and object_item_id=?)');params.append(args['entity'])
  from base import canon
  rows=self.db.execute('select r.* from item i join revision r on i.head_revision_id=r.revision_id where '+' and '.join(where)+' order by r.created_at desc limit ?',params+[limit+1]).fetchall();hits=[];size=0
  for row in rows[:limit]:
   hit={k:row[k] for k in ('item_id','revision_id','title','assertion_kind','certainty','temporal_status')};hit['domain']=CANONICAL.get(row['domain'],'unclassified');hit['legacy_domain']=row['domain'];hit['status']=row['status'];payload=json.loads(row['payload_json']);schedule=self.db.execute('SELECT * FROM schedule_detail WHERE revision_id=?',(row['revision_id'],)).fetchone()
   if schedule:hit['schedule_state']=payload.get('schedule_state','planned' if row['temporal_status']=='planned' else row['temporal_status']);hit['schedule']={k:schedule[k] for k in schedule.keys() if k!='revision_id'}
   hit['excerpt']=row['body'][:320];hit['source_ids']=[e[0] for e in self.db.execute('select source_id from evidence where revision_id=? limit 5',(row['revision_id'],))];size+=len(canon(hit))
   if size>4000:break
   hits.append(hit)
  return {'hits':hits,'count':len(hits),'truncated':len(hits)<len(rows),'coverage':'matching_current_records_only; health only with explicit health domain and original request'}
