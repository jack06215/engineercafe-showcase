import { useEffect } from 'react';

// While `when` is true, closing or reloading the tab asks first (the
// browser's own "Leave site?" dialog; its text can't be customised). For
// unsaved drafts, notebook text and an attempt mid-save.
export const useBeforeUnloadGuard = (when: boolean) => {
  useEffect(() => {
    if (!when) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Older browsers still look for returnValue.
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [when]);
};
