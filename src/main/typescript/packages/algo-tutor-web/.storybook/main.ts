import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(ts|tsx)'],
  // Actions, controls, interactions and the rest of 7.x's addon-essentials
  // are built into Storybook itself since 9; only docs is still an addon.
  addons: ['@storybook/addon-links', '@storybook/addon-docs'],
  framework: '@storybook/react-vite',
};

export default config;
