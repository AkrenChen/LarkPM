import { useEffect, useRef, useState, type ReactNode } from 'react';

export default function InlineValue({ label, value, children, revision, className = '' }: { label: string; value: ReactNode; children: ReactNode; className?: string; revision?: number }) {
  const [editing, setEditing] = useState(false), editor = useRef<HTMLDivElement>(null), openingTarget = useRef<HTMLElement | null>(null);
  useEffect(() => { setEditing(false); }, [revision]);
  useEffect(() => { if (editing) editor.current?.querySelector<HTMLElement>('input,textarea,button,select')?.focus(); }, [editing]);
  useEffect(() => {
    if (!editing) return;
    const outside = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node) || editor.current?.contains(target) || openingTarget.current?.contains(target)) return;
      if (target instanceof Element && target.closest('[role="listbox"]')) return;
      setEditing(false);
    };
    document.addEventListener('click', outside);
    return () => document.removeEventListener('click', outside);
  }, [editing]);
  return <div className={`inline-value ${className}${editing ? ' is-editing' : ''}`}>
    {editing ? <div ref={editor} className="inline-value-editor" onKeyDown={event => {
      if (event.key === 'Escape') { event.stopPropagation(); setEditing(false); }
      if (event.key === 'Enter' && (event.target as HTMLElement).tagName === 'INPUT') { event.preventDefault(); setEditing(false); }
    }}>{children}</div> : <button type="button" className="inline-value-display" aria-label={`编辑${label}`} title="单击修改" onClick={event => { openingTarget.current = event.currentTarget; setEditing(true); }} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setEditing(true); } }}>{value}</button>}
  </div>;
}
