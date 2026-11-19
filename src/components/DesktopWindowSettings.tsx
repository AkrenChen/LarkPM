import { invoke } from '@tauri-apps/api/core';
import { useEffect, useState } from 'react';
import { errorText } from '../api';

type Preferences = { shortcut: string; show_taskbar: boolean };

export default function DesktopWindowSettings() {
  const [settings, setSettings] = useState<Preferences | null>(null);
  const [recording, setRecording] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void invoke<{ settings: Preferences; error?: string }>('desktop_preferences_get').then(value => {
      if (active) { setSettings(value.settings); setError(value.error || ''); }
    }).catch(value => { if (active) setError(errorText(value)); });
    return () => { active = false; };
  }, []);
  async function save(next: Preferences) {
    setBusy(true); setError('');
    try { setSettings(await invoke<Preferences>('desktop_preferences_save', { settings: next })); }
    catch (value) { setError(errorText(value)); }
    finally { setBusy(false); setRecording(false); }
  }
  return <div className="desktop-window-settings"><h3>窗口与任务栏</h3>
    <label>显示／隐藏窗口快捷键<div className="button-row"><button type="button" className="button small" aria-label="设置显示隐藏窗口快捷键" disabled={!settings || busy} onClick={() => setRecording(true)} onBlur={() => setRecording(false)} onKeyDown={event => {
      if (!recording || !settings) return;
      event.preventDefault(); event.stopPropagation();
      if (event.key === 'Escape') { setRecording(false); return; }
      if (['Control', 'Alt', 'Shift', 'Meta'].includes(event.key) || event.repeat) return;
      if (!event.ctrlKey && !event.altKey && !event.metaKey) { setError('请组合使用 Ctrl、Alt 或 Win 和一个按键'); return; }
      const key = /^[a-z0-9]$/i.test(event.key) ? event.key.toUpperCase() : event.key === ' ' ? 'Space' : event.key;
      void save({ ...settings, shortcut: [event.ctrlKey && 'Ctrl', event.altKey && 'Alt', event.shiftKey && 'Shift', event.metaKey && 'Super', key].filter(Boolean).join('+') });
    }}>{recording ? '请按组合键，Esc 取消' : settings?.shortcut || '未设置 · 点击录入'}</button><button type="button" className="button small" disabled={!settings?.shortcut || busy} onClick={() => settings && void save({ ...settings, shortcut: '' })}>清除</button></div></label>
    <label className="checkbox-label"><input type="checkbox" aria-label="在任务栏显示窗口图标" checked={settings?.show_taskbar ?? true} disabled={!settings || busy} onChange={event => settings && void save({ ...settings, show_taskbar: event.target.checked })}/>在任务栏显示窗口图标</label>
    <p className="muted">快捷键切换显示／隐藏，隐藏后仍在托盘运行。设置立即生效并在重启后保留。</p>
    {error && <p className="source-error" role="alert">{error}</p>}
  </div>;
}
