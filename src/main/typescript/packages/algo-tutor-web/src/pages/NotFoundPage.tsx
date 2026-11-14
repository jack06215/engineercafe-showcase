import Button from '@mui/material/Button';
import { createLink } from '@tanstack/react-router';

import { PagePlaceholder } from '@/components/ui/PagePlaceholder';

const ButtonLink = createLink(Button);

export const NotFoundPage = () => (
  <PagePlaceholder title="Page not found">
    <ButtonLink to="/" variant="outlined" sx={{ mt: 1 }}>
      Go to the desk
    </ButtonLink>
  </PagePlaceholder>
);
