"""Summarize retained command output by query phase, not model token attribution."""
import hashlib
import json
from pathlib import Path
here=Path(__file__).resolve().parent
results=json.loads((here/'results.json').read_text());out={}
for condition,result in results.items():
 groups={}
 for i,command in enumerate(result['commands']):
  text=command['command']
  group=('archive_search' if ' archive-search ' in text else 'archive_neighbors' if ' archive-neighbors ' in text else 'instructions_and_runtime_listing' if '/runtime/SKILL.md' in text or '/runtime/references/archive.md' in text else 'other_commands')
  row=groups.setdefault(group,{'commands':0,'output_bytes':0,'command_indices':[]})
  row['commands']+=1;row['output_bytes']+=command['output_bytes'];row['command_indices'].append(i)
 assert sum(g['commands'] for g in groups.values())==result['command_count']
 assert sum(g['output_bytes'] for g in groups.values())==result['command_output_bytes']
 out[condition]=groups
receipt={'source_results_sha256':hashlib.sha256((here/'results.json').read_bytes()).hexdigest(),'scope':'Whole completed commands grouped by explicit archive or instruction command strings; mixed commands stay whole. Other commands are not automatically redundant. No actual-token attribution or counterfactual savings.','conditions':out}
(here/'command-phases.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(out)
