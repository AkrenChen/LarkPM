import type { DepartmentOption } from '../types';
import { departmentStyle } from '../departmentColors';
import ListSelect from './ListSelect';
import './DepartmentSelect.css';

export function DepartmentTag({ name, options }: { name: string; options: DepartmentOption[] }) {
  const option = options.find(o => o.name === name);
  return <span className="department-tag" style={departmentStyle(option?.color, name)} title={option ? name : `${name}（不在当前表选项中）`}>{name}{!option && <small> · 旧值</small>}</span>;
}

export default function DepartmentSelect({ value, options, onChange, label, placeholder = '选择部门', clearLabel = '清除部门', disabled = false }: {
  value: string; options: DepartmentOption[]; onChange: (value: string) => void; label: string; placeholder?: string; clearLabel?: string; disabled?: boolean;
}) {
  return <ListSelect className="department-select" aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value)} renderValue={() => value ? <DepartmentTag name={value} options={options}/> : <span className="department-placeholder">{placeholder}</span>}>
    <option value="">{clearLabel}</option>{options.map(option => <option key={option.id} value={option.name}>{option.name}</option>)}
  </ListSelect>;
}
