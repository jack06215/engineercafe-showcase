import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Testing Library only unmounts between tests by itself when the test
// runner's globals are on; Vitest's are off here.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

// jsdom has no matchMedia; MUI's color-scheme manager asks it for the OS's
// light/dark preference. Answer "light", as a fresh browser would.
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// jsdom doesn't implement scrolling; TanStack Router restores the scroll
// position on every navigation.
window.scrollTo = () => {};
