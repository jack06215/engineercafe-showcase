import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { getSuggestedPath } from '@/api/endpoints';
import type { AttemptOut, Language } from '@/api/types';
import { formatTimestamp } from '@/common/format';
import { CodeEditor } from '@/components/editor/CodeEditor';

type Props = {
  attempt: AttemptOut;
  code: string;
  language: Language;
  onCodeChange: (code: string) => void;
  // Link (and copy) a repo file; resolves once the server has copied it.
  onLink: (path: string) => Promise<void>;
  // Back to the in-app editor, starting from the last copy.
  onUnlink: () => Promise<void>;
  disabled?: boolean;
};

const PATH_ERRORS: Record<string, string> = {
  SOLUTION_FILE_MISSING: 'There is no file at that path.',
  SOLUTION_PATH_INVALID:
    'That path must be a UTF-8 file inside the repo, at most 1 MB.',
};

const errorText = (error: unknown) => {
  if (error && typeof error === 'object' && 'code' in error) {
    const code = String((error as { code: unknown }).code);
    if (code in PATH_ERRORS) return PATH_ERRORS[code];
  }
  return error instanceof Error ? error.message : String(error);
};

// Where the code comes from (SPEC §6.4): a file in the repo, copied into the
// attempt at every save, or the in-app editor.
export const SolutionSource = ({
  attempt,
  code,
  language,
  onCodeChange,
  onLink,
  onUnlink,
  disabled = false,
}: Props) => {
  const linked = attempt.solution_path !== null;
  const [editingPath, setEditingPath] = useState(false);
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const suggestion = useQuery({
    queryKey: ['suggested-path', attempt.problem.id, language],
    queryFn: () => getSuggestedPath(attempt.problem.id, language),
    enabled: editingPath,
  });
  const shownPath =
    path ?? attempt.solution_path ?? suggestion.data?.path ?? '';

  const link = async (target: string) => {
    setBusy(true);
    setError(null);
    try {
      await onLink(target.trim());
      setEditingPath(false);
      setPath(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const confirmAndLink = () => {
    if (
      !linked &&
      code.trim() !== '' &&
      !window.confirm(
        "Link this file? Its contents replace the code you've written here.",
      )
    ) {
      return;
    }
    void link(shownPath);
  };

  const unlink = async () => {
    if (
      !window.confirm(
        'Switch to the in-app editor? It starts from the last copy of the file.',
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onUnlink();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={1.5}>
      {linked && !editingPath && (
        <Stack spacing={1}>
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: 'center', flexWrap: 'wrap' }}
          >
            <Typography variant="body2">
              Solution file: <code>{attempt.solution_path}</code>
            </Typography>
            {attempt.code_copied_at && (
              <Typography variant="body2" color="text.secondary">
                copied at {formatTimestamp(attempt.code_copied_at)}
              </Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="outlined"
              disabled={disabled || busy}
              onClick={() => void link(attempt.solution_path ?? '')}
            >
              Copy now
            </Button>
            <Button
              size="small"
              disabled={disabled || busy}
              onClick={() => setEditingPath(true)}
            >
              Change path
            </Button>
            <Button
              size="small"
              disabled={disabled || busy}
              onClick={() => void unlink()}
            >
              Use the editor instead
            </Button>
          </Stack>
          <CodeEditor
            label="Copied code"
            language={language}
            value={attempt.code}
            readOnly
            minHeight={160}
          />
        </Stack>
      )}

      {editingPath && (
        <Stack spacing={1}>
          <TextField
            label="Solution file (relative to the repo root)"
            value={shownPath}
            onChange={(e) => setPath(e.target.value)}
            size="small"
            fullWidth
            helperText={
              suggestion.data && !path
                ? suggestion.data.exists
                  ? 'An existing file for this problem.'
                  : 'Suggested path; create the file in your editor first.'
                : ' '
            }
          />
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              size="small"
              disabled={disabled || busy || shownPath.trim() === ''}
              onClick={confirmAndLink}
            >
              Link file
            </Button>
            <Button
              size="small"
              onClick={() => {
                setEditingPath(false);
                setPath(null);
                setError(null);
              }}
            >
              Cancel
            </Button>
          </Stack>
        </Stack>
      )}

      {!linked && !editingPath && (
        <Stack spacing={1}>
          <CodeEditor
            label="Solution code"
            language={language}
            value={code}
            onChange={onCodeChange}
            readOnly={disabled}
          />
          <div>
            <Button
              size="small"
              disabled={disabled}
              onClick={() => setEditingPath(true)}
            >
              Link a file from the repo instead
            </Button>
          </div>
        </Stack>
      )}

      {error !== null && <Alert severity="error">{errorText(error)}</Alert>}
    </Stack>
  );
};
