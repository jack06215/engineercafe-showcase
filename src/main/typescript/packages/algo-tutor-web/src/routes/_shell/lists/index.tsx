import { createFileRoute } from '@tanstack/react-router';

import { ListsPage } from '@/pages/ListsPage';

export const Route = createFileRoute('/_shell/lists/')({
  component: ListsPage,
});
