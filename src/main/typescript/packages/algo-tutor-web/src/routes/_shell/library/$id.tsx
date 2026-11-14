import { createFileRoute } from '@tanstack/react-router';

import { ProblemPage } from '@/pages/ProblemPage';

export const Route = createFileRoute('/_shell/library/$id')({
  component: function ProblemPageRoute() {
    const { id } = Route.useParams();
    return <ProblemPage problemId={id} />;
  },
});
