"""Verify preserved legacy bytes and exact whole-document / workbook row selectors."""
import hashlib,json,re,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from base import canon,digest
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def integrity(row,settings):
 result={'file_sha256_matches':False,'selector_matches_original':False,'original_verified':False}
 try:
  locator=json.loads(row['locator_json']);sha=row['file_sha256'];obj=Path(locator['object_file']).resolve();root=Path(settings['archiveRoot']).resolve()/'attachments/objects'
  if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{64}',sha) or obj!=root/sha[:2]/sha:return result
  if not obj.is_file() or obj.stat().st_size>100*1024*1024:return result
  blob=obj.read_bytes();result['file_sha256_matches']=hashlib.sha256(blob).hexdigest()==sha
  if not result['file_sha256_matches']:return result
  if locator['type']=='legacy_health_document':result['selector_matches_original']=blob.decode('utf-8').replace('\r\n','\n').replace('\r','\n')==row['raw_text']
  elif locator['type']=='legacy_row':
   with zipfile.ZipFile(obj) as z:
    strings=[]
    if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
    rels={e.attrib['Id']:e.attrib['Target'] for e in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))};sheets=ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',NS)
    sheet=next(e for e in sheets if e.attrib['name']==locator['sheet']);target=rels[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']];target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
    xmlrow=next(e for e in ET.fromstring(z.read(target)).findall('m:sheetData/m:row',NS) if int(e.attrib['r'])==locator['row']);cells=[]
    for c in xmlrow.findall('m:c',NS):
     v=c.find('m:v',NS);f=c.find('m:f',NS);inline=c.find('m:is',NS);value=v.text if v is not None else None
     if c.attrib.get('t')=='s' and value is not None:value=strings[int(value)]
     if inline is not None:value=''.join(inline.itertext())
     if value is not None or f is not None:cells.append({'cell':c.attrib['r'],'type':c.attrib.get('t'),'value':value,'formula':f.text if f is not None else None,'style':c.attrib.get('s')})
    cols={re.sub('[0-9]','',c['cell']):c['value'] for c in cells};raw=cols.get('G') if locator['sheet']=='记录' else cols.get('I') if locator['sheet']=='消费记录' else cols.get('H');expected=canon({'sheet':locator['sheet'],'row':locator['row'],'cells':cells,'original_text':raw});result['selector_matches_original']=expected==row['raw_text']
  result['original_verified']=result['file_sha256_matches'] and result['selector_matches_original'] and digest(row['raw_text'])==row['content_sha256']
 except (OSError,ValueError,KeyError,StopIteration,zipfile.BadZipFile,ET.ParseError):pass
 return result
