import React, { useState } from 'react';
import { AppBar, Toolbar, Typography, Container, Box, IconButton, Button, Avatar, Menu, MenuItem } from '@mui/material';
import { Link, useLocation } from 'react-router-dom';
import { BookOpen, Moon, Sun, LogOut, User } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import SignInPromptModal from '../auth/SignInPromptModal';
import GlobalChatbot from '../chat/GlobalChatbot';

const Layout = ({ children, darkMode, onToggleDarkMode }) => {
  const location = useLocation();
  const { user, isAnonymous, login, logout } = useAuth();
  const [anchorEl, setAnchorEl] = useState(null);
  const isCourseMapRoute = location.pathname === '/';

  // Menu Handlers
  const handleMenu = (event) => setAnchorEl(event.currentTarget);
  const handleClose = () => setAnchorEl(null);
  const handleLogout = () => {
    handleClose();
    logout();
  };

  const borderColor = darkMode ? '#555' : '#1A1A1A';
  const cardBg = darkMode ? '#252542' : '#FFFFFF';
  const textColor = darkMode ? '#FFFFFF' : '#1A1A1A';

  return (
    <Box 
      sx={{ 
        minHeight: '100vh', 
        display: 'flex', 
        flexDirection: 'column',
        background: darkMode 
          ? 'linear-gradient(180deg, #1A1A2E 0%, #252542 100%)'
          : 'linear-gradient(180deg, #87CEEB 0%, #E0F7FA 30%, #FFFDF2 60%)', // Sky blue → cream
        transition: 'background 0.3s ease',
      }}
    >
      {/* Neo-Brutalist Navbar */}
      <AppBar 
        position="sticky" 
        elevation={0} 
        sx={{ 
          background: darkMode ? '#252542' : '#FFE66D',
          borderBottom: `3px solid ${borderColor}`,
          boxShadow: `0 4px 0px ${borderColor}`,
          color: textColor,
          borderRadius: 0, // No rounded corners
        }}
      >
          <Toolbar sx={{ py: 0.5, minHeight: { xs: 56, sm: 64 } }}>
            {/* Logo */}
            <Box
              component={Link}
              to="/"
              sx={{
                flexGrow: 1,
                textDecoration: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                '&:hover': { transform: 'translateY(-2px)' },
                transition: 'transform 0.2s ease',
              }}
            >
              <Box
                sx={{
                  width: 40,
                  height: 40,
                  borderRadius: '10px',
                  background: darkMode ? '#4ECDC4' : '#4ECDC4', // Teal/green logo
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: `3px solid ${borderColor}`,
                  boxShadow: `3px 3px 0px ${borderColor}`,
                }}
              >
                <BookOpen size={20} color="#FFFFFF" strokeWidth={2.5} />
              </Box>
              
              <Typography 
                variant="h6" 
                sx={{ 
                  fontWeight: 900,
                  color: textColor,
                  letterSpacing: '-0.02em',
                  fontSize: { xs: '1.1rem', md: '1.4rem' },
                }}
              >
                Spanish
                <Box component="span" sx={{ color: '#4ECDC4' }}>Amigo</Box>
              </Typography>
            </Box>

            {/* Right Side Icons */}
            <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>

              {/* Dark Mode Toggle */}
              <IconButton
                onClick={onToggleDarkMode}
                sx={{
                  background: darkMode ? '#3A3A5C' : '#FFFFFF',
                  border: `2px solid ${borderColor}`,
                  boxShadow: `2px 2px 0px ${borderColor}`,
                  width: 36,
                  height: 36,
                  transition: 'all 0.15s ease',
                  '&:hover': {
                    transform: 'translate(-1px, -1px)',
                    boxShadow: `3px 3px 0px ${borderColor}`,
                  },
                  '&:active': {
                    transform: 'translate(2px, 2px)',
                    boxShadow: `0px 0px 0px ${borderColor}`,
                  },
                }}
              >
                {darkMode ? <Sun size={16} color="#FFE66D" /> : <Moon size={16} color="#1A1A1A" />}
              </IconButton>

              {/* Auth Section */}
              {user && !isAnonymous ? (
                <>
                  <IconButton 
                    onClick={handleMenu} 
                    sx={{ 
                      p: 0, 
                      ml: 0.5,
                      border: `2px solid ${borderColor}`,
                      boxShadow: `2px 2px 0px ${borderColor}`,
                      width: 36,
                      height: 36,
                    }}
                  >
                    <Avatar 
                      alt={user.displayName} 
                      src={user.photoURL}
                      sx={{ width: 32, height: 32 }}
                    />
                  </IconButton>
                  <Menu
                    id="menu-appbar"
                    anchorEl={anchorEl}
                    anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                    keepMounted
                    transformOrigin={{ vertical: 'top', horizontal: 'right' }}
                    open={Boolean(anchorEl)}
                    onClose={handleClose}
                    PaperProps={{
                      sx: {
                        borderRadius: '12px',
                        mt: 1,
                        background: cardBg,
                        border: `3px solid ${borderColor}`,
                        boxShadow: `4px 4px 0px ${borderColor}`,
                        color: textColor,
                      }
                    }}
                  >
                    <MenuItem disabled sx={{ opacity: 0.7, fontSize: '0.85rem' }}>
                      {user.displayName}
                    </MenuItem>
                    <MenuItem onClick={handleLogout} sx={{ gap: 1, fontWeight: 700, color: '#FF6B6B' }}>
                      <LogOut size={16} /> Logout
                    </MenuItem>
                  </Menu>
                </>
              ) : (
                <>
                  {/* Desktop: Full button */}
                  <Button
                    variant="contained"
                    onClick={login}
                    startIcon={<User size={16} />}
                    sx={{
                      display: { xs: 'none', sm: 'flex' },
                      ml: 0.5,
                      borderRadius: '10px',
                      background: '#FF6B6B',
                      color: '#FFFFFF',
                      border: `2px solid ${borderColor}`,
                      boxShadow: `3px 3px 0px ${borderColor}`,
                      fontWeight: 800,
                      px: 2,
                      py: 0.5,
                      fontSize: '0.85rem',
                      '&:hover': {
                        background: '#FF8787',
                        transform: 'translate(-2px, -2px)',
                        boxShadow: `5px 5px 0px ${borderColor}`,
                      },
                      '&:active': {
                        transform: 'translate(3px, 3px)',
                        boxShadow: `0px 0px 0px ${borderColor}`,
                      },
                    }}
                  >
                    Sign In
                  </Button>

                  {/* Mobile: Icon only */}
                  <IconButton
                    onClick={login}
                    sx={{
                      display: { xs: 'flex', sm: 'none' },
                      ml: 0.5,
                      background: '#FF6B6B',
                      border: `2px solid ${borderColor}`,
                      boxShadow: `2px 2px 0px ${borderColor}`,
                      width: 36,
                      height: 36,
                      '&:hover': {
                        background: '#FF8787',
                        transform: 'translate(-1px, -1px)',
                        boxShadow: `3px 3px 0px ${borderColor}`,
                      },
                    }}
                  >
                    <User size={16} color="#FFFFFF" />
                  </IconButton>
                </>
              )}

            </Box>
          </Toolbar>
        </AppBar>

      {/* Main Content */}
      <Container 
        maxWidth={isCourseMapRoute ? false : 'sm'}
        sx={{ 
          flexGrow: 1, 
          py: { xs: 3, md: 4 },
          px: { xs: 2, sm: 3 },
          position: 'relative',
          zIndex: 1,
          ...(isCourseMapRoute && {
            width: '100%',
            maxWidth: {
              xs: '100%',
              sm: '760px',
              md: '1120px',
              lg: '1320px',
              xl: '1400px',
            },
          }),
        }}
      >
        <Box
          sx={{
            background: isCourseMapRoute ? 'transparent' : cardBg,
            borderRadius: isCourseMapRoute ? 0 : '16px',
            padding: isCourseMapRoute ? 0 : { xs: 2.5, md: 3.5 },
            border: isCourseMapRoute ? 'none' : `3px solid ${borderColor}`,
            boxShadow: isCourseMapRoute ? 'none' : `6px 6px 0px ${borderColor}`,
            position: 'relative',
            transition: 'all 0.3s ease',
          }}
        >
          {children}
        </Box>
      </Container>

      {/* Footer */}
      <Box 
        sx={{ 
          py: 2.5,
          textAlign: 'center',
          background: darkMode ? '#2D2D50' : '#4ECDC4',
          borderTop: `3px solid ${borderColor}`,
          color: darkMode ? '#FFFFFF' : '#1A1A1A',
        }}
      >
        <Typography 
          variant="body2" 
          sx={{ 
            fontWeight: 800,
            fontSize: { xs: '0.85rem', md: '0.95rem' },
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 1,
          }}
        >
          <span>☀️</span>
          Un poquito cada día — A little bit every day
          <span>🌻</span>
        </Typography>
      </Box>

      {/* Global AI Chatbot */}
      <GlobalChatbot darkMode={darkMode} onToggleTheme={onToggleDarkMode} />
      <SignInPromptModal />
    </Box>
  );
};

export default Layout;
