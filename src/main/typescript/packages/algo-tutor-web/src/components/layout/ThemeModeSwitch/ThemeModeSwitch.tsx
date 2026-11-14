import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import SettingsBrightnessIcon from '@mui/icons-material/SettingsBrightness';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import { useColorScheme } from '@mui/material/styles';

type Mode = 'system' | 'light' | 'dark';

const MODES: { mode: Mode; label: string; icon: React.ReactNode }[] = [
  {
    mode: 'system',
    label: 'Follow the system',
    icon: <SettingsBrightnessIcon />,
  },
  { mode: 'light', label: 'Light', icon: <LightModeIcon /> },
  { mode: 'dark', label: 'Dark', icon: <DarkModeIcon /> },
];

// The sidebar's light/dark switch (SPEC §13 Theme): system, light or dark,
// remembered per browser by the ThemeProvider (common/providers.tsx).
export const ThemeModeSwitch = () => {
  const { mode, setMode } = useColorScheme();
  return (
    <ToggleButtonGroup
      size="small"
      exclusive
      aria-label="Theme"
      value={mode ?? 'system'}
      onChange={(_event, next: Mode | null) => {
        if (next) setMode(next);
      }}
    >
      {MODES.map(({ mode: value, label, icon }) => (
        <Tooltip key={value} title={label}>
          <ToggleButton value={value} aria-label={label}>
            {icon}
          </ToggleButton>
        </Tooltip>
      ))}
    </ToggleButtonGroup>
  );
};
