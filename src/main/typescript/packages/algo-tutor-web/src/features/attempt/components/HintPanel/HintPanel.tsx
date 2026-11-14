import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import type { HintMessage } from '@/api/types';
import { formatMmSs } from '@/common/time';
import { Markdown } from '@/components/ui/Markdown';
import { tutorErrorText } from '@/features/tutor/common/tutorError';

type Props = {
  messages: HintMessage[];
  // Sends a message; resolves once Algo-chan has answered.
  onSend: (text: string) => Promise<void>;
  // Why the panel can't be used now (the tutor is off), if so.
  unavailable?: string | null;
  disabled?: boolean;
};

const TutorMessage = ({ message }: { message: HintMessage }) => (
  <Paper variant="outlined" sx={{ p: 1.5 }}>
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Typography variant="subtitle2">Algo-chan</Typography>
        {message.level && (
          <Chip
            size="small"
            label={message.level === 'major' ? 'Major hint' : 'Small hint'}
            color={message.level === 'major' ? 'warning' : 'default'}
          />
        )}
      </Stack>
      {message.analysis && (
        <Typography variant="body2" color="text.secondary">
          Where you were: {message.analysis}
        </Typography>
      )}
      <Markdown>{message.text}</Markdown>
    </Stack>
  </Paper>
);

const LearnerMessage = ({
  text,
  stuckAt,
}: {
  text: string;
  stuckAt: number | null;
}) => (
  <Paper
    variant="outlined"
    sx={{
      p: 1.5,
      alignSelf: 'flex-end',
      maxWidth: '90%',
      bgcolor: 'action.hover',
    }}
  >
    {stuckAt !== null && (
      <Typography variant="caption" color="text.secondary" component="div">
        Stuck at {formatMmSs(stuckAt)}
      </Typography>
    )}
    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
      {text}
    </Typography>
  </Paper>
);

// Interview hints from Algo-chan during an attempt (SPEC §12.5). Each hint
// is also written into the attempt's notes by the server.
export const HintPanel = ({
  messages,
  onSend,
  unavailable = null,
  disabled = false,
}: Props) => {
  const [text, setText] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const send = async () => {
    const message = text.trim();
    if (!message) return;
    setPending(message);
    setError(null);
    setText('');
    try {
      await onSend(message);
    } catch (e) {
      setError(e);
      setText(message);
    } finally {
      setPending(null);
    }
  };

  return (
    <Stack spacing={1.5} component="section" aria-label="Ask Algo-chan">
      <Typography variant="h6" component="h2">
        Ask Algo-chan
      </Typography>
      {unavailable ? (
        <Alert severity="info">{unavailable}</Alert>
      ) : (
        <>
          {messages.length === 0 && !pending && (
            <Typography variant="body2" color="text.secondary">
              Stuck? Say where you are. Algo-chan answers like an interviewer:
              the smallest useful nudge, never the full solution.
            </Typography>
          )}
          <Stack spacing={1}>
            {messages.map((m) =>
              m.role === 'tutor' ? (
                <TutorMessage key={m.id} message={m} />
              ) : (
                <LearnerMessage
                  key={m.id}
                  text={m.text}
                  stuckAt={m.stuck_at_seconds}
                />
              ),
            )}
            {pending && <LearnerMessage text={pending} stuckAt={null} />}
            {pending && (
              <Typography variant="body2" color="text.secondary" role="status">
                Algo-chan is thinking…
              </Typography>
            )}
          </Stack>
          {error !== null && (
            <Alert severity="error">{tutorErrorText(error)}</Alert>
          )}
          <TextField
            multiline
            minRows={2}
            size="small"
            label="Your message"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={disabled || pending !== null}
            slotProps={{ htmlInput: { maxLength: 4000 } }}
          />
          <div>
            <Button
              variant="outlined"
              onClick={() => void send()}
              disabled={disabled || pending !== null || text.trim() === ''}
            >
              Ask for a hint
            </Button>
          </div>
        </>
      )}
    </Stack>
  );
};
