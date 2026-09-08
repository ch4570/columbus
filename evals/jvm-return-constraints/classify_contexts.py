"""Classify removed calls by concrete Java AST ancestors, without resolving types."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
from tree_sitter import Language, Parser
import tree_sitter_java

p=argparse.ArgumentParser();p.add_argument('repo',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
review=json.loads(Path(__file__).with_name('spring-removed-review.json').read_text())
parser=Parser(Language(tree_sitter_java.language()));trees={};rows=[]
def walk(node):
 yield node
 for child in node.named_children:yield from walk(child)
for item in review['removed']:
 edge=item['edge'];path=edge['path'];data=(a.repo/path).read_bytes()
 assert hashlib.sha256(data).hexdigest()==item['source_sha256']
 tree=trees[path] if path in trees else trees.setdefault(path,parser.parse(data))
 matches=[n for n in walk(tree.root_node) if n.type=='method_invocation' and data.count(b'\n',0,n.start_byte)+1==edge['line'] and re.sub(r'\s+',' ',data[n.start_byte:n.end_byte].decode()).strip()==edge['evidence']]
 assert len(matches)==1,(path,edge['line'],len(matches))
 node=matches[0];ancestors=[];parent=node.parent
 while parent and len(ancestors)<6:
  ancestors.append({'type':parent.type,'start_line':data.count(b'\n',0,parent.start_byte)+1,'end_line':data.count(b'\n',0,parent.end_byte)+1})
  parent=parent.parent
 rows.append({'source':edge['source'],'target':edge['target'],'line':edge['line'],'expected_type':item['expected_type'],'callee_span':[node.start_byte,node.end_byte],'ancestors':ancestors})
result={'all_removed_calls_matched':True,'calls':len(rows),'immediate_parent_counts':dict(collections.Counter(r['ancestors'][0]['type'] for r in rows)),'missing_expected_type_parent_counts':dict(collections.Counter(r['ancestors'][0]['type'] for r in rows if not r['expected_type'])),'rows':rows,'scope':'AST context categories only; no compiler validity or resolution claim.'}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(result['missing_expected_type_parent_counts'])
