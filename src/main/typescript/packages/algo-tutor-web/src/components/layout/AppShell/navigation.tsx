import AutoStoriesIcon from '@mui/icons-material/AutoStories';
import ExtensionIcon from '@mui/icons-material/Extension';
import FormatListNumberedIcon from '@mui/icons-material/FormatListNumbered';
import ReportOutlinedIcon from '@mui/icons-material/ReportOutlined';
import SettingsIcon from '@mui/icons-material/Settings';
import StackedBarChartIcon from '@mui/icons-material/StackedBarChart';
import TodayIcon from '@mui/icons-material/Today';

// The sidebar, in SPEC §14's order.
export const NAVIGATION = [
  { to: '/', label: 'Desk', icon: <TodayIcon />, exact: true },
  { to: '/library', label: 'Library', icon: <AutoStoriesIcon />, exact: false },
  {
    to: '/lists',
    label: 'Lists',
    icon: <FormatListNumberedIcon />,
    exact: false,
  },
  {
    to: '/topics',
    label: 'Topics',
    icon: <StackedBarChartIcon />,
    exact: false,
  },
  { to: '/patterns', label: 'Patterns', icon: <ExtensionIcon />, exact: false },
  {
    to: '/mistakes',
    label: 'Mistakes',
    icon: <ReportOutlinedIcon />,
    exact: false,
  },
  { to: '/settings', label: 'Settings', icon: <SettingsIcon />, exact: false },
] as const;
