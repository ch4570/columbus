"""Read-only saved-graph trial gate; never starts a model or creates an index."""
import gzip
import hashlib
import json
import lzma
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def file_manifest(root):
    result = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if {'.git', '__pycache__'} & set(relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Symlink in frozen evaluation inputs')
        if path.is_file():
            result[relative.as_posix()] = digest(path)
    return result


def verify(repository, runtime, artifact, expected):
    repository, runtime, artifact = map(Path, (repository, runtime, artifact))
    if any((repository / name).exists() for name in ('.columbus', '.repoatlas')):
        raise ValueError('Archive trial consumer contains a local index directory')
    if artifact.is_symlink() or artifact.resolve().is_relative_to(repository.resolve()):
        raise ValueError('Archive must be a separate regular frozen artifact')
    source = file_manifest(repository)
    if source != expected['source_manifest'] or file_manifest(runtime) != expected['runtime_manifest']:
        raise ValueError('Frozen source or runtime changed')
    checksum = digest(artifact)
    if checksum != expected['archive_sha256']:
        raise ValueError('Frozen archive checksum changed')
    with artifact.open('rb') as raw:
        magic = raw.read(6)
    opener = gzip.open if magic.startswith(b'\x1f\x8b') else lzma.open if magic == b'\xfd7zXZ\x00' else None
    if opener is None:
        raise ValueError('Unsupported archive compression')
    names = {'file':'files','node':'nodes','scope':'scopes','edge':'edges','reference':'references','import':'imports','diagnostic':'diagnostics'}
    counts = dict.fromkeys(names.values(), 0)
    header = None
    end = None
    files = {}
    with opener(artifact, 'rt', encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            kind, data = row['record'], row['data']
            if header is None:
                if kind != 'manifest' or data.get('format') != 'columbus-graph' or data.get('version') != 1:
                    raise ValueError('Invalid archive manifest')
                header = data
                continue
            if end is not None:
                raise ValueError('Trailing archive records')
            if kind == 'end':
                end = data
                continue
            if kind not in names:
                raise ValueError('Unknown archive record')
            counts[names[kind]] += 1
            if kind == 'file':
                path = data['path']
                if path in files or source.get(path) != data['hash']:
                    raise ValueError('Archive source hash differs from frozen source')
                files[path] = data['hash']
    if (not header or header.get('revision') != expected['revision'] or end != counts
            or counts != expected['counts'] or not files):
        raise ValueError('Archive revision or complete record counts differ')
    if (digest(artifact) != checksum or file_manifest(repository) != source
            or file_manifest(runtime) != expected['runtime_manifest']):
        raise ValueError('Inputs changed during preflight')
    return {'passed':True,'archive_sha256':checksum,'revision':header['revision'],
            'source_files_verified':len(source),'indexed_source_files_verified':len(files),
            'counts':counts,'consumer_index_absent':True}
