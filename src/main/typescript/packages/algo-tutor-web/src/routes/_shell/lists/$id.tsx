import { createFileRoute } from '@tanstack/react-router';

import { ListPage } from '@/pages/ListPage';

export const Route = createFileRoute('/_shell/lists/$id')({
  component: function ListPageRoute() {
    const { id } = Route.useParams();
    return <ListPage listId={id} />;
  },
});
