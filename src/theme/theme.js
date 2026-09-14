import { createTheme } from '@mui/material/styles';

const shadowColorLight = '#1A1A1A';
const shadowColorDark = '#000000';

export const createAppTheme = (mode = 'light') => {
  const isDark = mode === 'dark';
  const shadowColor = isDark ? shadowColorDark : shadowColorLight;
  const borderColor = isDark ? '#333333' : '#1A1A1A'; // slightly lighter border in dark mode
  const brandColors = {
    coral: '#FF6B6B',
    teal: '#4ECDC4',
    yellow: '#FFE66D',
    purple: '#A78BFA',
  };

  return createTheme({
    palette: {
      mode,
      primary: {
        main: '#FF6B6B', // Coral Pink
        contrastText: '#FFFFFF',
      },
      secondary: {
        main: '#4ECDC4', // Mint Green
        contrastText: '#1A1A1A',
      },
      accent: {
        main: '#FFE66D', // Sunny Yellow
        contrastText: '#1A1A1A',
      },
      success: {
        main: '#00D9A3',
      },
      background: {
        default: isDark ? '#1A1A2E' : '#FFFDF2',
        paper: isDark ? '#252542' : '#FFFFFF',
        gradient: isDark ? '#1A1A2E' : '#FFFDF2',
        gradientLight: isDark ? '#252542' : '#FFFFFF',
        mesh: 'none',
      },
      text: {
        primary: isDark ? '#F0F0F0' : '#1A1A1A',
        secondary: isDark ? '#B0B3C1' : '#4A5568',
      },
      divider: isDark ? '#444' : '#1A1A1A',
    },
    typography: {
      fontFamily: '"Nunito", "Quicksand", sans-serif',
      h1: { fontWeight: 900, fontSize: 'clamp(2.5rem, 5vw, 4rem)', letterSpacing: '-0.02em', color: isDark ? '#FFFFFF' : '#1A1A1A' },
      h2: { fontWeight: 800, fontSize: 'clamp(2rem, 4vw, 3rem)', letterSpacing: '-0.01em' },
      h3: { fontWeight: 800, fontSize: 'clamp(1.5rem, 3vw, 2.25rem)' },
      h4: { fontWeight: 800, fontSize: 'clamp(1.25rem, 2.5vw, 1.75rem)' },
      h5: { fontWeight: 800, fontSize: 'clamp(1rem, 2vw, 1.5rem)' },
      h6: { fontWeight: 800, fontSize: 'clamp(0.875rem, 1.5vw, 1.25rem)' },
      button: { textTransform: 'none', fontWeight: 800, letterSpacing: '0.02em', fontSize: '1rem' },
      body1: { fontSize: '1rem', lineHeight: 1.7, fontWeight: 700 },
      body2: { fontSize: '0.875rem', lineHeight: 1.6, fontWeight: 700 },
    },
    shape: {
      borderRadius: 12,
    },
    spanishAmigo: {
      colors: brandColors,
      outline: {
        color: isDark ? '#686879' : borderColor,
        width: 3,
      },
      shadows: {
        card: `6px 6px 0px ${shadowColor}`,
        control: `3px 3px 0px ${shadowColor}`,
      },
      radii: {
        control: 10,
        surface: 16,
      },
      surfaces: {
        canvas: isDark ? '#1A1A2E' : '#FFFDF2',
        raised: isDark ? '#252542' : '#FFFFFF',
      },
    },
    shadows: [
      'none',
      `4px 4px 0px ${shadowColor}`, // Elevation 1 used everywhere now
      ...Array(23).fill(`4px 4px 0px ${shadowColor}`),
    ],
    components: {
      MuiButton: {
        styleOverrides: {
          root: {
            padding: '12px 28px',
            fontSize: '1rem',
            borderRadius: '12px',
            fontWeight: 800,
            border: `3px solid ${borderColor}`,
            boxShadow: `4px 4px 0px ${shadowColor}`,
            transition: 'all 0.15s ease',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: isDark ? '#FFFFFF' : '#1A1A1A',
            '&:hover': {
              transform: 'translate(-2px, -2px)',
              boxShadow: `6px 6px 0px ${shadowColor}`,
            },
            '&:active': {
              transform: 'translate(4px, 4px)',
              boxShadow: `0px 0px 0px ${shadowColor}`,
            },
          },
          contained: {
            background: isDark ? '#FF6B6B' : '#FFE66D',
            color: '#1A1A1A',
            '&:hover': {
              background: isDark ? '#FF8787' : '#FFF099',
            },
          },
          outlined: {
            background: isDark ? '#252542' : '#FFFFFF',
            borderWidth: '3px',
            '&:hover': {
              borderWidth: '3px',
              background: isDark ? '#3A3A3A' : '#F0F0F0',
            },
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: '16px',
            boxShadow: `6px 6px 0px ${shadowColor}`,
            border: `3px solid ${borderColor}`,
            background: isDark ? '#252542' : '#FFFFFF',
            transition: 'all 0.2s ease',
            '&:hover': {
              transform: 'translate(-4px, -4px)',
              boxShadow: `10px 10px 0px ${shadowColor}`,
            },
            '&::before': {
              display: 'none', // Remove the tiny top gradient bar from old theme
            }
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: '8px',
            fontWeight: 800,
            fontSize: '0.875rem',
            padding: '4px',
            border: `2px solid ${borderColor}`,
            boxShadow: `2px 2px 0px ${shadowColor}`,
          },
          filled: {
            background: '#4ECDC4',
            color: '#1A1A1A',
          },
        },
      },
      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: '12px',
              background: isDark ? '#1A1A2E' : '#FFFFFF',
              transition: 'all 0.2s ease',
              boxShadow: `4px 4px 0px ${shadowColor}`,
              '& fieldset': {
                border: `3px solid ${borderColor}`,
              },
              '&:hover fieldset': {
                border: `3px solid ${borderColor}`,
              },
              '&.Mui-focused': {
                transform: 'translate(-2px, -2px)',
                boxShadow: `6px 6px 0px ${shadowColor}`,
              },
              '&.Mui-focused fieldset': {
                border: `3px solid ${borderColor}`,
              },
            },
          },
        },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            borderRadius: '8px',
            height: '16px',
            border: `2px solid ${borderColor}`,
            background: isDark ? '#1A1A1A' : '#FFFFFF',
          },
          bar: {
            borderRadius: '0px',
            background: '#FF6B6B',
            borderRight: `2px solid ${borderColor}`,
          },
        },
      },
    },
    breakpoints: {
      values: { xs: 0, sm: 600, md: 900, lg: 1200, xl: 1536 },
    },
  });
};

export const customStyles = {
  gradientText: (mode = 'light') => ({
    color: mode === 'dark' ? '#FFE66D' : '#FF6B6B', // Flattened out
    textShadow: `3px 3px 0px ${mode === 'dark' ? '#000000' : '#1A1A1A'}`,
  }),
  glassCard: (mode = 'light') => ({
    background: mode === 'dark' ? '#252542' : '#FFFFFF',
    border: `3px solid ${mode === 'dark' ? '#333333' : '#1A1A1A'}`,
    boxShadow: `8px 8px 0px ${mode === 'dark' ? '#000000' : '#1A1A1A'}`,
    borderRadius: '16px',
  }),
  floatingAnimation: {
    animation: 'bounceHover 2s infinite',
    '@keyframes bounceHover': {
      '0%, 100%': { transform: 'translateY(0px)' },
      '50%': { transform: 'translateY(-10px)' },
    },
  },
};
