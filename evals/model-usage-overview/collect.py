"""Summarize seven completed recent comparisons without model calls or token estimates."""
import hashlib
import json
from pathlib import Path
here=Path(__file__).resolve().parent
cases=['django-callers','django-html-callers','archive-capfirst','archive-urlencode','archive-safe-redirect','archive-force-bytes','archive-force-bytes-v2']
records=[]
for case in cases:
 path=here.parent/case/'results.json';raw=path.read_bytes();result=json.loads(raw)
 row={'case':case,'results_sha256':hashlib.sha256(raw).hexdigest(),'conditions':{}}
 for name in ['baseline','columbus']:
  r=result[name];u=r.get('usage');summary={k:r[k] for k in ['elapsed_seconds','timed_out','return_code','command_count','command_output_bytes']}
  summary['usage']=u
  if u is not None:
   assert u['input_tokens']>=u['cached_input_tokens']>=0
   assert u['uncached_input_tokens']==u['input_tokens']-u['cached_input_tokens']
  summary['automatic_quality_passed']=r['quality']['passed']
  row['conditions'][name]=summary
 records.append(row)
(here/'results.json').write_text(json.dumps({'scope':'Seven recent completed comparisons including one explicit force_bytes repeat; not the entire experiment history, not a population estimate. Missing usage remains null. Semantic judgments remain in each source report.','comparisons':records},indent=2)+'\n')
print('Verified',len(records),'completed result files; no model calls')
