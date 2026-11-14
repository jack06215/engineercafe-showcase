import { useBlocker } from '@tanstack/react-router';

import { useBeforeUnloadGuard } from './useBeforeUnloadGuard';

// While `when` is true, both closing the tab and moving to another page in
// the app ask first (SPEC §11: "asks before you leave with unsaved changes").
export const useLeaveGuard = (
  when: boolean,
  message = 'You have unsaved changes. Leave anyway?',
) => {
  useBeforeUnloadGuard(when);
  useBlocker({
    shouldBlockFn: () => when && !window.confirm(message),
    enableBeforeUnload: false,
  });
};
