import MenuIcon from '@mui/icons-material/Menu';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';
import { useState } from 'react';

import { ThemeModeSwitch } from '../ThemeModeSwitch';

import { NAVIGATION } from './navigation';

const DRAWER_WIDTH = 220;

// A router link that looks like a sidebar row and is "selected" on its page.
const NavLink = createLink(ListItemButton);

const Sidebar = ({ onNavigate }: { onNavigate?: () => void }) => (
  <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
    <Toolbar>
      <Typography variant="h6" component="div" noWrap>
        algo_tutor
      </Typography>
    </Toolbar>
    <Divider />
    <Box component="nav" aria-label="Main" sx={{ flexGrow: 1 }}>
      <List>
        {NAVIGATION.map(({ to, label, icon, exact }) => (
          <NavLink
            key={to}
            to={to}
            activeOptions={{ exact }}
            activeProps={{ selected: true, 'aria-current': 'page' }}
            onClick={onNavigate}
          >
            <ListItemIcon>{icon}</ListItemIcon>
            <ListItemText primary={label} />
          </NavLink>
        ))}
      </List>
    </Box>
    <Divider />
    <Box sx={{ p: 2 }}>
      <ThemeModeSwitch />
    </Box>
  </Box>
);

type Props = {
  children: React.ReactNode;
};

// Every page but the attempt page (SPEC §14): the sidebar, permanent on
// wide screens and behind a menu button on narrow ones, and the page.
export const AppShell = ({ children }: Props) => {
  const [open, setOpen] = useState(false);

  return (
    <Box sx={{ display: 'flex', minHeight: '100%' }}>
      <AppBar
        position="fixed"
        color="default"
        elevation={0}
        sx={{ display: { md: 'none' } }}
      >
        <Toolbar>
          <IconButton
            edge="start"
            aria-label="Open navigation"
            onClick={() => setOpen(true)}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" component="div" noWrap>
            algo_tutor
          </Typography>
        </Toolbar>
      </AppBar>
      <Drawer
        variant="temporary"
        open={open}
        onClose={() => setOpen(false)}
        sx={{
          display: { xs: 'block', md: 'none' },
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH },
        }}
      >
        <Sidebar onNavigate={() => setOpen(false)} />
      </Drawer>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', md: 'block' },
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
          },
        }}
        open
      >
        <Sidebar />
      </Drawer>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          minWidth: 0,
          p: { xs: 2, md: 3 },
          pt: { xs: 9, md: 3 },
        }}
      >
        {children}
      </Box>
    </Box>
  );
};
