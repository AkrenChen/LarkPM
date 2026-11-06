import { invoke } from '@tauri-apps/api/core';
import type { Task } from './types';
export const rpc = <T,>(method: string, params: Record<string, unknown> = {}) => invoke<T>('rpc', { method, params });
export function errorText(error: unknown): string {
  return typeof error === 'string' ? error : error instanceof Error ? error.message : String(error);
}
export function parseConflict(error: unknown): { current: Task; message: string } | null {
  try { const data = JSON.parse(errorText(error)); return data.kind === 'conflict' ? data : null; } catch { return null; }
}
export function formatValue(value: unknown): string {
  if (value == null || value === '') return '未设置';
  if (Array.isArray(value)) return value.map(v => typeof v === 'object' && v ? v.name || v.id : String(v)).join('、') || '未设置';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
export function dateLabel(value: string): string { return value ? value.slice(5).replace('-', '/') : '未排期'; }
export function today(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}
