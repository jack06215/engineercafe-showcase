import { createFileRoute } from '@tanstack/react-router';

import { AttemptPage } from '@/pages/AttemptPage';

// Full-window: outside the `_shell` layout, so no sidebar (SPEC §14).
export const Route = createFileRoute('/attempts/$id')({
  component: function AttemptRoute() {
    const { id } = Route.useParams();
    return <AttemptPage attemptId={id} />;
  },
});
