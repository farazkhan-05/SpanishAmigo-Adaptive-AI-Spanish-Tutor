import React from 'react';
import { Box, Button, Typography } from '@mui/material';
import { ArrowRight, CheckCircle2, Compass, Flag, Layers3 } from 'lucide-react';

const supportCardSx = {
  border: (theme) => `3px solid ${theme.spanishAmigo.outline.color}`,
  borderRadius: '16px',
  boxShadow: (theme) => theme.spanishAmigo.shadows.card,
  p: { xs: 2, sm: 2.25 },
};

export const ContinueLearningPanel = ({ lesson, isComplete, onContinue }) => (
  <Box
    component="aside"
    aria-labelledby="continue-title"
    sx={{
      ...supportCardSx,
      backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#2E4050' : '#DDF9F6',
      transform: { lg: 'rotate(-1deg)' },
      '@media (prefers-reduced-motion: reduce)': { transform: 'none' },
    }}
  >
    <Box sx={{ width: 42, height: 42, display: 'grid', placeItems: 'center', borderRadius: '11px', backgroundColor: (theme) => theme.spanishAmigo.colors.teal, color: '#1A1A1A', border: '2px solid #1A1A1A', mb: 1.5 }}>
      {isComplete ? <CheckCircle2 size={22} aria-hidden="true" /> : <Compass size={22} aria-hidden="true" />}
    </Box>
    <Typography id="continue-title" sx={{ fontWeight: 900, fontSize: '1.05rem', lineHeight: 1.2 }}>
      {isComplete ? 'Journey complete' : 'Continue learning'}
    </Typography>
    {isComplete ? (
      <Typography sx={{ mt: 1, color: 'text.secondary', fontSize: '0.84rem', fontWeight: 700 }}>
        Every lesson in this course is complete. ¡Excelente trabajo!
      </Typography>
    ) : (
      <>
        <Typography sx={{ mt: 1, color: 'text.secondary', fontSize: '0.72rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '.08em' }}>
          Lesson {lesson?.number}
        </Typography>
        <Typography sx={{ mt: 0.35, fontWeight: 900, fontSize: '0.94rem', lineHeight: 1.35, overflowWrap: 'anywhere' }}>
          {lesson?.title}
        </Typography>
        <Button
          fullWidth
          variant="contained"
          onClick={onContinue}
          endIcon={<ArrowRight size={17} />}
          sx={{ mt: 2, minHeight: 44, py: 1, px: 1.5, backgroundColor: (theme) => theme.spanishAmigo.colors.coral, color: '#fff', fontSize: '0.78rem', '&:hover': { backgroundColor: '#FF8585' }, '&.Mui-focusVisible': { outline: '4px solid #A78BFA', outlineOffset: '3px' } }}
        >
          Continue
        </Button>
      </>
    )}
  </Box>
);

export const CourseSummaryPanel = ({ completedCount, remainingCount, totalCount }) => (
  <Box
    component="aside"
    aria-labelledby="summary-title"
    sx={{
      ...supportCardSx,
      backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#3A334D' : '#F0EAFE',
      transform: { lg: 'rotate(1deg)' },
      '@media (prefers-reduced-motion: reduce)': { transform: 'none' },
    }}
  >
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
      <Box sx={{ width: 38, height: 38, display: 'grid', placeItems: 'center', borderRadius: '10px', backgroundColor: (theme) => theme.spanishAmigo.colors.purple, color: '#1A1A1A', border: '2px solid #1A1A1A' }}>
        <Layers3 size={20} aria-hidden="true" />
      </Box>
      <Typography id="summary-title" sx={{ fontWeight: 900, fontSize: '1rem' }}>Course at a glance</Typography>
    </Box>
    <Box component="dl" sx={{ m: 0, display: 'grid', gap: 1.25 }}>
      {[
        { label: 'Lessons completed', value: completedCount, icon: <CheckCircle2 size={14} aria-hidden="true" />, color: '#4ECDC4' },
        { label: 'Lessons remaining', value: remainingCount, icon: <Flag size={14} aria-hidden="true" />, color: '#FFE66D' },
        { label: 'Total lessons', value: totalCount, icon: <Layers3 size={14} aria-hidden="true" />, color: '#FF6B6B' },
      ].map(({ label, value, icon, color }) => (
        <Box key={label} sx={{ display: 'grid', gridTemplateColumns: '30px 1fr auto', alignItems: 'center', gap: 1, py: 0.75, borderBottom: '1px solid', borderColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(255,255,255,.12)' : 'rgba(26,26,26,.16)', '&:last-child': { borderBottom: 0 } }}>
          <Box sx={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: '8px', backgroundColor: color, color: '#1A1A1A', border: '2px solid #1A1A1A' }}>
            {icon}
          </Box>
          <Typography component="dt" sx={{ color: 'text.secondary', fontWeight: 800, fontSize: '0.76rem', lineHeight: 1.25 }}>{label}</Typography>
          <Typography component="dd" sx={{ m: 0, fontWeight: 900, fontSize: '1.05rem' }}>{value}</Typography>
        </Box>
      ))}
    </Box>
  </Box>
);
