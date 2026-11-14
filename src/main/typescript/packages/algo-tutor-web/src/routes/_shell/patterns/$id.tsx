import { createFileRoute } from '@tanstack/react-router';

import { PatternPage } from '@/pages/PatternPage';

export const Route = createFileRoute('/_shell/patterns/$id')({
  component: function PatternPageRoute() {
    const { id } = Route.useParams();
    return <PatternPage patternId={id} />;
  },
});
