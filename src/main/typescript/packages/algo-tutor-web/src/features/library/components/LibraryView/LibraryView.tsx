import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';
import { useState } from 'react';

import type {
  ListSummary,
  PatternSummary,
  ProblemPage,
  ProblemQuery,
} from '@/api/types';
import { formatDay, OUTCOME_LABEL, SOURCE_LABEL } from '@/common/format';
import { formatMmSs } from '@/common/time';
import { RatingChip } from '@/components/ui/RatingChip';

import type { LibrarySearch } from '../../common/search';

const RouterLink = createLink(Link);

type Sort = ProblemQuery['sort'];

type Props = {
  search: LibrarySearch;
  onSearch: (patch: Partial<LibrarySearch>) => void;
  page: ProblemPage | undefined;
  topics: { id: string; name: string }[];
  patterns: PatternSummary[];
  lists: ListSummary[];
};

// One filter: a select whose empty value means "any".
const Filter = ({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | undefined;
  options: [string, string][];
  onChange: (value: string | undefined) => void;
}) => (
  <TextField
    select
    size="small"
    label={label}
    value={value ?? ''}
    onChange={(e) => onChange(e.target.value || undefined)}
    sx={{ minWidth: 150 }}
  >
    <MenuItem value="">Any</MenuItem>
    {options.map(([v, text]) => (
      <MenuItem key={v} value={v}>
        {text}
      </MenuItem>
    ))}
  </TextField>
);

const COLUMNS: { label: string; sort?: Sort }[] = [
  { label: 'Problem', sort: 'title' },
  { label: 'Difficulty', sort: 'difficulty' },
  { label: 'Rating', sort: 'rating' },
  { label: 'Topic' },
  { label: 'Latest', sort: 'latest' },
  { label: 'Time', sort: 'time' },
  { label: 'Confidence', sort: 'confidence' },
  { label: 'Next review', sort: 'next_review' },
];

