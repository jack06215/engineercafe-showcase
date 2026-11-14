import { fn } from 'storybook/test';

import { listSummary, NOW, settings } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { SettingsView } from './SettingsView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'settings/SettingsView',
  component: SettingsView,
  decorators: [withRouter],
  args: {
    settings: settings({ active_list_leetcode: 'l-nc150' }),
    bank: settings().bank,
    lists: [listSummary()],
    backup: {
      last_backup_at: NOW,
      path: '.data/backups/algo_tutor-20261108.sqlite',
      kept: 7,
    },
    tutor: {
      enabled: true,
      provider: 'ollama',
      model: 'qwen3.6:35b',
      leaves_machine: false,
      pending_reports: 0,
    },
    onSave: fn(async () => {}),
    onRefreshBank: fn(async () => {}),
    onBackup: fn(async () => {}),
    onTestTutor: fn(async () => ({
      ok: true,
      provider: 'ollama',
      model: 'qwen3.6:35b',
      latency_ms: 840,
      error_kind: null,
      message: null,
    })),
    onReplan: fn(async () => {}),
  },
} satisfies Meta<typeof SettingsView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const BankDownloading: Story = {
  args: { bank: { ...settings().bank, status: 'running' } },
};
