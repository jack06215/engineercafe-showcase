import { describe, expect, it } from 'vitest';

import { LEVEL_FLOOR, levelChartSpec } from './levelChartSpec';

type Spec = {
  height: number;
  data: { values: Record<string, unknown>[] };
  layer: { encoding: Record<string, Record<string, unknown>> }[];
};

const levels = [
  { topicId: 'array', name: 'Array', level: 1849.6 },
  { topicId: 'string', name: 'String', level: 1300 },
  { topicId: 'trie', name: 'Trie', level: 2140 },
];

describe('levelChartSpec', () => {
  it('rounds levels and marks topics at target by the rounded level', () => {
    const spec = levelChartSpec(levels, 1850) as unknown as Spec;
    expect(spec.data.values).toEqual([
      {
        topicId: 'array',
        name: 'Array',
        level: 1850,
        order: 0,
        status: 'At target',
      },
      {
        topicId: 'string',
        name: 'String',
        level: 1300,
        order: 1,
        status: 'Below target',
      },
      {
        topicId: 'trie',
        name: 'Trie',
        level: 2140,
        order: 2,
        status: 'At target',
      },
    ]);
  });

  it('starts bars at 1000, draws the target, and keeps the given order', () => {
    const spec = levelChartSpec(levels, 1850) as unknown as Spec;
    const [bars, rule] = spec.layer;
    expect(bars.encoding.x2).toEqual({ datum: LEVEL_FLOOR });
    expect(bars.encoding.x.scale).toEqual({
      domain: [1000, 2200],
      zero: false,
      nice: false,
    });
    expect(bars.encoding.y.sort).toEqual({ field: 'order' });
    expect(rule.encoding.x.datum).toBe(1850);
  });

  it('is one row per topic tall, for all 34', () => {
    const many = Array.from({ length: 34 }, (_, i) => ({
      topicId: `t${i}`,
      name: `Topic ${i}`,
      level: 1300,
    }));
    const spec = levelChartSpec(many, 1850) as unknown as Spec;
    expect(spec.height).toBe(34 * 18);
    expect(spec.layer[0].encoding.x.scale).toMatchObject({
      domain: [1000, 1900],
    });
  });
});
