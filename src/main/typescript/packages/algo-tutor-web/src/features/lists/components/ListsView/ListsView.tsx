import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';

import type {
  BundledSet,
  ListCreated,
  ListEntriesIn,
  ListPreview,
  ListSummary,
  PackReport,
} from '@/api/types';
import { SOURCE_LABEL } from '@/common/format';

import { NewListForm } from '../NewListForm';
import { PackImport } from '../PackImport';

const RouterLink = createLink(Link);

export const COURSES: { set: BundledSet; name: string; blurb: string }[] = [
  {
    set: 'neetcode-150',
    name: 'NeetCode 150',
    blurb: '150 problems in 18 sections',
  },
  { set: 'blind-75', name: 'Blind 75', blurb: 'The classic 75' },
  {
    set: 'hello-interview',
    name: 'Hello Interview',
    blurb: '88 problems in 16 sections',
  },
];

type Props = {
  lists: ListSummary[];
  onFollow: (set: BundledSet) => void;
  onToggleActive: (list: ListSummary) => void;
  onPreview: (body: ListEntriesIn) => Promise<ListPreview>;
  onCreate: (body: ListEntriesIn) => Promise<ListCreated>;
  onImport: (
    pack: unknown,
    dryRun: boolean,
    idempotencyKey: string,
  ) => Promise<PackReport>;
  busy?: boolean;
};

const Section = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <Paper variant="outlined" sx={{ p: 2 }}>
    <Stack spacing={1.5} component="section" aria-label={title}>
      <Typography variant="h6" component="h2">
        {title}
      </Typography>
      {children}
    </Stack>
  </Paper>
);

// Lists (SPEC §5.10, §14 Lists): bundled courses, your own lists and packs.
// One list per source can be active; it fills the daily plan first.
export const ListsView = ({
  lists,
  onFollow,
  onToggleActive,
  onPreview,
  onCreate,
  onImport,
  busy = false,
}: Props) => {
  // A followed course's list is bundled, with the course id as `origin`.
  const followed = (set: BundledSet) =>
    lists.find((l) => l.kind === 'bundled' && l.origin === set);

  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        Lists
      </Typography>

      <Section title="Courses">
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          {COURSES.map(({ set, name, blurb }) => {
            const list = followed(set);
            return (
              <Paper key={set} variant="outlined" sx={{ p: 2, flex: 1 }}>
                <Stack spacing={1}>
                  <Typography variant="subtitle1">{name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {blurb}
                  </Typography>
                  {list ? (
                    <RouterLink to="/lists/$id" params={{ id: list.id }}>
                      Following · {list.done} / {list.total} done
                    </RouterLink>
                  ) : (
                    <div>
                      <Button
                        variant="outlined"
                        size="small"
                        disabled={busy}
                        onClick={() => onFollow(set)}
                      >
                        Follow
                      </Button>
                    </div>
                  )}
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      </Section>

      <Section title="Your lists">
        {lists.length === 0 ? (
          <Typography color="text.secondary">
            No lists yet. Follow a course, paste one below, or import a pack.
          </Typography>
        ) : (
          <Table size="small" aria-label="Lists">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Source</TableCell>
                <TableCell>Kind</TableCell>
                <TableCell sx={{ width: '25%' }}>Progress</TableCell>
                <TableCell>Active</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {lists.map((list) => (
                <TableRow key={list.id} hover>
                  <TableCell>
                    <RouterLink to="/lists/$id" params={{ id: list.id }}>
                      {list.name}
                    </RouterLink>
                  </TableCell>
                  <TableCell>{SOURCE_LABEL[list.source]}</TableCell>
                  <TableCell>
                    <Chip size="small" label={list.kind} />
                  </TableCell>
                  <TableCell>
                    <Stack
                      direction="row"
                      spacing={1}
                      sx={{ alignItems: 'center' }}
                    >
                      <LinearProgress
                        variant="determinate"
                        value={list.total ? (list.done / list.total) * 100 : 0}
                        sx={{ flex: 1, height: 6, borderRadius: 3 }}
                      />
                      <Typography variant="body2">
                        {list.done} / {list.total}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Switch
                      size="small"
                      checked={list.active}
                      disabled={busy}
                      onChange={() => onToggleActive(list)}
                      slotProps={{
                        input: {
                          'aria-label': `Active ${SOURCE_LABEL[list.source]} list: ${list.name}`,
                        },
                      }}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>

      <Section title="New list from entries">
        <NewListForm onPreview={onPreview} onCreate={onCreate} />
      </Section>

      <Section title="Import a question pack">
        <PackImport onImport={onImport} />
      </Section>
    </Stack>
  );
};
