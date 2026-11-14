import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  COLOR_SCHEME_STORAGE_KEY,
  theme,
  THEME_MODE_STORAGE_KEY,
} from '@/common/theme';

const defaultQueryClient = new QueryClient();

type Props = {
  children: React.ReactNode;
  // Tests pass their own, so cached results don't leak between them.
  queryClient?: QueryClient;
};

// Everything the app needs above the router: the MUI/Emotion theme (light,
// dark or the OS's, remembered per browser), the baseline styles and the
// TanStack Query cache. Storybook wraps every story in it too.
export const AppProviders: React.FC<Props> = ({
  children,
  queryClient = defaultQueryClient,
}) => {
  return (
    <ThemeProvider
      theme={theme}
      defaultMode="system"
      modeStorageKey={THEME_MODE_STORAGE_KEY}
      colorSchemeStorageKey={COLOR_SCHEME_STORAGE_KEY}
      disableTransitionOnChange
    >
      <CssBaseline enableColorScheme />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
};
