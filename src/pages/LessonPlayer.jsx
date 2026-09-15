import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Navigate } from 'react-router-dom';
import { Box, Container, IconButton, LinearProgress, Typography, Chip } from '@mui/material';
import { X, Award, Zap, Heart, Target, TrendingUp } from 'lucide-react';

import { courseData } from '../data/curriculum';
import { useProgress } from '../context/ProgressContext';
import { useLessonNavigation } from '../hooks/useLessonNavigation';

import ContextSlide from '../components/lesson/ContextSlide';
import RevealSlide from '../components/lesson/RevealSlide';
import QuizSlide from '../components/lesson/QuizSlide';
import SuccessScreen from '../components/lesson/SuccessScreen';

const LessonPlayer = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { markLessonComplete, completedLessons } = useProgress();

  const [isCompleted, setIsCompleted] = useState(false);
  const [slideTransition, setSlideTransition] = useState(false);
  const [streak, setStreak] = useState(0);
  const completionTimerRef = useRef(null);

  const lessonId = parseInt(id);
  const lesson = courseData.find((l) => l.id === lessonId);

  useEffect(() => {
    setStreak(completedLessons.length);
  }, [completedLessons]);

  const handleLessonFinish = () => {
    markLessonComplete(lessonId);
    if (completionTimerRef.current) clearTimeout(completionTimerRef.current);
    const timer = setTimeout(() => {
      setIsCompleted(true);
      completionTimerRef.current = null;
    }, 300);
    completionTimerRef.current = timer;
  };

  useEffect(() => {
    return () => {
      if (completionTimerRef.current) clearTimeout(completionTimerRef.current);
    };
  }, []);

  const {
    currentSlide,
    progress,
    nextSlide
  } = useLessonNavigation(lesson, handleLessonFinish);

  useEffect(() => {
    setSlideTransition(true);
    const timer = setTimeout(() => setSlideTransition(false), 150);
    return () => clearTimeout(timer);
  }, [currentSlide]);

  if (!lesson) return <Navigate to="/" />;

  if (isCompleted) {
    return <SuccessScreen onBackToMap={() => navigate('/')} />;
  }

  const renderSlide = () => {
    if (!currentSlide) return null;
    switch (currentSlide.type) {
      case 'context': return <ContextSlide data={currentSlide} onNext={nextSlide} />;
      case 'reveal': return <RevealSlide data={currentSlide} onNext={nextSlide} />;
      case 'practice': return <QuizSlide key={`${currentSlide.type}:${currentSlide.question}`} data={currentSlide} onNext={nextSlide} />;
      default: return null;
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Top Navigation Bar */}
      <Box
        sx={{
          p: 1.5,
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          background: '#FFE66D',
          borderBottom: '3px solid #1A1A1A',
          boxShadow: '0 3px 0px #1A1A1A',
        }}
      >
        {/* Close Button */}
        <IconButton
          onClick={() => navigate('/')}
          sx={{
            background: '#FFFFFF',
            border: '2px solid #1A1A1A',
            boxShadow: '2px 2px 0px #1A1A1A',
            width: 36,
            height: 36,
            transition: 'all 0.15s ease',
            '&:hover': {
              background: '#FF6B6B',
              color: '#FFFFFF',
              transform: 'translate(-1px, -1px)',
              boxShadow: '3px 3px 0px #1A1A1A',
            },
            '&:active': {
              transform: 'translate(2px, 2px)',
              boxShadow: '0px 0px 0px #1A1A1A',
            },
          }}
        >
          <X size={18} color="#1A1A1A" />
        </IconButton>

        {/* Progress Bar */}
        <Box sx={{ flexGrow: 1, position: 'relative' }}>
          <LinearProgress
            variant="determinate"
            value={progress}
          />
          <Typography
            variant="caption"
            sx={{
              position: 'absolute',
              right: 8,
              top: '50%',
              transform: 'translateY(-50%)',
              color: (theme) => theme.palette.mode === 'dark' ? '#FFFFFF' : '#1A1A1A',
              fontWeight: 900,
              fontSize: '0.65rem',
            }}
          >
            {Math.round(progress)}%
          </Typography>
        </Box>

        {/* Lesson Title */}
        <Chip
          label={lesson.title}
          size="small"
          sx={{
            background: '#FFFFFF',
            border: '2px solid #1A1A1A',
            boxShadow: '2px 2px 0px #1A1A1A',
            color: '#1A1A1A',
            fontWeight: 800,
            fontSize: '0.72rem',
            display: { xs: 'none', sm: 'flex' },
          }}
        />

        {/* Streak */}
        {streak > 0 && (
          <Chip
            label={`${streak} 🔥`}
            size="small"
            sx={{
              background: '#FF6B6B',
              color: '#FFFFFF',
              fontWeight: 900,
              fontSize: '0.75rem',
              border: '2px solid #1A1A1A',
              boxShadow: '2px 2px 0px #1A1A1A',
            }}
          />
        )}
      </Box>

      {/* Main Content */}
      <Container
        maxWidth="sm"
        sx={{
          flexGrow: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          py: { xs: 2, md: 3 },
          px: { xs: 2, sm: 3 },
        }}
      >
        {/* Slide Card */}
        <Box
          sx={{
            width: '100%',
            bgcolor: 'background.paper',
            borderRadius: '16px',
            border: '3px solid',
            borderColor: 'divider',
            boxShadow: (theme) => `6px 6px 0px ${theme.palette.divider}`,
            p: { xs: 2.5, sm: 3, md: 3.5 },
            minHeight: { xs: 300, md: 380 },
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            opacity: slideTransition ? 0.6 : 1,
            transform: slideTransition ? 'scale(0.98)' : 'scale(1)',
            transition: 'all 0.15s ease',
          }}
        >
          <Box
            sx={{
              opacity: slideTransition ? 0 : 1,
              transform: slideTransition ? 'translateX(-5px)' : 'translateX(0)',
              transition: 'all 0.15s ease',
            }}
          >
            {renderSlide()}
          </Box>
        </Box>
      </Container>

      {/* Bottom Bar */}
      <Box
        sx={{
          p: 1.5,
          textAlign: 'center',
          background: '#4ECDC4',
          borderTop: '3px solid #1A1A1A',
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1 }}>
          <Chip
            icon={<Heart size={12} />}
            label="¡Muy bien!"
            size="small"
            sx={{
              background: '#FF6B6B',
              color: '#FFFFFF',
              fontWeight: 800,
              border: '2px solid #1A1A1A',
              fontSize: '0.7rem',
            }}
          />
          <Chip
            icon={<TrendingUp size={12} />}
            label="Keep going!"
            size="small"
            sx={{
              background: '#FFE66D',
              color: '#1A1A1A',
              fontWeight: 800,
              border: '2px solid #1A1A1A',
              fontSize: '0.7rem',
            }}
          />
          <Chip
            icon={<Award size={12} />}
            label="You got this!"
            size="small"
            sx={{
              background: '#A78BFA',
              color: '#FFFFFF',
              fontWeight: 800,
              border: '2px solid #1A1A1A',
              fontSize: '0.7rem',
              display: { xs: 'none', sm: 'flex' },
            }}
          />
        </Box>
      </Box>
    </Box>
  );
};

export default LessonPlayer;
