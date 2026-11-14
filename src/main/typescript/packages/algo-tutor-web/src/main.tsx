import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from '@/App';
import { createAppRouter } from '@/common/router';

import '@/styles/global.scss';
import '@/styles/application.scss';

const router = createAppRouter();

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App router={router} />
  </StrictMode>,
);
