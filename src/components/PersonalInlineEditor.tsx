import { useLayoutEffect, useRef, useState } from 'react';
import Icon from './Icon';

export default function PersonalInlineEditor({ initial = '', label, onSave, onCancel }: {
  initial?: string; label: string; onSave: (text: string) => Promise<boolean>; onCancel: () => void;
}) {
  const [text, setText] = useState(initial), [saving, setSaving] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null), locked = useRef(false);
  useLayoutEffect(() => { const el = input.current; if (el) { el.style.height = '0'; el.style.height = `${el.scrollHeight}px`; } }, [text]);
  async function save() {
    if (!text.trim() || locked.current) return;
    locked.current = true; setSaving(true);
    try { if (await onSave(text.trim())) onCancel(); }
    finally { locked.current = false; setSaving(false); }
  }
  return <div className="personal-inline-editor">
    <textarea ref={input} autoFocus rows={1} aria-label={label} maxLength={10000} value={text} disabled={saving} placeholder="输入待办，Enter 保存" onChange={event => setText(event.target.value)} onKeyDown={event => {
      if (event.nativeEvent.isComposing) return;
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void save(); }
      if (event.key === 'Escape' && !saving) { event.preventDefault(); event.stopPropagation(); onCancel(); }
    }}/>
    <div><span>Enter 保存 · Shift＋Enter 换行</span><button type="button" aria-label="取消编辑待办" disabled={saving} onClick={onCancel}><Icon name="close" size={13}/></button><button type="button" aria-label="保存待办" disabled={saving || !text.trim()} onClick={() => void save()}><Icon name="check" size={13}/></button></div>
  </div>;
}
