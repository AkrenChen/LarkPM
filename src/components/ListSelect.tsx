import { Children, Fragment, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import Icon from './Icon';
import './ListSelect.css';

type Option = { value: string; label: string; disabled?: boolean };
function text(node: ReactNode): string {
  return Children.toArray(node).map(child => isValidElement<{ children?: ReactNode }>(child) ? text(child.props.children) : String(child)).join('');
}
function optionsFrom(children: ReactNode): Option[] {
  return Children.toArray(children).flatMap(child => {
    if (!isValidElement<{ value?: string; children?: ReactNode; disabled?: boolean }>(child)) return [];
    if (child.type === Fragment) return optionsFrom(child.props.children);
    const label = text(child.props.children);
    return [{ value: child.props.value ?? label, label, disabled: child.props.disabled }];
  });
}

export default function ListSelect({ children, value, onChange, disabled = false, id, className = '', 'aria-label': label, renderValue, selectedValues, onToggle }: {
  children: ReactNode; value: string; onChange: (event: { target: { value: string } }) => void; disabled?: boolean; id?: string; className?: string; 'aria-label'?: string; renderValue?: (label: string) => ReactNode; selectedValues?: string[]; onToggle?: (value: string) => void;
}) {
  const options = optionsFrom(children), key = JSON.stringify(options);
  const [open, setOpen] = useState(false), [active, setActive] = useState(0);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 160, maxHeight: 280 });
  const trigger = useRef<HTMLButtonElement>(null), menu = useRef<HTMLDivElement>(null), menuId = useId();
  const selected = options.find(option => option.value === value);
  function show() { setActive(Math.max(0, options.findIndex(option => selectedValues ? selectedValues.includes(option.value) : option.value === value))); setOpen(true); }
  function choose(index: number) {
    if (!options[index] || options[index].disabled) return;
    if (selectedValues) { onToggle?.(options[index].value); trigger.current?.focus(); return; }
    onChange({ target: { value: options[index].value } }); setOpen(false); trigger.current?.focus();
  }
  useEffect(() => { setOpen(false); }, [disabled, key]);
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = trigger.current?.getBoundingClientRect();
      if (!rect) return;
      if (rect.bottom < 0 || rect.top > window.innerHeight) { setOpen(false); return; }
      const width = Math.min(Math.max(rect.width, 160), window.innerWidth - 16);
      const below = window.innerHeight - rect.bottom - 12, above = rect.top - 12;
      const upwards = below < Math.min(options.length * 34 + 10, 200) && above > below;
      const maxHeight = Math.min(280, Math.max(68, upwards ? above : below));
      setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)), top: upwards ? rect.top - Math.min(maxHeight, options.length * 34 + 10) - 4 : rect.bottom + 4, width, maxHeight });
    };
    const outside = (event: PointerEvent) => { if (!trigger.current?.contains(event.target as Node) && !menu.current?.contains(event.target as Node)) setOpen(false); };
    place(); document.addEventListener('pointerdown', outside); window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); };
  }, [open, key]);
  useEffect(() => { if (open) menu.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' }); }, [active, open]);
  return <>
    <button ref={trigger} id={id} type="button" className={`list-select ${className}${open ? ' is-open' : ''}`} role="combobox" aria-label={label} aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? menuId : undefined} aria-activedescendant={open ? `${menuId}-${active}` : undefined} disabled={disabled}
      onClick={() => open ? setOpen(false) : show()} onKeyDown={event => {
        if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); }
        else if (event.key === 'Tab') setOpen(false);
        else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          if (!open) show();
          else setActive(index => event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length);
        } else if ((event.key === 'Enter' || event.key === ' ') && open) { event.preventDefault(); choose(active); }
        else if (event.key.length === 1 && event.key !== ' ') {
          const index = options.findIndex(option => option.label.toLowerCase().startsWith(event.key.toLowerCase()));
          if (index >= 0) { event.preventDefault(); setActive(index); setOpen(true); }
        }
      }}>
      <span>{renderValue ? renderValue(selected?.label || value) : selected?.label || value || '请选择'}</span><Icon name="chevron" size={12}/>
    </button>
    {open && createPortal(<div ref={menu} id={menuId} className="select-list" role="listbox" aria-label={`${label || '下拉'}选项`} aria-multiselectable={selectedValues ? true : undefined} style={position}>
      {options.map((option, index) => <button type="button" role="option" key={`${option.value}:${index}`} id={`${menuId}-${index}`} data-index={index} aria-label={option.label} aria-selected={selectedValues ? selectedValues.includes(option.value) : value === option.value} disabled={option.disabled} tabIndex={-1} className={(selectedValues ? selectedValues.includes(option.value) : value === option.value) ? 'is-selected' : active === index ? 'is-focused' : ''} onPointerMove={() => setActive(index)} onMouseDown={event => event.preventDefault()} onClick={() => choose(index)}><span>{option.label}</span>{(selectedValues ? selectedValues.includes(option.value) : value === option.value) && <Icon name="check" size={13}/>}</button>)}
      {!options.length && <p>暂无选项</p>}
    </div>, document.body)}
  </>;
}
