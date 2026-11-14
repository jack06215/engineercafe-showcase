import { createFileRoute } from '@tanstack/react-router';

import { TopicsPage } from '@/pages/TopicsPage';

export const Route = createFileRoute('/_shell/topics/')({
  component: TopicsPage,
});
