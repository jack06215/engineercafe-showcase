import { createTheme } from '@mui/material/styles';

// Where the theme switch keeps the viewer's choice (system / light / dark),
// per browser (SPEC §13). MUI's storage manager wraps every localStorage call
// in try/catch, so a private window or blocked storage falls back to the OS.
export const THEME_MODE_STORAGE_KEY = 'algo-tutor.theme-mode';
export const COLOR_SCHEME_STORAGE_KEY = 'algo-tutor.color-scheme';

// The app's MUI theme, light and dark. MUI's ThemeProvider (see
// providers.tsx) also hands it to Emotion, so css-prop and styled() callbacks
// get the same object, typed in src/emotion.d.ts. With CSS variables the
// light/dark switch is a class on <html>, not a re-render of every component.
export const theme = createTheme({
  cssVariables: { colorSchemeSelector: 'class' },
  colorSchemes: { light: true, dark: true },
  typography: {
    fontFamily: [
      '"Helvetica Neue"',
      'Arial',
      '"Hiragino Kaku Gothic ProN"',
      '"Hiragino Sans"',
      'Meiryo',
      'sans-serif',
    ].join(','),
  },
});
