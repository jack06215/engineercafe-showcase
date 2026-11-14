import { describe, expect, it } from 'vitest';

import { repoPathFor } from './repoPath';

const README =
  'packages/programming_exercise/common_coding_pattern/01_sliding_window/README.md';

describe('repoPathFor', () => {
  it.each([
    [
      './fruits.py',
      'packages/programming_exercise/common_coding_pattern/01_sliding_window/fruits.py',
    ],
    [
      'fruits.py#L3',
      'packages/programming_exercise/common_coding_pattern/01_sliding_window/fruits.py',
    ],
    [
      '../02_two_pointers/README.md',
      'packages/programming_exercise/common_coding_pattern/02_two_pointers/README.md',
    ],
    ['/docs/x.md', 'docs/x.md'],
  ])('%s → %s', (href, path) => {
    expect(repoPathFor(README, href)).toBe(path);
  });

  it('keeps absolute URLs and drops in-page anchors', () => {
    expect(repoPathFor(README, 'https://leetcode.com/')).toBe(
      'https://leetcode.com/',
    );
    expect(repoPathFor(README, '#complexity')).toBeNull();
  });
});
