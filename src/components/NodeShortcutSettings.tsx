import { useState } from 'react';
import { defaultNodeShortcuts, shortcutText, type NodeShortcuts } from '../nodeShortcuts';
import ListSelect from './ListSelect';

export default function NodeShortcutSettings({ value, onChange }: { value: NodeShortcuts; onChange: (value: NodeShortcuts) => void }) {
  const [recording, setRecording] = useState(false), [error, setError] = useState('');
  return <div className="node-shortcut-settings"><h3>节点快捷键</h3><label>按住进入编排<ListSelect aria-label="编排快捷键" value={value.arrange} onChange={event => { onChange({ ...value, arrange: event.target.value as NodeShortcuts['arrange'] }); setError(''); }}><option value="Alt">Alt</option><option value="Shift">Shift</option></ListSelect></label><label>切换所选任务状态<button type="button" className="button" aria-label="录制状态快捷键" onClick={() => { setRecording(true); setError(''); }} onBlur={() => setRecording(false)} onKeyDown={event => {
    if (!recording) return;
    event.preventDefault(); event.stopPropagation();
    if (event.key === 'Escape') { setRecording(false); return; }
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(event.key)) return;
    if (event.nativeEvent.isComposing || event.metaKey || !/^[a-z0-9]$/i.test(event.key) || event.altKey || event.shiftKey || (!event.ctrlKey && ['f','r'].includes(event.key.toLowerCase()))) { setError('使用字母、数字或 Ctrl＋字母／数字；不使用编排键、浏览器刷新键。'); return; }
    const status = `${event.ctrlKey ? 'Ctrl+' : ''}${event.key.toUpperCase()}`;
    if (['Ctrl+R','Ctrl+W','Ctrl+Q','Ctrl+T','Ctrl+F','Ctrl+A','Ctrl+C','Ctrl+V','Ctrl+X','Ctrl+Z','Ctrl+S'].includes(status)) { setError('这个组合有常用系统或编辑用途，请换一个。'); return; }
    onChange({ ...value, status }); setRecording(false); setError('');
  }}>{recording ? '请按下快捷键…' : shortcutText(value.status)}</button></label>{error && <p role="alert">{error}</p>}<p className="muted">Ctrl＋点击多选，Esc 取消当前拖动；松开编排键保留已放下的排序并退出。按状态快捷键前，先点击任务状态按钮或选中任务。</p><button type="button" className="button small" onClick={() => onChange({ ...defaultNodeShortcuts })}>恢复默认快捷键</button></div>;
}
