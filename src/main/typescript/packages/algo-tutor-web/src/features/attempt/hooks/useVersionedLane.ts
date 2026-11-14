import { useState, useSyncExternalStore } from 'react';

import { type Versioned, VersionedLane } from '../common/lane';

// A lane for `initial` that lives as long as the component, and the record
// and error it currently holds. Remount (a new `key`) for another record.
export const useVersionedLane = <T extends Versioned>(initial: T) => {
  const [lane] = useState(() => new VersionedLane(initial));
  const { record, error } = useSyncExternalStore(
    lane.subscribe,
    lane.getSnapshot,
    lane.getSnapshot,
  );
  return { lane, record, error };
};
