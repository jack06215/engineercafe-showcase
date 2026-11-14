import { fn } from 'storybook/test';

import { VegaLiteChart } from './VegaLiteChart';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'charts/VegaLiteChart',
  component: VegaLiteChart,
  args: {
    spec: {
      $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
      width: 'container',
      height: 240,
      params: [{ name: 'highlight', value: null }],
      data: {
        values: [
          { month: 'Jan', revenue: 42 },
          { month: 'Feb', revenue: 51 },
          { month: 'Mar', revenue: 38 },
          { month: 'Apr', revenue: 64 },
          { month: 'May', revenue: 57 },
        ],
      },
      mark: { type: 'bar', cursor: 'pointer' },
      encoding: {
        x: { field: 'month', type: 'ordinal', sort: null },
        y: { field: 'revenue', type: 'quantitative' },
        opacity: {
          condition: {
            test: 'highlight !== null && datum.month !== highlight',
            value: 0.3,
          },
          value: 1,
        },
      },
    },
    // Clicked bars show up in the Actions panel.
    onDatumClick: fn(),
  },
} satisfies Meta<typeof VegaLiteChart>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

// The `highlight` param set through `signals`, without re-embedding.
export const WithSignal: Story = {
  args: {
    signals: { highlight: 'Apr' },
  },
};
