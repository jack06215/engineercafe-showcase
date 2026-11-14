import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useState } from 'react';

import { createProblem } from '@/api/endpoints';
import type { Difficulty, ProblemDetail } from '@/api/types';

type Props = {
  open: boolean;
  onClose: () => void;
  onAdded: (problem: ProblemDetail) => void;
};

const ATCODER = /^https:\/\/atcoder\.jp\/contests\/[^/]+\/tasks\/[^/?#]+/;

// "Add problem" (SPEC §5.1, §14 Library): a LeetCode or AtCoder URL. AtCoder
// is never fetched, so it needs a typed title. Adding one that exists
// returns the existing problem.
export const AddProblemDialog = ({ open, onClose, onAdded }: Props) => {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [difficulty, setDifficulty] = useState<Difficulty | ''>('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const atcoder = ATCODER.test(url.trim());

  const add = async () => {
    setBusy(true);
    setError(null);
    try {
      const added = await createProblem({
        url: url.trim(),
        title: title.trim() || null,
        difficulty: difficulty || null,
      });
      setUrl('');
      setTitle('');
      setDifficulty('');
      onAdded(added);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Add a problem</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="LeetCode or AtCoder URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://leetcode.com/problems/two-sum/"
            autoFocus
          />
          <TextField
            label={
              atcoder ? 'Title (required for AtCoder)' : 'Title (optional)'
            }
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required={atcoder}
            slotProps={{ htmlInput: { maxLength: 300 } }}
          />
          <TextField
            select
            label="Difficulty"
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value as Difficulty | '')}
          >
            <MenuItem value="">None</MenuItem>
            <MenuItem value="Easy">Easy</MenuItem>
            <MenuItem value="Medium">Medium</MenuItem>
            <MenuItem value="Hard">Hard</MenuItem>
          </TextField>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => void add()}
          disabled={
            busy || url.trim() === '' || (atcoder && title.trim() === '')
          }
        >
          Add
        </Button>
      </DialogActions>
    </Dialog>
  );
};
