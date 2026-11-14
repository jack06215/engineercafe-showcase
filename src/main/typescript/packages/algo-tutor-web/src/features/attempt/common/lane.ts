// One lane for every write to a versioned record (an attempt, a notebook).
//
// Each write carries the record's version and the server refuses a stale
// one with 409 STALE (SPEC §6.5, §18.3). Draft saves, stopwatch heartbeats
// and pause/resume all bump an attempt's version, so they must not race:
// they run here one at a time, and each operation receives the record as
// the previous one left it. Never capture a version outside the lane.
//
// The first failure freezes the lane: later operations fail with the same
// error until `clearError` (retry) or `replace` (reload the saved record).
// Ported from BloomCode's AttemptQueue, plus a subscription for React.

export type Versioned = { version: number };

export type LaneSnapshot<T> = {
  record: T;
  error: unknown;
};

export class VersionedLane<T extends Versioned> {
  private tail: Promise<unknown> = Promise.resolve();
  private listeners = new Set<() => void>();
  private snapshot: LaneSnapshot<T>;

  constructor(initial: T) {
    this.snapshot = { record: initial, error: null };
  }

  // The latest committed record. (Not `current`: the React Compiler
  // treats any `.current` as a ref.)
  get record(): T {
    return this.snapshot.record;
  }

  get error(): unknown {
    return this.snapshot.error;
  }

  // Queue `operation` behind every earlier one. It gets the latest committed
  // record and returns the server's new copy, which becomes `record`.
  run(operation: (current: T) => Promise<T>): Promise<T> {
    const next = this.tail.then(async () => {
      if (this.snapshot.error) throw this.snapshot.error;
      try {
        const committed = await operation(this.snapshot.record);
        this.set({ record: committed, error: null });
        return committed;
      } catch (error) {
        this.set({ ...this.snapshot, error });
        throw error;
      }
    });
    this.tail = next.catch(() => undefined);
    return next;
  }

  // Unfreeze, keeping the record (for retrying after a network error).
  clearError(): void {
    if (this.snapshot.error) this.set({ ...this.snapshot, error: null });
  }

  // Take a freshly loaded record and unfreeze (after "Reload saved version").
  replace(record: T): void {
    this.set({ record, error: null });
  }

  // For useSyncExternalStore: arrow properties, so they can be passed bare.
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): LaneSnapshot<T> => this.snapshot;

  private set(snapshot: LaneSnapshot<T>): void {
    this.snapshot = snapshot;
    for (const listener of this.listeners) listener();
  }
}

// Run `operation` in the lane, but let failures `soft` accepts (a bad path,
// a refused form, the tutor being down) through without freezing it: the
// lane keeps its record and the caller gets the error.
export const runSoft = async <T extends Versioned>(
  lane: VersionedLane<T>,
  operation: (current: T) => Promise<T>,
  soft: (error: unknown) => boolean,
): Promise<T> => {
  let failure: { error: unknown } | null = null;
  const result = await lane.run(async (current) => {
    try {
      return await operation(current);
    } catch (error) {
      if (!soft(error)) throw error;
      failure = { error };
      return current;
    }
  });
  if (failure) throw (failure as { error: unknown }).error;
  return result;
};
