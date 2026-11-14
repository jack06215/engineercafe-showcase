import { createFileRoute } from '@tanstack/react-router';

import { librarySearchSchema } from '@/features/library/common/search';
import { LibraryPage } from '@/pages/LibraryPage';

export const Route = createFileRoute('/_shell/library/')({
  validateSearch: librarySearchSchema,
  component: function LibraryRoute() {
    return <LibraryPage search={Route.useSearch()} />;
  },
});
