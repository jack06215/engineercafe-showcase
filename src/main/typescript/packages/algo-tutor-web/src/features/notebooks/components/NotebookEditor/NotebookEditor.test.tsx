import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/api/client';
import { notebook } from '@/api/fixtures';
import type { NotebookPatch } from '@/api/types';
import { routeRenderComponent } from '@/common/test-utils';

import { NotebookEditor } from './NotebookEditor';

afterEach(() => {
  localStorage.clear();
});

describe('NotebookEditor', () => {
  it('saves with the version, and keeps changes over a stale write', async () => {
    const onSave = vi
      .fn<(patch: NotebookPatch) => Promise<ReturnType<typeof notebook>>>()
      .mockRejectedValueOnce(new ApiError(409, 'STALE', 'changed elsewhere'))
      .mockImplementation(async (patch) =>
        notebook({
          cues: patch.cues ?? '',
          pitfalls: patch.pitfalls ?? '',
          notes: patch.notes ?? '',
          version: patch.version + 1,
          updated_at: '2026-11-08T10:00:00Z',
        }),
      );
    const loadSaved = vi.fn(async () =>
      notebook({ version: 4, cues: 'theirs' }),
    );
    routeRenderComponent(
      <NotebookEditor
        notebook={notebook({ version: 3 })}
        storageKey="topic:array"
        onSave={onSave}
        loadSaved={loadSaved}
      />,
    );

    await userEvent.type(
      await screen.findByLabelText('Recognition cues'),
      'pairs',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Save notebook' }),
    );
    await userEvent.click(
      await screen.findByRole('button', {
        name: 'Refresh saved version, keep my changes',
      }),
    );
    expect(screen.getByLabelText('Recognition cues')).toHaveValue('pairs');

    await userEvent.click(
      screen.getByRole('button', { name: 'Save notebook' }),
    );
    await waitFor(() =>
      expect(screen.getByText(/^Saved /)).toBeInTheDocument(),
    );
    expect(onSave).toHaveBeenLastCalledWith({
      version: 4,
      cues: 'pairs',
      pitfalls: '',
      notes: '',
    });
  });

  it('offers to restore a recovery draft left in this browser', async () => {
    localStorage.setItem(
      'algo-tutor.notebook-draft.pattern:01',
      JSON.stringify({ cues: 'left behind', pitfalls: '', notes: '' }),
    );
    routeRenderComponent(
      <NotebookEditor
        notebook={notebook()}
        storageKey="pattern:01"
        onSave={vi.fn()}
        loadSaved={vi.fn()}
      />,
    );
    await userEvent.click(
      await screen.findByRole('button', { name: 'Restore' }),
    );
    expect(screen.getByLabelText('Recognition cues')).toHaveValue(
      'left behind',
    );
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });
});
