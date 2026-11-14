import type { TopLevelSpec } from 'vega-lite';

// SPEC §7.1: levels never drop below 1000, so every bar starts there.
export const LEVEL_FLOOR = 1000;

export type TopicLevel = {
  topicId: string;
  name: string;
  level: number;
};

const ROW_PX = 18;

// A horizontal bar per topic, from 1000 to its level, with a rule at the
// target (SPEC §7.3, §14 Topics). Topics keep the order given. A topic is
// "at target" when its rounded level reaches the target.
export const levelChartSpec = (
  levels: readonly TopicLevel[],
  target: number,
): TopLevelSpec => {
  const values = levels.map((t, order) => {
    const level = Math.round(t.level);
    return {
      topicId: t.topicId,
      name: t.name,
      level,
      order,
      status: level >= target ? 'At target' : 'Below target',
    };
  });
  const highest = Math.max(target, ...values.map((v) => v.level));
  // Leave room past the target so its rule isn't on the chart's edge.
  const domainMax = Math.ceil((highest + 50) / 100) * 100;
  const scale = { domain: [LEVEL_FLOOR, domainMax], zero: false, nice: false };

  return {
    $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
    width: 'container',
    // A numeric height: `{ step }` with a container width drops fit-y.
    height: Math.max(ROW_PX, values.length * ROW_PX),
    data: { values },
    layer: [
      {
        mark: { type: 'bar', cursor: 'pointer', cornerRadiusEnd: 2 },
        encoding: {
          y: {
            field: 'name',
            type: 'nominal',
            title: null,
            sort: { field: 'order' },
          },
          x: { field: 'level', type: 'quantitative', title: 'Level', scale },
          x2: { datum: LEVEL_FLOOR },
          color: {
            field: 'status',
            type: 'nominal',
            title: null,
            scale: {
              domain: ['Below target', 'At target'],
              range: ['#4c78a8', '#54a24b'],
            },
            legend: { orient: 'bottom' },
          },
          tooltip: [
            { field: 'name', title: 'Topic' },
            { field: 'level', title: 'Level' },
            { field: 'status', title: 'Status' },
          ],
        },
      },
      {
        mark: { type: 'rule', strokeDash: [4, 3], color: '#e45756' },
        encoding: { x: { datum: target, type: 'quantitative', scale } },
      },
    ],
  };
};
