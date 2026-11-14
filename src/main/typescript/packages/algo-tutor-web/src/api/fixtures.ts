// Sample contract values for tests and stories. Each builder takes
// overrides, so a test states only what it cares about.
import type {
  AttemptOut,
  Desk,
  ListDetail,
  ListSummary,
  Notebook,
  PatternDetail,
  PlanItemOut,
  PlanOut,
  ProblemBrief,
  ProblemDetail,
  ProblemRow,
  Report,
  SettingsOut,
  TopicDetail,
  TopicLevel,
  TopicLevels,
} from './types';

export const NOW = '2026-11-08T09:00:00Z';
export const TODAY = '2026-11-08';

export const problemBrief = (o: Partial<ProblemBrief> = {}): ProblemBrief => ({
  id: 'p-two-sum',
  source: 'leetcode',
  title: 'Two Sum',
  url: 'https://leetcode.com/problems/two-sum/',
  number: 1,
  contest: null,
  difficulty: 'Easy',
  rating: { value: 1149, estimated: true },
  ...o,
});

export const report = (o: Partial<Report> = {}): Report => ({
  status: 'none',
  summary: null,
  strengths: null,
  improvements: null,
  complexity: null,
  practice: null,
  error_kind: null,
  error_message: null,
  model: null,
  reported_at: null,
  ...o,
});

export const attempt = (o: Partial<AttemptOut> = {}): AttemptOut => ({
  id: 'a-1',
  problem: problemBrief(),
  plan_item_id: 'i-1',
  context: 'targeted',
  evidence: 'near_transfer',
  status: 'active',
  version: 1,
  language: 'python',
  code: '',
  solution_path: null,
  code_copied_at: null,
  notes: '',
  outcome: null,
  help: 'unknown',
  confidence: null,
  active_seconds: 0,
  gap_seconds: 0,
  running_since: NOW,
  last_heartbeat_at: NOW,
  needs_gap_decision: false,
  started_at: NOW,
  finished_at: null,
  study_date: TODAY,
  next_review_date: null,
  strongest_hint: null,
  takeaway: null,
  mistake_labels: null,
  signals: null,
  patterns: null,
  report: null,
  server_now: NOW,
  ...o,
});

export const completedAttempt = (o: Partial<AttemptOut> = {}): AttemptOut =>
  attempt({
    status: 'completed',
    version: 5,
    code: 'class Solution:\n    def twoSum(self, nums, target):\n        ...',
    outcome: 'solved',
    help: 'none',
    confidence: 4,
    active_seconds: 754,
    running_since: null,
    finished_at: '2026-11-08T09:12:34Z',
    next_review_date: '2026-11-22',
    takeaway: '',
    mistake_labels: [],
    signals: { accepted_first_try: null, difficulty: null },
    patterns: [],
    report: report(),
    ...o,
  });

export const planItem = (o: Partial<PlanItemOut> = {}): PlanItemOut => ({
  id: 'i-1',
  lane: 'leetcode',
  position: 0,
  problem: problemBrief(),
  attempt_id: null,
  status: 'active',
  reason: 'Hash Table · your level 1300',
  kind: 'topic',
  disposition: null,
  is_check: false,
  signals: null,
  ...o,
});

export const plan = (
  items: PlanItemOut[],
  o: Partial<PlanOut> = {},
): PlanOut => ({
  id: 'plan-1',
  plan_date: TODAY,
  timezone: 'Asia/Tokyo',
  version: 3,
  items,
  ...o,
});

export const desk = (o: Partial<Desk> = {}): Desk => {
  const items = [
    planItem(),
    planItem({
      id: 'i-2',
      position: 1,
      status: 'queued',
      problem: problemBrief({
        id: 'p-check',
        title: 'Longest Consecutive Sequence',
        number: 128,
        difficulty: 'Medium',
        rating: { value: 1610, estimated: false },
      }),
      reason: 'Transfer check — spot the approach yourself',
      kind: null,
      is_check: true,
    }),
    planItem({
      id: 'i-3',
      lane: 'atcoder',
      position: 0,
      status: 'queued',
      problem: problemBrief({
        id: 'p-abc174-e',
        source: 'atcoder',
        title: 'Logs',
        url: 'https://atcoder.jp/contests/abc174/tasks/abc174_e',
        number: null,
        contest: 'abc174',
        difficulty: null,
        rating: null,
      }),
      reason: 'From Tessoku book, chapter 1',
      kind: 'list',
    }),
  ];
  return {
    hidden_assessment: false,
    active_attempt: null,
    today: TODAY,
    plan: plan(items),
    left_today: 3,
    total_today: 3,
    checks_due: 1,
    bank_empty: false,
    ...o,
  };
};

export const hiddenDesk = (): Desk => ({
  hidden_assessment: true,
  active_attempt: {
    id: 'a-check',
    problem_title: null,
    context: 'mixed',
    status: 'active',
  },
  today: TODAY,
  plan: null,
  left_today: 0,
  total_today: 0,
  checks_due: 0,
  bank_empty: false,
});

export const problemRow = (o: Partial<ProblemRow> = {}): ProblemRow => ({
  problem: problemBrief(),
  topic_id: 'hash-table',
  source_tags: ['Array', 'Hash Table'],
  patterns: [],
  paid_only: false,
  popularity: 99,
  latest_outcome: 'solved',
  latest_active_seconds: 754,
  latest_confidence: 4,
  next_review_date: '2026-11-22',
  ...o,
});

