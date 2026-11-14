import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useState } from 'react';

type Props = {
  // Everything typed that the server doesn't have, as one block of text.
  unsavedText: string;
  onReload: () => void;
};

// Shown when a write came back 409 STALE (SPEC §6.5): the record changed
// elsewhere, saving is frozen and the edits exist only on this page.
export const StaleNotice = ({ unsavedText, onReload }: Props) => {
  const [copied, setCopied] = useState<'no' | 'yes' | 'failed'>('no');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(unsavedText);
      setCopied('yes');
    } catch {
      setCopied('failed');
    }
  };

  return (
    <Alert severity="warning" role="alert">
      <Stack spacing={1.5}>
        <span>
          This changed elsewhere, so your latest edits weren't saved. Copy them
          before reloading the saved version: reloading replaces what's on this
          page.
        </span>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Button variant="outlined" size="small" onClick={() => void copy()}>
            {copied === 'yes' ? 'Copied' : 'Copy unsaved text'}
          </Button>
          <Button variant="contained" size="small" onClick={onReload}>
            Reload saved version
          </Button>
          {copied === 'failed' && (
            <span>The clipboard isn't available; select and copy by hand.</span>
          )}
        </Stack>
      </Stack>
    </Alert>
  );
};
