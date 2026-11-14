import { createFileRoute } from '@tanstack/react-router';

import { MistakesPage } from '@/pages/MistakesPage';

export const Route = createFileRoute('/_shell/mistakes')({
  component: MistakesPage,
});
