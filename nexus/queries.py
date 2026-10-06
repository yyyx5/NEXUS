"""Complete statistics with bounded pages; no raw SQL from callers."""
import datetime as dt
from base import canon

class Queries:
 def period_query(self,args):
  for k in ('start','end'):
   if args.get(k):dt.date.fromisoformat(args[k])
  if args.get('start') and args.get('end') and args['start']>=args['end']:raise ValueError('start must precede exclusive end')
  self.db.execute('begin')
  try:
   health=args.get('domain') in ('health','健康')
   if health and not getattr(self,'_health_access',False):raise ValueError('explicit health request required')
   where=[self.visibility_sql(health=health)];params=[]
   date="coalesce(r.valid_from,(SELECT occurred_date FROM financial_detail f WHERE f.revision_id=r.revision_id),(SELECT start_date FROM schedule_detail s WHERE s.revision_id=r.revision_id))"
   if args['template']=='upcoming_schedules':
    where.extend(["EXISTS(SELECT 1 FROM schedule_detail s WHERE s.revision_id=r.revision_id)","r.temporal_status='planned'","coalesce(json_extract(r.payload_json,'$.schedule_state'),'planned')!='cancelled'"])
    date="(SELECT start_date FROM schedule_detail s WHERE s.revision_id=r.revision_id)"
    args={**args,'start':args.get('start') or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()}
   if args['template']=='unclassified_records':args={**args,'domain':'unclassified'}
   if args.get('domain'):
    clause,values=self.domain_filter(args['domain']);where.append(clause);params.extend(values)
   undated=self.db.execute('SELECT count(*) FROM current_item r WHERE '+' AND '.join(where)+' AND '+date+' IS NULL',params).fetchone()[0]
   for key,op in [('start','>='),('end','<')]:
    if args.get(key):where.append(date+op+'?');params.append(args[key])
   clause=' AND '.join(where)
   counts={r[0]:r[1] for r in self.db.execute('SELECT r.domain,count(*) FROM current_item r WHERE '+clause+' GROUP BY r.domain',params)}
   category="coalesce(json_extract(r.payload_json,'$.category'),CASE WHEN EXISTS(SELECT 1 FROM financial_detail f WHERE f.revision_id=r.revision_id) THEN 'financial' WHEN EXISTS(SELECT 1 FROM task_detail t WHERE t.revision_id=r.revision_id) THEN 'task' WHEN EXISTS(SELECT 1 FROM schedule_detail s WHERE s.revision_id=r.revision_id) THEN 'schedule' ELSE 'uncategorized' END)"
   categories={r[0]:r[1] for r in self.db.execute('SELECT '+category+',count(*) FROM current_item r WHERE '+clause+' GROUP BY '+category,params)}
   sql='SELECT r.item_id,r.revision_id,r.title,r.domain,r.valid_from,'+date+' AS effective_date,r.time_expression,r.assertion_kind,r.certainty,r.temporal_status,substr(r.body,1,160) AS excerpt FROM current_item r WHERE '+clause+' ORDER BY coalesce('+date+',r.created_at),r.item_id'
   key='period:'+canon([args.get('start'),args.get('end'),args.get('domain'),args['template']])
   result=self.page_sql(sql,params,args,key)
   result.update({'total_count':result['total'],'returned_count':result['returned'],'page':result['offset']//args.get('limit',10)+1,'has_more':result['next_cursor'] is not None,'statistics_complete':True,'all_matching_records_returned':result['next_cursor'] is None and result['offset']==0,'expanded_text_complete':False,'excerpt_char_limit':160,'text_mode':'representative_candidates' if args['template']=='domain_summary_candidates' else 'paged_excerpts','domain_counts':counts,'categorized_counts':categories,'uncategorized':categories.get('uncategorized',0),'undated_count':undated,'date_basis':'valid_from, otherwise financial.occurred_date/schedule.start_date; start inclusive/end exclusive; undated not guessed','coverage':'matching_current_active_private_nexus_records_only'})
   from taxonomy import CANONICAL
   display_counts={}
   for name,count in counts.items():
    display=CANONICAL.get(name,'unclassified');display_counts[display]=display_counts.get(display,0)+count
   result['domain_counts']=display_counts
   for hit in result['hits']:
    if args['template']=='upcoming_schedules':
     detail=self.db.execute('SELECT * FROM schedule_detail WHERE revision_id=?',(hit['revision_id'],)).fetchone();hit['schedule']={k:detail[k] for k in detail.keys() if k!='revision_id'};hit['schedule_state']='planned';hit['status']='active'
    hit['legacy_domain']=hit['domain'];hit['domain']=CANONICAL.get(hit['domain'],'unclassified')
   self.db.execute('commit');return result
  except BaseException:self.db.execute('rollback');raise
 def financial_query(self,args):
  template=args['template'];gid=args.get('group_id')
  if template=='trip_costs':
   if gid and args.get('entity_id') and gid!=args['entity_id']:raise ValueError('conflicting trip IDs')
   gid=gid or args.get('entity_id')
   if not gid:raise ValueError('explicit trip/group id required')
  for k in ('start','end'):
   if args.get(k):dt.date.fromisoformat(args[k])
  if args.get('start') and args.get('end') and args['start']>=args['end']:raise ValueError('invalid date range')
  where=[self.visibility_sql()];params=[]
  if gid:
   h=self.head(gid)
   if h['visibility']!='private' or h['status']!='active':raise ValueError('group unavailable')
   import json
   authoritative=bool(json.loads(h['payload_json']).get('nexus_group'))
   predicate='for_group' if authoritative else 'for_trip'
   where.append('EXISTS(SELECT 1 FROM relation e WHERE e.revision_id=r.revision_id AND e.object_item_id=? AND e.predicate=?)');params.extend([gid,predicate])
  if args.get('domain'):
   clause,values=self.domain_filter(args['domain']);where.append(clause);params.extend(values)
  if template=='financial_totals':where.append("f.entry_class='booked'")
  for k,op in [('start','>='),('end','<')]:
   if args.get(k):where.append('f.occurred_date'+op+'?');params.append(args[k])
  buckets={}
  for r in self.db.execute('SELECT f.* FROM current_item r JOIN financial_detail f USING(revision_id) WHERE '+' AND '.join(where),params):
   key=(r['currency'],r['scale'],r['direction'])+((r['entry_class'],) if template=='trip_costs' else ())
   bucket=buckets.setdefault(key,[0,0]);bucket[0]+=r['amount_minor'];bucket[1]+=1
  return [dict(currency=k[0],scale=k[1],direction=k[2],**({'entry_class':k[3]} if len(k)==4 else {}),total_minor=v[0],count=v[1]) for k,v in sorted(buckets.items())]
