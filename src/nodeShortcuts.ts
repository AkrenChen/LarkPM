export type NodeShortcuts = { arrange: 'Alt' | 'Shift'; status: string };
export const defaultNodeShortcuts: NodeShortcuts = { arrange: 'Alt', status: 'S' };
const key = 'larkpm-node-shortcuts';

export function readNodeShortcuts(): NodeShortcuts {
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    if (saved && ['Alt', 'Shift'].includes(saved.arrange) && typeof saved.status === 'string' && saved.status.length <= 30) return saved;
  } catch { /* Ignore invalid stored preferences. */ }
  return { ...defaultNodeShortcuts };
}

export function saveNodeShortcuts(value: NodeShortcuts) { localStorage.setItem(key, JSON.stringify(value)); }
export function shortcutText(value: string) { return value.replaceAll('+', '＋'); }
export function matchesStatus(event: KeyboardEvent, value: string) {
  const keys = value.toLowerCase().split('+');
  return event.key.toLowerCase() === keys[keys.length - 1] && event.ctrlKey === keys.includes('ctrl') && event.shiftKey === keys.includes('shift') && event.altKey === keys.includes('alt') && !event.metaKey && !event.repeat && !event.isComposing;
}
