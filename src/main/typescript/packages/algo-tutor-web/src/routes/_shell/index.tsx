import { createFileRoute } from '@tanstack/react-router';

import { DeskPage } from '@/pages/DeskPage';

export const Route = createFileRoute('/_shell/')({
  component: DeskPage,
});
