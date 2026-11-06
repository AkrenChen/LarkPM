import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse


DEFAULT_SOURCE_FIELDS = {
    'tests': dict(project='项目名', title='测试项目', start='进测日期', end='结测日期', version='版本号'),
    'versions': dict(platform='平台', version='版本号', status='审核状态', released='过审时间'),
}


def normalize_source(source, kind):
    source = dict(source)
    url = source.get('url', '').strip()
    if not url:
        return None
    parsed = urlparse(url)
    parts = parsed.path.strip('/').split('/')
    if (parsed.scheme != 'https' or not (parsed.hostname or '').endswith(('.feishu.cn', '.larksuite.com'))
            or parsed.username or len(parts) != 2 or parts[0] not in ('base', 'wiki')):
        raise ValueError('关联表请使用飞书 /base/ 或 /wiki/ HTTPS 链接')
    source['url'] = url
    source['table_id'] = parse_qs(parsed.query).get('table', [''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]+', source['table_id']):
        raise ValueError('关联表链接缺少有效 table 参数')
    if parts[0] == 'base':
        source['base_token'] = parts[1]
    else:
        source['base_token'] = source.get('base_token', '').strip()
    if source['base_token'] and not re.fullmatch(r'[A-Za-z0-9_-]+', source['base_token']):
        raise ValueError('关联表 Base Token 格式不正确')
    source['fields'] = dict(DEFAULT_SOURCE_FIELDS[kind], **source.get('fields', {}))
    if any(not isinstance(v, str) or not v.strip() for v in source['fields'].values()):
        raise ValueError('关联表字段映射不能为空')
    source['project_value'] = str(source.get('project_value', '')).strip()
    source['online_value'] = str(source.get('online_value', '已过审')).strip()
    if kind == 'tests' and not source['project_value']:
        raise ValueError('请填写测试表中本项目的项目名')
    if kind == 'versions' and not source['online_value']:
        raise ValueError('请填写代表线上的审核状态')
    return source


def summarize_versions(rows, online_value):
    result = dict(android=None, ios=None)
    for row in rows:
        platform = row.get('platform', '').strip().lower()
        key = 'android' if platform in ('安卓', 'android') else 'ios' if platform == 'ios' else None
        if not key or row.get('status') != online_value or not row.get('version'):
            continue
        def rank(value):
            return (value.get('released', ''), tuple(int(n) for n in re.findall(r'\d+', value['version'])))
        if result[key] is None or rank(row) > rank(result[key]):
            result[key] = row
    return result


def test_windows(rows, project):
    return sorted([r for r in rows if project and r.get('project', '').strip() == project],
                  key=lambda r: (r.get('start', ''), r.get('end', ''), r.get('id', '')))


def refreshed_cache(remote, source, kind):
    rows = remote.source_rows(source, kind)
    result = dict(updated_at=datetime.now(timezone.utc).isoformat(), error='')
    if kind == 'tests':
        result['windows'] = test_windows(rows, source['project_value'])
    else:
        result['rows'] = rows
        result['online'] = summarize_versions(rows, source['online_value'])
    return result
