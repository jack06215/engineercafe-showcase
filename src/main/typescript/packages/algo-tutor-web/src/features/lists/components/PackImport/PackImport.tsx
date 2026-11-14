import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import { newIdempotencyKey } from '@/api/client';
import type { PackReport } from '@/api/types';

type Props = {
  onImport: (
    pack: unknown,
    dryRun: boolean,
    idempotencyKey: string,
  ) => Promise<PackReport>;
};

const describe = (report: PackReport) => {
  if (report.already_applied) {
    return 'This pack was already imported; nothing changes.';
  }
  const would = report.dry_run;
  const created = report.lists_created ?? [];
  const extended = report.lists_extended ?? [];
  const lists = [
    created.length > 0 &&
      `${would ? 'create' : 'created'} ${created.join(', ')}`,
    extended.length > 0 &&
      `${would ? 'extend' : 'extended'} ${extended.join(', ')}`,
  ].filter(Boolean);
  return `${[
    `${would ? 'Would add' : 'Added'} ${report.problems_created} new problems (${report.problems_existing} already in the library)`,
    `${report.entries_added} list entries`,
    `${report.patterns_added ?? 0} pattern labels`,
    ...lists,
  ].join(', ')}.`;
};

// Question packs (SPEC §5.9): pick a file, dry run, then apply.
export const PackImport = ({ onImport }: Props) => {
  const [fileName, setFileName] = useState<string | null>(null);
  const [pack, setPack] = useState<unknown>(null);
  const [report, setReport] = useState<PackReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // One key per file: applying twice replays the first import.
  const [applyKey, setApplyKey] = useState(newIdempotencyKey);

  const pick = async (file: File | undefined) => {
    setReport(null);
    setError(null);
    setPack(null);
    setFileName(file?.name ?? null);
    if (!file) return;
    try {
      setPack(JSON.parse(await file.text()));
      setApplyKey(newIdempotencyKey());
    } catch {
      setError(`${file.name} isn't valid JSON.`);
    }
  };

  const run = async (dryRun: boolean) => {
    setBusy(true);
    setError(null);
    try {
      setReport(
        await onImport(pack, dryRun, dryRun ? newIdempotencyKey() : applyKey),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Button variant="outlined" component="label">
          Choose a pack…
          <input
            hidden
            type="file"
            accept="application/json,.json"
            onChange={(e) => void pick(e.target.files?.[0])}
          />
        </Button>
        <Typography variant="body2" color="text.secondary">
          {fileName ?? 'A version 2 question pack (JSON)'}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1}>
        <Button
          variant="outlined"
          disabled={busy || pack === null}
          onClick={() => void run(true)}
        >
          Dry run
        </Button>
        <Button
          variant="contained"
          disabled={busy || pack === null || report === null || !report.dry_run}
          onClick={() => void run(false)}
        >
          Apply
        </Button>
      </Stack>
      {report && (
        <Alert severity={report.dry_run ? 'info' : 'success'}>
          {describe(report)}
        </Alert>
      )}
      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );
};
