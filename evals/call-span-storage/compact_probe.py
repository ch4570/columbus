"""Measure a lossless span encoding experiment; not a published archive format."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import tempfile
from columbus.archive import archive
from columbus.index import RepositoryIndex, compact

KEYS=('lineno','col_offset','end_lineno','end_col_offset')
def span(value, reverse=False):
    if reverse:
        assert isinstance(value,list) and len(value)==4
        return dict(zip(KEYS,value))
    assert set(value)==set(KEYS)
    return [value[k] for k in KEYS]
def transform(row, reverse=False):
    result=copy.deepcopy(row);data=result['data']
    if row['record']=='reference' and 'callee_span' in data:
        data['callee_span']=span(data['callee_span'],reverse)
    if row['record']=='edge':
        try:evidence=json.loads(data['evidence'])
        except (ValueError,TypeError):evidence=None
        if isinstance(evidence,dict) and 'callee_span' in evidence:
            evidence['callee_span']=span(evidence['callee_span'],reverse)
            data['evidence']=compact(evidence)
    return result
p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);original=root/'original.gz';candidate=root/'candidate.gz'
    receipt=archive(RepositoryIndex(a.database),original)
    rows=0;changed=0
    with gzip.open(original,'rb') as source,candidate.open('wb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as output:
            for line in source:
                row=json.loads(line);encoded=transform(row)
                assert transform(encoded,True)==row
                changed+=encoded!=row;rows+=1
                output.write((compact(encoded)+'\n').encode())
    result={'rows_roundtrip_verified':rows,'changed_records':changed,'original_gzip_bytes':receipt['bytes'],
            'candidate_gzip_bytes':candidate.stat().st_size,
            'change_percent':(candidate.stat().st_size/receipt['bytes']-1)*100,
            'production_format_changed':False,'same_record_order':True,
            'scope':'Exact decoded row and embedded evidence string roundtrip, fixed-order four-coordinate arrays; prototype only.'}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
