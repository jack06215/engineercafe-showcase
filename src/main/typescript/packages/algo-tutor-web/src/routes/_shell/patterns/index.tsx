import { createFileRoute } from '@tanstack/react-router';

import { PatternsPage } from '@/pages/PatternsPage';

export const Route = createFileRoute('/_shell/patterns/')({
  component: PatternsPage,
});
