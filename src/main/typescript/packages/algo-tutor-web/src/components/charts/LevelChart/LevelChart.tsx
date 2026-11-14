import { useMemo } from 'react';

import { VegaLiteChart } from '../VegaLiteChart';

import { levelChartSpec, type TopicLevel } from './levelChartSpec';

type Props = {
  levels: readonly TopicLevel[];
  target: number;
  onTopicClick?: (topicId: string) => void;
};

// The training levels against the target (SPEC §14 Topics): a bar per topic
// from 1000 to its level, and the target as a dashed rule.
export const LevelChart = ({ levels, target, onTopicClick }: Props) => {
  const spec = useMemo(() => levelChartSpec(levels, target), [levels, target]);
  return (
    <VegaLiteChart
      spec={spec}
      onDatumClick={(datum) => {
        if (typeof datum.topicId === 'string') onTopicClick?.(datum.topicId);
      }}
    />
  );
};
