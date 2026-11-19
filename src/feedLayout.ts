export function feedColumnCount(width: number): number {
  return Math.max(1, Math.floor((width + 12) / 342));
}

export class StableRequirementOrder {
  private names: string[] = [];
  private states = new Map<string, string>();
  private priorities = new Map<string, string>();
  private scope: string | undefined;
  private epoch = 0;

  update(names: string[], tasks: { id: string; state: string }[], columns: { name: string; priority?: string }[], scope: string) {
    const states = new Map(tasks.map(task => [task.id, task.state]));
    const priorities = new Map(columns.map(column => [column.name, column.priority || '']));
    const changed = scope !== this.scope
      || tasks.some(task => this.states.has(task.id) && this.states.get(task.id) !== task.state)
      || names.some(name => this.names.includes(name) && (priorities.get(name) || '') !== (this.priorities.get(name) || ''));
    const available = new Set(names);
    if (changed) {
      this.names = [...names];
      this.epoch++;
    } else {
      const retained = this.names.filter(name => available.has(name));
      const existing = new Set(retained);
      this.names = [...retained, ...names.filter(name => !existing.has(name))];
    }
    if (available.has('')) this.names = ['', ...this.names.filter(Boolean)];
    this.states = states;
    this.priorities = priorities;
    this.scope = scope;
    return { names: this.names, epoch: this.epoch };
  }
}
