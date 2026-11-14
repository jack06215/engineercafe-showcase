import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQueryClient } from '@tanstack/react-query';
import { createLink, useNavigate } from '@tanstack/react-router';

import { cancelAttempt } from '@/api/endpoints';
import { keys } from '@/api/queries';
import type { AttemptOut } from '@/api/types';
import { RatingChip } from '@/components/ui/RatingChip';

import { sourceName } from '../../common/attempt';
import { useVersionedLane } from '../../hooks/useVersionedLane';

import { ActiveAttempt } from './ActiveAttempt';
import { CompletedAttempt } from './CompletedAttempt';

const ButtonLink = createLink(Button);

type Props = {
  initial: AttemptOut;
};

// The attempt page (SPEC §14 Attempt), full-window. Remount it (a `key`) for
// another attempt: the write lane belongs to one record.
export const AttemptScreen = ({ initial }: Props) => {
  const { lane, record } = useVersionedLane(initial);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const completed = record.status === 'completed';

  const cancel = async () => {
    if (
      !window.confirm('Cancel this attempt? Its code and notes are deleted.')
    ) {
      return;
    }
    await cancelAttempt(record.id);
    await queryClient.invalidateQueries({ queryKey: keys.desk });
    await navigate({ to: '/' });
  };

  return (
    <Stack spacing={2}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ justifyContent: 'space-between', flexWrap: 'wrap' }}
      >
        <ButtonLink to="/" startIcon={<ArrowBackIcon />}>
          Back to the desk
        </ButtonLink>
        <Stack direction="row" spacing={1}>
          {completed && (
            <ButtonLink
              to="/library/$id"
              params={{ id: record.problem.id }}
              variant="outlined"
            >
              Problem page
            </ButtonLink>
          )}
          <Button
            variant="outlined"
            href={record.problem.url}
            target="_blank"
            rel="noreferrer"
            endIcon={<OpenInNewIcon />}
          >
            Open on {sourceName(record)}
          </Button>
          {!completed && (
            <Button color="error" onClick={() => void cancel()}>
              Cancel attempt
            </Button>
          )}
        </Stack>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Typography variant="h4" component="h1">
          {record.problem.title}
        </Typography>
        <RatingChip rating={record.problem.rating} />
      </Stack>
      {completed ? (
        <CompletedAttempt lane={lane} record={record} />
      ) : (
        <ActiveAttempt lane={lane} />
      )}
    </Stack>
  );
};
