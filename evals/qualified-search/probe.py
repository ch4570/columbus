"""Bounded qualified search must expose omitted ambiguous declarations."""
import json
from pathlib import Path
import tempfile
from columbus.index import RepositoryIndex

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    for i in range(60):
        folder=root/f'p{i:02}';folder.mkdir()
        (folder/'Loader.java').write_text(f'package p{i:02}; class Loader {{ void getResource() {{}} }}')
    index=RepositoryIndex(root/'.columbus/index.sqlite');index.refresh(root)
    search=index.search('Loader.getResource',limit=50)
    assert len(search['hits'])==50 and search['truncated']
    assert all(h['retrieval']['qualified_suffix'] for h in search['hits'])
    context=index.context('Loader.getResource',mode='signatures',budget_bytes=64000)
    assert context['truncated'] and not context['semantic_complete']
    filtered=index.search('Loader.getResource',path='p59/*')
    assert not filtered['truncated']
    assert all(h['path'].startswith('p59/') for h in filtered['hits'])
    assert sum(h['retrieval']['qualified_suffix'] for h in filtered['hits'])==1
    assert filtered['hits'][0]['qualname']=='p59.Loader.getResource'
    exact=index.search('p59.Loader.getResource',limit=1)
    assert exact['hits'][0]['qualname']=='p59.Loader.getResource'
    result={'fixture_declarations':60,'bounded_search_hits':len(search['hits']),
            'search_truncated':search['truncated'],'context_truncated':context['truncated'],
            'filtered_declaration':filtered['hits'][0]['qualname'],'filtered_truncated':filtered['truncated'],
            'exact_first':exact['hits'][0]['qualname'],'runtime_executed':False}
    print(json.dumps(result,indent=2))
