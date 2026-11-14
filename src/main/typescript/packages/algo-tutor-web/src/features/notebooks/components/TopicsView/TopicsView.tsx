import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';

import type { LevelChange, TopicLevel, TopicLevels } from '@/api/types';
import { LEVEL_FLOOR, LevelChart } from '@/components/charts/LevelChart';

const RouterLink = createLink(Link);

// "+12 after Two Sum (≈1732)" (SPEC §7.3).
export const describeChange = (change: LevelChange): string =>
  `${change.delta >= 0 ? '+' : ''}${change.delta} after ${change.problem_title} (${
    change.estimated ? '≈' : ''
  }${change.rating})`;

export const LevelBadge = ({ topic }: { topic: TopicLevel }) =>
  topic.at_target ? (
    <Chip size="small" color="success" label="At target" />
  ) : topic.last_change?.result === 'struggled' ? (
    <Chip size="small" color="warning" label="Last: struggled" />
  ) : null;

export const LevelBar = ({
  level,
  target,
}: {
  level: number;
  target: number;
}) => (
  <LinearProgress
    variant="determinate"
    aria-label={`Level ${level} of ${target}`}
    value={Math.max(
      0,
      Math.min(100, ((level - LEVEL_FLOOR) / (target - LEVEL_FLOOR)) * 100),
    )}
    sx={{ height: 8, borderRadius: 4, minWidth: 120 }}
  />
);

type Props = {
  levels: TopicLevels;
  onTopic: (topicId: string) => void;
};

// Topics (SPEC §7.3, §14 Topics): the 34 levels against the target.
export const TopicsView = ({ levels, onTopic }: Props) => {
  const target = levels.target_rating;
  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        Topics
      </Typography>
      <Typography color="text.secondary">
        Your training level per topic, on LeetCode's contest-rating scale.
        Target {target.toLocaleString('en')}.
      </Typography>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <LevelChart
          levels={levels.topics.map((t) => ({
            topicId: t.id,
            name: t.name,
            level: t.level,
          }))}
          target={target}
          onTopicClick={onTopic}
        />
      </Paper>
      <Paper variant="outlined">
        <Table size="small" aria-label="Training levels">
          <TableHead>
            <TableRow>
              <TableCell>Topic</TableCell>
              <TableCell>Level</TableCell>
              <TableCell sx={{ width: '30%' }}>Progress</TableCell>
              <TableCell>Last change</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {levels.topics.map((topic) => (
              <TableRow key={topic.id} hover>
                <TableCell>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ alignItems: 'center' }}
                  >
                    <RouterLink to="/topics/$id" params={{ id: topic.id }}>
                      {topic.name}
                    </RouterLink>
                    <LevelBadge topic={topic} />
                  </Stack>
                </TableCell>
                <TableCell>{topic.level}</TableCell>
                <TableCell>
                  <LevelBar level={topic.level} target={target} />
                </TableCell>
                <TableCell>
                  {topic.last_change
                    ? describeChange(topic.last_change)
                    : 'Not practised yet'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
};
