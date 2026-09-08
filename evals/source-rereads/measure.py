"""Measure verified physical-line overlap in retained traces; never execute commands."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex

p=argparse.ArgumentParser();p.add_argument('observation',type=Path);p.add_argument('output',type=Path);p.add_argument('--case',default='archive-urlencode');p.add_argument('--prefix',default='django/');a=p.parse_args()
if not re.fullmatch(r'[a-z0-9][a-z0-9-]*',a.case):p.error('case must be a filename-safe case ID')
manifest=json.loads((a.observation/'manifest.json').read_text())['source_manifest']
result={'scope':f'Verified bounded {a.prefix} source reads only; excludes rg, help, skill text, metadata and model tokens.', 'conditions':{}}
for condition in ['baseline','columbus']:
    trial=a.observation/'trials'/f'{a.case}-{condition}-1'
    recorded=json.loads((trial/'result.json').read_text())
    raw=(trial/'events.jsonl').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==recorded['events_sha256']
    seen=set();reads=[];unverified=[];files={};empty_ranges=[]
    def add(path,start,end,output,mode,command_id):
        if not path.startswith(a.prefix) or path not in manifest:return
        if path not in files:
            data=(a.observation/'repository'/path).read_bytes()
            assert hashlib.sha256(data).hexdigest()==manifest[path]
            parts=data.split(b'\n');files[path]=[x+b'\n' for x in parts[:-1]]+([parts[-1]] if parts[-1] else [])
        lines=files[path];end=min(end,len(lines))
        if start>end:
            empty_ranges.append({'path':path,'start':start,'file_lines':len(lines),'mode':mode});return
        span=lines[start-1:end]
        text=b''.join(span).decode('utf-8').rstrip('\n')
        if mode=='sed':verified=text in output
        elif mode=='nl':
            numbered=[(int(m[1]),m[2]) for s in output.split('\n') if (m:=re.fullmatch(r'\s*(\d+)\t(.*)',s))]
            expected=[(n,lines[n-1].decode().rstrip('\n')) for n in range(start,end+1)]
            verified=any(numbered[i:i+len(expected)]==expected for i in range(len(numbered)))
        elif mode=='archive-source':
            escapes={n:f'\\u{n:04x}' for n in range(32)}
            escapes.update({n:f'\\u{n:04x}' for n in (0x85,0x2028,0x2029)})
            escapes.update({9:'\\t',10:'\\n',13:'\\r',127:'\\u007f'})
            expected=[f'{n}| '+lines[n-1].decode().rstrip('\n').translate(escapes) for n in range(start,end+1)]
            verified=output.rstrip('\n').split('\n')==expected
        else:
            verified=all(f'{n}| '+lines[n-1].decode().rstrip('\n') in output for n in range(start,end+1))
        if not verified:unverified.append({'path':path,'start':start,'end':end,'mode':mode});return
        duplicates=[n for n in range(start,end+1) if (path,n) in seen]
        reads.append({'command_id':command_id,'path':path,'start':start,'end':end,'mode':mode,'bytes':sum(map(len,span)),
                      'repeated_bytes':sum(len(lines[n-1]) for n in duplicates),'repeated_lines':len(duplicates)})
        seen.update((path,n) for n in range(start,end+1))
    for event in map(json.loads,raw.splitlines()):
        item=event.get('item',{})
        if event['type']!='item.completed' or item.get('type')!='command_execution' or item.get('exit_code')!=0:continue
        command=item['command'];output=item['aggregated_output'];outer=shlex.split(command)
        groups=[]
        for line in outer[-1].split('\n'):
            try:
                lexer=shlex.shlex(line,posix=True,punctuation_chars=';&');lexer.whitespace_split=True
                group=[]
                for token in lexer:
                    if token in {';', '&&', '&'}:
                        if group:groups.append(group)
                        group=[]
                    else:group.append(token)
                if group:groups.append(group)
            except ValueError:continue
        for tokens in groups:
            if len(tokens)==4 and tokens[:2]==['sed','-n']:
                mode,spec,path='sed',tokens[2],tokens[3]
            elif len(tokens)==7 and tokens[:2]==['nl','-ba'] and tokens[3:6]==['|','sed','-n']:
                mode,spec,path='nl',tokens[6],tokens[2]
            elif (len(tokens) in {8,9} and tokens[:2]==['sed','-n']
                  and tokens[4:7]==['|','nl','-ba']
                  and ((len(tokens)==8 and re.fullmatch(r'-v\d+',tokens[7]))
                       or (len(tokens)==9 and tokens[7]=='-v' and tokens[8].isdigit()))
                  and re.fullmatch(r'\d+,\d+p',tokens[2])):
                # Verify actual printed line numbers against physical source;
                # a wrong -v value must not be treated as a valid source range.
                mode,spec,path='nl',tokens[2],tokens[3]
            else:continue
            if re.fullmatch(r'\d+,\d+p(?:;\d+,\d+p)*',spec):
                for part in spec.split(';'):
                    m=re.fullmatch(r'(\d+),(\d+)p',part)
                    add(path,int(m[1]),int(m[2]),output,mode,item['id'])
        if 'archive-source' in command and output.startswith('columbus archive-source;'):
            rows=output.split('\n')
            if len(rows)>1 and rows[1].startswith('metadata '):
                c=json.loads(rows[1][len('metadata '):])
                if c.get('source_hash')!=manifest.get(c['path']):
                    unverified.append({'path':c['path'],'start':c['start_line'],'end':c['end_line'],
                                       'mode':'archive-source','reason':'source hash differs from source manifest'})
                else:
                    add(c['path'],c['start_line'],c['end_line'],'\n'.join(rows[2:]),'archive-source',item['id'])
        if any(name in command for name in ('archive-neighbors', 'archive-callers')) and 'call_context:' in output:
            page_files,page_nodes,section={},{},None
            context,block=None,[]
            def check_context(c,lines):
                if c is None:return
                if c.get('source_hash')!=manifest.get(c['path']):
                    unverified.append({'path':c['path'],'start':c['start_line'],'end':c['end_line'],
                                       'mode':'archive-context','reason':'context hash differs from source manifest'})
                    return
                add(c['path'],c['start_line'],c['end_line'],'\n'.join(lines),'archive-context',item['id'])
            for line in output.split('\n'):
                if line.startswith(('files ', 'nodes ', 'edges ')):
                    section=line.split()[0]
                elif line.startswith('call_context:'):
                    section='contexts'
                elif line.startswith('[') and section in {'files','nodes'}:
                    row=json.loads(line)
                    if section=='files':page_files[row[0]]=row[1:]
                    else:page_nodes[row[0]]=row[2]
                elif line.startswith(('{"source_id":','{"source_node":')):
                    check_context(context,block)
                    c=json.loads(line)
                    if 'source_node' in c:
                        c['source_id']=page_nodes[c.pop('source_node')]['id']
                        c['path'],c['source_hash']=page_files[c.pop('file_number')]
                    context,block=c,[]
                elif section=='contexts' and context is not None:
                    block.append(line)
            check_context(context,block)
    result['conditions'][condition]={'verified_ranges':len(reads),'unique_lines':len(seen),'source_bytes_returned':sum(x['bytes'] for x in reads),
        'repeated_source_bytes':sum(x['repeated_bytes'] for x in reads),'empty_ranges':empty_ranges,'unverified_ranges':unverified,'reads':reads,'events_sha256':recorded['events_sha256']}
a.output.write_text(json.dumps(result,indent=2)+'\n')
print({k:{f:v for f,v in d.items() if f!='reads'} for k,d in result['conditions'].items()})
