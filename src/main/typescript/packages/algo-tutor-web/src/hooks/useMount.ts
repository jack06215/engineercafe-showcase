import { useEffect, useRef } from 'react';

/**
 * Runs `effect` once per mounted component, in development and production.
 *
 * StrictMode in development mounts, unmounts and remounts every component, so
 * a plain `useEffect(effect, [])` runs twice there. The ref survives that
 * remount and keeps the second run from firing.
 *
 * There is no cleanup: StrictMode would call it on the simulated unmount and
 * never set the effect up again. Effects that need cleanup belong in a plain
 * useEffect, which React expects to be safe to run twice.
 *
 * Upstream skipped the first run instead and relied on StrictMode's second
 * one, so `effect` never ran in production.
 *
 * @see {@link https://react.dev/reference/react/StrictMode#fixing-bugs-found-by-re-running-effects-in-development}
 */
export const useMount = (effect: () => void) => {
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) {
      return;
    }

    ranRef.current = true;
    effect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
