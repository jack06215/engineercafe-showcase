import { fn } from 'storybook/test';

import { LevelChart } from './LevelChart';

import type { Meta, StoryObj } from '@storybook/react-vite';

// SPEC Appendix B's topics in curriculum order, at made-up levels.
const NAMES = [
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

const meta = {
  title: 'charts/LevelChart',
  component: LevelChart,
  args: {
    target: 1850,
    levels: NAMES.map((name, i) => ({
      topicId: name.toLowerCase().replaceAll(' ', '-'),
      name,
      level: 1000 + ((i * 137) % 1050),
    })),
    onTopicClick: fn(),
  },
} satisfies Meta<typeof LevelChart>;

export default meta;

type Story = StoryObj<typeof meta>;

export const AllTopics: Story = {};

export const FreshStart: Story = {
  args: {
    levels: NAMES.map((name) => ({
      topicId: name.toLowerCase().replaceAll(' ', '-'),
      name,
      level: 1300,
    })),
  },
};
