import type { Project, TestWindow, VersionOverviewRow } from './types';

export function compareVersions(a: string, b: string): number {
  const parts = (value: string) => value.match(/\d+(?:\.\d+)+/)?.[0].split('.').map(Number);
  const left = parts(a), right = parts(b);
  if (left && right) {
    for (let index = 0; index < Math.max(left.length, right.length); index++) {
      const difference = (left[index] || 0) - (right[index] || 0);
      if (difference) return difference;
    }
    return 0;
  }
  return a.localeCompare(b, 'zh-CN', { numeric: true });
}

export function platformName(value: string): string {
  return /android|安卓/i.test(value) ? 'Android' : /ios/i.test(value) ? 'iOS' : value || '双端';
}

export function versionRows(project: Project, overrides = project.version_overview || []): VersionOverviewRow[] {
  const cache = project.source_cache?.versions;
  const sources = cache?.rows || Object.values(cache?.online || {}).filter(row => row !== null);
  const rows = new Map<string, VersionOverviewRow>();
  for (const row of sources) {
    if (!row.version) continue;
    rows.set(`source:${row.id}`, { id: `source:${row.id}`, version: row.version, platform: platformName(row.platform), submitted: row.submitted?.slice(0, 10) || '', description: row.description || '', status: row.status || '', origin: 'source' });
  }
  for (const [version, date] of Object.entries(project.targets || {})) {
    if (!date) continue;
    const platform = version.match(/[（(]([^）)]+)[）)]/)?.[1] || '双端';
    const number = version.replace(/\s*[（(][^）)]+[）)]\s*/, '').trim();
    rows.set(`legacy:${version}`, { id: `legacy:${version}`, version: number, platform: platformName(platform), submitted: date, description: project.target_details?.[version]?.description || '', status: '', origin: 'legacy' });
  }
  for (const override of overrides) {
    const base = rows.get(override.id);
    const { released: previousDate, ...values } = override;
    if (values.submitted === undefined && previousDate !== undefined) values.submitted = previousDate;
    if (!base && override.origin === 'source') continue;
    rows.set(override.id, { version: '', platform: '双端', submitted: '', description: '', status: '', origin: 'local', ...base, ...values });
  }
  const merged = new Map<string, VersionOverviewRow>();
  for (const row of rows.values()) {
    const key = `${row.version.trim().toLowerCase()}|${platformName(row.platform)}`;
    const previous = merged.get(key);
    if (!previous) merged.set(key, row);
    else if (row.origin === 'local') merged.set(key, { ...previous, ...row, status: previous.status || row.status });
    else merged.set(key, { ...previous, submitted: previous.submitted || row.submitted, description: previous.description || row.description });
  }
  return [...merged.values()].sort((a, b) => compareVersions(b.version, a.version) || b.submitted.localeCompare(a.submitted) || a.platform.localeCompare(b.platform) || a.id.localeCompare(b.id));
}

export function latestVersionTarget(project: Project) {
  return versionRows(project)[0];
}

export function isReleasedTest(test: TestWindow, project: Project): boolean {
  const text = `${test.version || ''} ${test.title}`;
  const version = text.match(/\d+(?:\.\d+)+/)?.[0];
  if (!version) return false;
  const platforms: Array<'android' | 'ios'> = [];
  if (/android|安卓/i.test(text)) platforms.push('android');
  if (/ios/i.test(text)) platforms.push('ios');
  if (!platforms.length && /双端/.test(text)) platforms.push('android', 'ios');
  return platforms.length > 0 && platforms.every(platform => {
    const online = project.source_cache?.versions?.online?.[platform];
    return !!online && compareVersions(online.version, version) >= 0;
  });
}
