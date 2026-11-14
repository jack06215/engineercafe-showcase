import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

type Props = {
  title: string;
  // What the screen will hold (SPEC §14).
  children?: React.ReactNode;
};

// A screen's heading and a line about it, until the screen is built.
export const PagePlaceholder = ({ title, children }: Props) => (
  <Stack spacing={1}>
    <Typography variant="h4" component="h1">
      {title}
    </Typography>
    {children && (
      <Typography color="text.secondary" component="div">
        {children}
      </Typography>
    )}
  </Stack>
);
