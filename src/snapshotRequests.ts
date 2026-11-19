export class SnapshotRequests<T> {
  private pending = new Map<string, Promise<T>>();

  async run(project: string, load: () => Promise<T>, fresh = false): Promise<T> {
    const previous = this.pending.get(project);
    if (previous) {
      if (!fresh) return previous;
      // A mutation must not reuse a snapshot started before its commit.
      await previous.catch(() => undefined);
      return this.run(project, load);
    }
    const request = load().finally(() => {
      if (this.pending.get(project) === request) this.pending.delete(project);
    });
    this.pending.set(project, request);
    return request;
  }
}
