import type { Decorator, Preview } from '@storybook/react-vite';

import { AppProviders } from '@/common/providers';

import '@/styles/global.scss';

// The theme and query cache. Stories of components that use TanStack Router
// hooks or <Link> need a router too; see the README's Storybook notes.
const withAppProviders: Decorator = (Story) => {
  return (
    <AppProviders>
      <Story />
    </AppProviders>
  );
};

const preview: Preview = {
  // 7.x's `docs: { autodocs: true }`.
  tags: ['autodocs'],
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/,
      },
    },
  },
  decorators: [withAppProviders],
};

export default preview;