// The library (SPEC §14 Library): every problem, filtered, sorted and
// paged on the server, with the filters in the URL.
export const LibraryView = ({
  search,
  onSearch,
  page,
  topics,
  patterns,
  lists,
}: Props) => {
  const [q, setQ] = useState(search.q ?? '');
  const sort = search.sort ?? 'title';
  const order = search.order ?? 'asc';
  // Any filter change goes back to the first page.
  const filter = (patch: Partial<LibrarySearch>) =>
    onSearch({ ...patch, page: undefined });
  const topicName = new Map(topics.map((t) => [t.id, t.name]));

  return (
    <Stack spacing={2}>
      <Stack
        component="form"
        role="search"
        direction="row"
        spacing={1.5}
        useFlexGap
        sx={{ flexWrap: 'wrap' }}
        onSubmit={(e: React.FormEvent) => {
          e.preventDefault();
          filter({ q: q.trim() || undefined });
        }}
      >
        <TextField
          size="small"
          label="Search title or URL"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onBlur={() => filter({ q: q.trim() || undefined })}
          sx={{ minWidth: 240 }}
        />
        <Filter
          label="Source"
          value={search.source}
          options={[
            ['leetcode', 'LeetCode'],
            ['atcoder', 'AtCoder'],
          ]}
          onChange={(v) => filter({ source: v as LibrarySearch['source'] })}
        />
        <Filter
          label="Topic"
          value={search.topic}
          options={[
            ['none', 'No topic'],
            ...topics.map((t): [string, string] => [t.id, t.name]),
          ]}
          onChange={(v) => filter({ topic: v })}
        />
        <TextField
          size="small"
          label="LeetCode tag"
          defaultValue={search.tag ?? ''}
          onBlur={(e) => filter({ tag: e.target.value.trim() || undefined })}
          sx={{ minWidth: 150 }}
        />
        <Filter
          label="Pattern"
          value={search.pattern}
          options={patterns.map((p): [string, string] => [p.id, p.name])}
          onChange={(v) => filter({ pattern: v })}
        />
        <Filter
          label="Difficulty"
          value={search.difficulty}
          options={[
            ['Easy', 'Easy'],
            ['Medium', 'Medium'],
            ['Hard', 'Hard'],
          ]}
          onChange={(v) =>
            filter({ difficulty: v as LibrarySearch['difficulty'] })
          }
        />
        <Filter
          label="Latest result"
          value={search.latest}
          options={[
            ['solved', 'Solved'],
            ['not_solved', 'Not solved'],
            ['stopped', 'Stopped'],
            ['not_submitted', 'Not attempted'],
          ]}
          onChange={(v) => filter({ latest: v as LibrarySearch['latest'] })}
        />
        <Filter
          label="List"
          value={search.list_id}
          options={lists.map((l): [string, string] => [l.id, l.name])}
          onChange={(v) => filter({ list_id: v })}
        />
        <Filter
          label="Solve time"
          value={search.time}
          options={[
            ['0-10', '0–10 min'],
            ['10-20', '10–20 min'],
            ['20-30', '20–30 min'],
            ['30-45', '30–45 min'],
            ['45+', '45+ min'],
            ['unknown', 'Unknown'],
          ]}
          onChange={(v) => filter({ time: v as LibrarySearch['time'] })}
        />
        <Filter
          label="Confidence"
          value={search.confidence}
          options={[
            ['low', 'Below 3'],
            ['medium', '3 to 4'],
            ['high', '4 or more'],
            ['unknown', 'Unknown'],
          ]}
          onChange={(v) =>
            filter({ confidence: v as LibrarySearch['confidence'] })
          }
        />
      </Stack>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small" aria-label="Problems">
          <TableHead>
            <TableRow>
              {COLUMNS.map(({ label, sort: key }) => (
                <TableCell
                  key={label}
                  sortDirection={key === sort ? order : false}
                >
                  {key ? (
                    <TableSortLabel
                      active={key === sort}
                      direction={key === sort ? order : 'asc'}
                      onClick={() =>
                        onSearch({
                          sort: key,
                          order:
                            key === sort && order === 'asc' ? 'desc' : 'asc',
                          page: undefined,
                        })
                      }
                    >
                      {label}
                    </TableSortLabel>
                  ) : (
                    label
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {page?.items.map((row) => (
              <TableRow key={row.problem.id} hover>
                <TableCell>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ alignItems: 'center' }}
                  >
                    <RouterLink
                      to="/library/$id"
                      params={{ id: row.problem.id }}
                    >
                      {row.problem.number !== null && `${row.problem.number}. `}
                      {row.problem.title}
                    </RouterLink>
                    {row.problem.source === 'atcoder' && (
                      <Chip size="small" label={SOURCE_LABEL.atcoder} />
                    )}
                    {row.paid_only && <Chip size="small" label="Paid" />}
                  </Stack>
                </TableCell>
                <TableCell>{row.problem.difficulty ?? '–'}</TableCell>
                <TableCell>
                  <RatingChip rating={row.problem.rating} />
                </TableCell>
                <TableCell>
                  {row.topic_id
                    ? (topicName.get(row.topic_id) ?? row.topic_id)
                    : '–'}
                </TableCell>
                <TableCell>
                  {row.latest_outcome ? OUTCOME_LABEL[row.latest_outcome] : '–'}
                </TableCell>
                <TableCell>
                  {row.latest_active_seconds === null
                    ? '–'
                    : formatMmSs(row.latest_active_seconds)}
                </TableCell>
                <TableCell>{row.latest_confidence ?? '–'}</TableCell>
                <TableCell>
                  {row.next_review_date ? formatDay(row.next_review_date) : '–'}
                </TableCell>
              </TableRow>
            ))}
            {page && page.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={COLUMNS.length}>
                  <Typography color="text.secondary">
                    No problems match these filters.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={page?.total ?? 0}
          page={(search.page ?? 1) - 1}
          rowsPerPage={search.page_size ?? 25}
          rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_e, p) => onSearch({ page: p + 1 })}
          onRowsPerPageChange={(e) =>
            onSearch({ page_size: Number(e.target.value), page: undefined })
          }
        />
      </TableContainer>
    </Stack>
  );
};