export const problemDetail = (
  o: Partial<ProblemDetail> = {},
): ProblemDetail => ({
  problem: problemBrief(),
  external_id: 'two-sum',
  paid_only: false,
  source_tags: ['Array', 'Hash Table'],
  neetcode_category: 'Arrays & Hashing',
  topic_id: 'hash-table',
  topic_overridden: false,
  patterns: ['02_two_pointers'],
  notes: '',
  exposed: true,
  lists: [{ id: 'l-nc150', name: 'NeetCode 150' }],
  review: {
    problem_id: 'p-two-sum',
    recommended_date: '2026-11-22',
    effective_date: '2026-11-22',
    action: 'recommended',
    stage: 'mixed',
    version: 2,
  },
  attempts: [
    {
      id: 'a-1',
      problem_id: 'p-two-sum',
      status: 'completed',
      context: 'targeted',
      language: 'python',
      outcome: 'solved',
      help: 'none',
      confidence: 4,
      active_seconds: 754,
      started_at: NOW,
      finished_at: '2026-11-08T09:12:34Z',
      study_date: TODAY,
    },
  ],
  ...o,
});

export const listSummary = (o: Partial<ListSummary> = {}): ListSummary => ({
  id: 'l-nc150',
  name: 'NeetCode 150',
  source: 'leetcode',
  kind: 'bundled',
  origin: 'neetcode-150',
  source_url: null,
  created_at: NOW,
  active: true,
  done: 12,
  total: 150,
  ...o,
});

export const listDetail = (o: Partial<ListDetail> = {}): ListDetail => ({
  summary: listSummary({
    id: 'l-own',
    name: 'Warm-up',
    kind: 'own',
    origin: null,
    total: 2,
    done: 1,
  }),
  entries: [
    {
      problem: problemBrief(),
      position: 0,
      section: null,
      added_at: NOW,
      done: true,
    },
    {
      problem: problemBrief({
        id: 'p-valid',
        title: 'Valid Anagram',
        number: 242,
      }),
      position: 1,
      section: null,
      added_at: NOW,
      done: false,
    },
  ],
  ...o,
});

export const topicLevel = (o: Partial<TopicLevel> = {}): TopicLevel => ({
  id: 'hash-table',
  name: 'Hash Table',
  curriculum: 3,
  level: 1312,
  at_target: false,
  attempts: 1,
  last_change: {
    delta: 12,
    attempt_id: 'a-1',
    problem_title: 'Two Sum',
    rating: 1149,
    estimated: true,
    result: 'strong',
    study_date: TODAY,
  },
  ...o,
});

export const TOPIC_NAMES = [
  'Array',
  'String',
  'Hash Table',
  'Two Pointers',
  'Sliding Window',
  'Prefix Sum',
  'Stack',
  'Queue',
  'Linked List',
  'Binary Search',
  'Recursion',
  'Tree',
  'Binary Search Tree',
  'DFS',
  'BFS',
  'Priority Queue',
  'Backtracking',
  'Greedy',
  'Graph',
  'Trie',
  'Union Find',
  'Monotonic Stack',
  'Monotonic Queue',
  'Sorted Container',
  'Divide And Conquer',
  'Dynamic Programming',
  'Bit Manipulation',
  'Math',
  'Shortest Path',
  'Sweep Line',
  'Design',
  'Simulation',
  'Brute Force',
  'Observation',
];

export const topicLevels = (): TopicLevels => ({
  target_rating: 1850,
  topics: TOPIC_NAMES.map((name, i) =>
    topicLevel({
      id: name.toLowerCase().replaceAll(' ', '-'),
      name,
      curriculum: i + 1,
      level: i === 2 ? 1312 : 1300,
      attempts: i === 2 ? 1 : 0,
      last_change: i === 2 ? topicLevel().last_change : null,
    }),
  ),
});

export const notebook = (o: Partial<Notebook> = {}): Notebook => ({
  cues: '',
  pitfalls: '',
  notes: '',
  version: 1,
  updated_at: null,
  ...o,
});

export const topicDetail = (o: Partial<TopicDetail> = {}): TopicDetail => ({
  level: topicLevel(),
  target_rating: 1850,
  notebook: notebook(),
  problems: [
    { problem: problemBrief(), attempts: 1, latest_outcome: 'solved' },
  ],
  unseen_count: 41,
  ...o,
});

export const patternDetail = (
  o: Partial<PatternDetail> = {},
): PatternDetail => ({
  pattern: {
    id: '01_sliding_window',
    name: 'Sliding Window',
    position: 1,
    missing: false,
    problems: 1,
  },
  readme_path:
    'packages/programming_exercise/common_coding_pattern/01_sliding_window/README.md',
  readme_markdown:
    '# Sliding Window\n\nKeep a window over a contiguous range and slide it.\n\nSee [the solutions](./maximum_sum_subarray.py).',
  notebook: notebook(),
  problems: [],
  ...o,
});

export const settings = (o: Partial<SettingsOut> = {}): SettingsOut => ({
  timezone: 'Asia/Tokyo',
  questions_per_day: 2,
  atcoder_per_day: 0,
  target_rating: 1850,
  include_paid_only: false,
  onboarding_complete: true,
  active_list_leetcode: null,
  active_list_atcoder: null,
  last_backup_at: NOW,
  bank: {
    status: 'done',
    fetched_at: NOW,
    pages_done: 37,
    pages_total: 37,
    problems: 3120,
    estimated: 2410,
    method: 'ridge-v1 mae=148',
    unknown_tags: [],
    error: null,
  },
  ...o,
});
