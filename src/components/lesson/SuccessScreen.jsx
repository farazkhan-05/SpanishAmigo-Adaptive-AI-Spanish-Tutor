import React, { useEffect, useState } from 'react';
import { Box, Typography, Button, Container, Chip, LinearProgress } from '@mui/material';
import Confetti from 'react-confetti';
import { Trophy, Zap, Home, Award, TrendingUp } from 'lucide-react';

const SuccessScreen = ({ onBackToMap }) => {
  const [windowSize, setWindowSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });
  const [xpCount, setXpCount] = useState(0);
  const [showStats, setShowStats] = useState(false);

  const targetXP = 100;

  // Handle window resize for confetti
  useEffect(() => {
    const handleResize = () => {
      setWindowSize({ width: window.innerWidth, height: window.innerHeight });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Animate XP counter
  useEffect(() => {
    const duration = 1500;
    const steps = 40;
    const increment = targetXP / steps;
    let current = 0;

    const timer = setInterval(() => {
      current += increment;
      if (current >= targetXP) {
        setXpCount(targetXP);
        clearInterval(timer);
        setShowStats(true);
      } else {
        setXpCount(Math.floor(current));
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, []);

  return (
    <Box
      sx={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: '#FFE66D',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        overflow: 'hidden',
      }}
    >
      {/* Confetti */}
      <Confetti
        width={windowSize.width}
        height={windowSize.height}
        recycle={false}
        numberOfPieces={400}
        gravity={0.2}
        colors={['#FF6B6B', '#4ECDC4', '#A78BFA', '#1A1A1A', '#FFFFFF']}
      />

      <Container maxWidth="sm">
        {/* Trophy */}
        <Box
          sx={{
            mb: 3,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Box
            sx={{
              width: 100,
              height: 100,
              borderRadius: '20px',
              background: '#4ECDC4',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '4px solid #1A1A1A',
              boxShadow: '6px 6px 0px #1A1A1A',
            }}
          >
            <Trophy size={50} color="#1A1A1A" strokeWidth={2.5} />
          </Box>
        </Box>

        {/* Title */}
        <Typography
          variant="h3"
          sx={{
            fontWeight: 900,
            mb: 1,
            color: '#1A1A1A',
            fontSize: { xs: '1.8rem', md: '2.5rem' },
          }}
        >
          Leccion Completada!
        </Typography>

        <Typography
          variant="body1"
          sx={{
            mb: 3,
            color: '#1A1A1A',
            fontWeight: 700,
            fontSize: { xs: '1rem', md: '1.15rem' },
            opacity: 0.8,
          }}
        >
          You are one step closer to fluency!
        </Typography>

        {/* XP Card */}
        <Box
          sx={{
            bgcolor: 'background.paper',
            borderRadius: '16px',
            p: 3,
            mb: 3,
            border: '3px solid',
            borderColor: 'divider',
            boxShadow: (theme) => `6px 6px 0px ${theme.palette.divider}`,
          }}
        >
          {/* XP Badge */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
            <Box
              sx={{
                width: 56,
                height: 56,
                borderRadius: '14px',
                background: '#A78BFA',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '3px solid #1A1A1A',
                boxShadow: '3px 3px 0px #1A1A1A',
              }}
            >
              <Zap size={28} color="#FFFFFF" fill="#FFFFFF" />
            </Box>
          </Box>

          <Typography
            variant="h3"
            sx={{
              fontWeight: 900,
              color: '#FF6B6B',
              mb: 0.5,
              fontSize: { xs: '2rem', md: '2.5rem' },
            }}
          >
            +{xpCount} XP
          </Typography>

          <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 700, mb: 2, opacity: 0.8 }}>
            Experience Points Earned
          </Typography>

          {/* Progress Bar */}
          <LinearProgress
            variant="determinate"
            value={(xpCount / targetXP) * 100}
            sx={{
              height: 10,
              borderRadius: '6px',
              border: '2px solid #1A1A1A',
              background: '#F0F0F0',
              '& .MuiLinearProgress-bar': {
                background: '#4ECDC4',
                borderRadius: '4px',
              },
            }}
          />
        </Box>

        {/* Achievement Badges */}
        {showStats && (
          <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center', mb: 3, flexWrap: 'wrap' }}>
            <Chip
              icon={<Award size={14} />}
              label="Lesson Master"
              sx={{
                background: '#4ECDC4',
                border: '2px solid #1A1A1A',
                boxShadow: '2px 2px 0px #1A1A1A',
                color: '#1A1A1A',
                fontWeight: 800,
                fontSize: '0.75rem',
              }}
            />
            <Chip
              icon={<TrendingUp size={14} />}
              label="Progress Unlocked"
              sx={{
                background: '#A78BFA',
                border: '2px solid #1A1A1A',
                boxShadow: '2px 2px 0px #1A1A1A',
                color: '#FFFFFF',
                fontWeight: 800,
                fontSize: '0.75rem',
              }}
            />
          </Box>
        )}

        {/* Back Button */}
        <Button
          variant="contained"
          size="large"
          onClick={onBackToMap}
          sx={{
            px: 4,
            py: 1.5,
            fontSize: '1rem',
            fontWeight: 800,
            borderRadius: '14px',
            background: '#FFFFFF',
            color: '#1A1A1A',
            border: '3px solid #1A1A1A',
            boxShadow: '5px 5px 0px #1A1A1A',
            textTransform: 'uppercase',
            transition: 'all 0.15s ease',
            '&:hover': {
              background: '#F0F0F0',
              transform: 'translate(-2px, -2px)',
              boxShadow: '7px 7px 0px #1A1A1A',
            },
            '&:active': {
              transform: 'translate(5px, 5px)',
              boxShadow: '0px 0px 0px #1A1A1A',
            },
          }}
        >
          <Home size={20} style={{ marginRight: 8 }} />
          Back to Journey Map
        </Button>
      </Container>
    </Box>
  );
};

export default SuccessScreen;