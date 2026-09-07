"""Record distinct calls collapsed by line-based Python edge deduplication."""
import ast
import json
from pathlib import Path
import tempfile
from columbus.index import RepositoryIndex
source='def target(value): return value\ndef caller(): return target(1) + target(2)\n'
syntax_calls=[node for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Call)]
assert len(syntax_calls)==2 and len({node.col_offset for node in syntax_calls})==2
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'demo.py').write_text(source)
    index=RepositoryIndex(root/'.columbus/index.sqlite');index.refresh(root)
    packet=index.callers('target')
    item,=packet['items']
    assert item['call_sites']==1
    print(json.dumps({'ast_call_sites':2,'stored_call_sites':item['call_sites'],
                      'distinct_ast_columns':[node.col_offset for node in syntax_calls],
                      'same_line':True,'bug_reproduced':True,'fixed':False},indent=2))
