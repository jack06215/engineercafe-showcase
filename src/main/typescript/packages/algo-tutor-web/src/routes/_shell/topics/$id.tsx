import { createFileRoute } from '@tanstack/react-router';

import { TopicPage } from '@/pages/TopicPage';

export const Route = createFileRoute('/_shell/topics/$id')({
  component: function TopicPageRoute() {
    const { id } = Route.useParams();
    return <TopicPage topicId={id} />;
  },
});
