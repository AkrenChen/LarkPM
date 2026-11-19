import { isUnavailable, type Owner, type Person, type Project } from './types.ts';

export function availableFilterOwners(owners: Owner[], people: Person[]): Owner[] {
  const unavailable = new Set(people.filter(isUnavailable).map(person => person.id));
  return [...new Map(owners.filter(owner => !unavailable.has(owner.id)).map(owner => [owner.id, owner])).values()];
}

function platforms(value: string, unspecifiedBoth = false): string[] {
  if (/双端/i.test(value)) return ['android', 'ios'];
  const result = [];
  if (/android|安卓/i.test(value)) result.push('android');
  if (/ios/i.test(value)) result.push('ios');
  return result.length || !unspecifiedBoth ? result : ['android', 'ios'];
}

function versionKey(value: string): string {
  return value.replace(/[（(]\s*(?:android|安卓|ios|双端)(?:\s*[/、+&]\s*(?:android|安卓|ios))*\s*[）)]/gi, '').trim().replace(/^v(?=\d)/i, '').toLowerCase();
}

export function isApprovedFilterVersion(value: string, project?: Project): boolean {
  if (!value || !project) return false;
  const cache = project.source_cache?.versions;
  const rows = [...(cache?.rows || []), ...Object.values(cache?.online || {}).filter(row => row !== null)];
  const approved = project.sources?.versions?.online_value || '已过审';
  const matching = rows.filter(row => row.status === approved && versionKey(row.version) === versionKey(value));
  return platforms(value, true).every(platform => matching.some(row => platforms(row.platform).includes(platform)));
}
