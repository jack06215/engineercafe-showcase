import '@emotion/react';
import type { Theme as MuiTheme } from '@mui/material/styles';

// Emotion's theme is MUI's: ThemeProvider passes the MUI theme to both.
declare module '@emotion/react' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface Theme extends MuiTheme {}
}
