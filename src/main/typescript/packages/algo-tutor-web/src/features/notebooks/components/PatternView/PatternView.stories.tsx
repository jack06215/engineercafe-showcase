import { fn } from 'storybook/test';

import { notebook, patternDetail } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { PatternView } from './PatternView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'notebooks/PatternView',
  component: PatternView,
  decorators: [withRouter],
  args: {
    detail: patternDetail(),
    onSave: fn(async () => notebook({ version: 2 })),
    loadSaved: fn(async () => notebook()),
  },
} satisfies Meta<typeof PatternView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithReadme: Story = {};

export const ReadmeMissing: Story = {
  args: { detail: patternDetail({ readme_markdown: null }) },
};
