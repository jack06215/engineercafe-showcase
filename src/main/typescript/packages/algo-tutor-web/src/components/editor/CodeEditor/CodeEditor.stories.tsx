import { fn } from 'storybook/test';

import { CodeEditor } from './CodeEditor';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'editor/CodeEditor',
  component: CodeEditor,
  args: {
    label: 'Solution code',
    language: 'python',
    value: [
      'class Solution:',
      '    def twoSum(self, nums: list[int], target: int) -> list[int]:',
      '        seen: dict[int, int] = {}',
      '        for i, x in enumerate(nums):',
      '            if target - x in seen:',
      '                return [seen[target - x], i]',
      '            seen[x] = i',
      '        return []',
    ].join('\n'),
    onChange: fn(),
  },
} satisfies Meta<typeof CodeEditor>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Python: Story = {};

export const Go: Story = {
  args: {
    language: 'go',
    value:
      'func twoSum(nums []int, target int) []int {\n\tseen := map[int]int{}\n\tfor i, x := range nums {\n\t\tif j, ok := seen[target-x]; ok {\n\t\t\treturn []int{j, i}\n\t\t}\n\t\tseen[x] = i\n\t}\n\treturn nil\n}',
  },
};

export const TypeScript: Story = {
  args: {
    language: 'typescript',
    value:
      'function twoSum(nums: number[], target: number): number[] {\n  const seen = new Map<number, number>();\n  for (const [i, x] of nums.entries()) {\n    const j = seen.get(target - x);\n    if (j !== undefined) return [j, i];\n    seen.set(x, i);\n  }\n  return [];\n}',
  },
};

export const ReadOnly: Story = { args: { readOnly: true } };
