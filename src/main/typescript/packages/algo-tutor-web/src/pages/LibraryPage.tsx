import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useState } from 'react';

import { isApiError } from '@/api/client';
import {
  listsQuery,
  patternsQuery,
  problemsQuery,
  topicsQuery,
} from '@/api/queries';
import { ApiUnavailable } from '@/components/ui/ApiUnavailable';
import { LockedNotice } from '@/components/ui/LockedNotice';
import {
  type LibrarySearch,
  toProblemQuery,
} from '@/features/library/common/search';
import { AddProblemDialog } from '@/features/library/components/AddProblemDialog';
import { LibraryView } from '@/features/library/components/LibraryView';

type Props = {
  search: LibrarySearch;
};

export const LibraryPage = ({ search }: Props) => {
  const navigate = useNavigate();
  const [adding, setAdding] = useState(false);
  const problems = useQuery({
    ...problemsQuery(toProblemQuery(search)),
    placeholderData: keepPreviousData,
  });
  const topics = useQuery(topicsQuery);
  const patterns = useQuery(patternsQuery);
  const lists = useQuery(listsQuery);

  const onSearch = (patch: Partial<LibrarySearch>) =>
    void navigate({
      to: '/library',
      search: (previous) => ({ ...previous, ...patch }),
      replace: true,
    });

  return (
    <Stack spacing={2}>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'center' }}
      >
        <Typography variant="h4" component="h1">
          Library
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setAdding(true)}
        >
          Add problem
        </Button>
      </Stack>
      {problems.isError ? (
        isApiError(problems.error, 'HIDDEN_ASSESSMENT') ? (
          <LockedNotice />
        ) : (
          <ApiUnavailable
            error={problems.error}
            onRetry={() => void problems.refetch()}
          />
        )
      ) : (
        <>
          {problems.isFetching && <LinearProgress aria-label="Loading" />}
          <LibraryView
            search={search}
            onSearch={onSearch}
            page={problems.data}
            topics={topics.data?.topics ?? []}
            patterns={patterns.data ?? []}
            lists={lists.data ?? []}
          />
        </>
      )}
      <AddProblemDialog
        open={adding}
        onClose={() => setAdding(false)}
        onAdded={(added) => {
          setAdding(false);
          void navigate({
            to: '/library/$id',
            params: { id: added.problem.id },
          });
        }}
      />
    </Stack>
  );
};
