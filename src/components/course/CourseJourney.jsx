import React from 'react';
import { Box, ButtonBase, Chip, LinearProgress, Typography } from '@mui/material';
import { Check, CheckCircle2, Lock, MapPin, Play, Rocket } from 'lucide-react';

const lessonColors = ['#FF6B6B', '#4ECDC4', '#FFE66D', '#A78BFA', '#F59E62'];

const CourseJourney = ({ lessons, progressPercent, onLessonClick }) => (
  <Box
    component="section"
    aria-labelledby="journey-title"
    sx={{
      backgroundColor: (theme) => theme.spanishAmigo.surfaces.raised,
      border: (theme) => `${theme.spanishAmigo.outline.width}px solid ${theme.spanishAmigo.outline.color}`,
      borderRadius: { xs: '18px', sm: '24px' },
      boxShadow: (theme) => theme.spanishAmigo.shadows.card,
      p: { xs: 2, sm: 3, md: 3.5 },
    }}
  >
    <Box sx={{ textAlign: 'center', mb: { xs: 2.5, sm: 3 } }}>
      <Box
        sx={{
          width: { xs: 54, sm: 62 },
          height: { xs: 54, sm: 62 },
          borderRadius: '16px',
          backgroundColor: (theme) => theme.spanishAmigo.colors.coral,
          display: 'grid',
          placeItems: 'center',
          border: (theme) => `3px solid ${theme.spanishAmigo.outline.color}`,
          boxShadow: (theme) => theme.spanishAmigo.shadows.control,
          mx: 'auto',
          mb: 2,
        }}
      >
        <MapPin size={28} color="#fff" strokeWidth={2.7} aria-hidden="true" />
      </Box>
      <Typography id="journey-title" component="h1" variant="h3" sx={{ fontWeight: 900, letterSpacing: '-0.035em' }}>
        Tu Viaje Español
      </Typography>
      <Typography sx={{ mt: 0.5, color: 'text.secondary', fontWeight: 700, fontSize: { xs: '0.9rem', sm: '1rem' } }}>
        Una conversación a la vez
      </Typography>
    </Box>

    <Box
      sx={{
        backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#35304A' : '#FFE66D',
        color: (theme) => theme.palette.mode === 'dark' ? '#fff' : '#1A1A1A',
        border: (theme) => `3px solid ${theme.spanishAmigo.outline.color}`,
        borderRadius: '16px',
        boxShadow: (theme) => theme.spanishAmigo.shadows.control,
        p: { xs: 1.5, sm: 2 },
        mb: 3,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'end', justifyContent: 'space-between', gap: 2, mb: 1.25 }}>
        <Box>
          <Typography sx={{ fontSize: '0.72rem', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '.09em', opacity: 0.72 }}>
            Course progress
          </Typography>
          <Typography sx={{ fontSize: { xs: '1.35rem', sm: '1.55rem' }, fontWeight: 900, lineHeight: 1.15 }}>
            Your learning journey
          </Typography>
        </Box>
        <Typography aria-label={`${progressPercent} percent complete`} sx={{ color: (theme) => theme.spanishAmigo.colors.purple, fontSize: { xs: '1.5rem', sm: '1.8rem' }, fontWeight: 900, lineHeight: 1 }}>
          {progressPercent}%
        </Typography>
      </Box>
      <LinearProgress variant="determinate" value={progressPercent} aria-label="Course completion" />
    </Box>

    <Box component="ol" aria-label="Spanish course lessons" sx={{ listStyle: 'none', p: 0, m: 0, display: 'flex', flexDirection: 'column', gap: { xs: 1.5, sm: 1.75 } }}>
      {lessons.map((lesson, index) => {
        const isLocked = lesson.status === 'locked';
        const isCompleted = lesson.status === 'completed';
        const isActive = lesson.status === 'active';
        const accent = lessonColors[index % lessonColors.length];

        return (
          <Box component="li" key={lesson.id}>
            <ButtonBase
              disabled={isLocked}
              onClick={() => onLessonClick(lesson, isLocked)}
              aria-label={`Lesson ${lesson.number}: ${lesson.title}. ${isCompleted ? 'Completed' : isActive ? 'Ready to start' : 'Locked'}`}
              sx={{
                width: '100%',
                textAlign: 'left',
                alignItems: 'stretch',
                borderRadius: '14px',
                color: 'inherit',
                '&.Mui-focusVisible': {
                  outline: (theme) => `4px solid ${theme.palette.mode === 'dark' ? theme.spanishAmigo.colors.yellow : '#4C1D95'}`,
                  outlineOffset: '4px',
                },
              }}
            >
              <Box
                sx={{
                  width: '100%',
                  display: { xs: 'grid', sm: 'flex' },
                  gridTemplateColumns: { xs: '42px minmax(0, 1fr)' },
                  alignItems: 'center',
                  columnGap: { xs: 1.25, sm: 1.75 },
                  rowGap: { xs: 0.75, sm: 0 },
                  p: { xs: 1.25, sm: 1.5 },
                  borderRadius: '14px',
                  border: (theme) => `3px solid ${isLocked ? (theme.palette.mode === 'dark' ? '#55576A' : '#A8AFBA') : theme.spanishAmigo.outline.color}`,
                  backgroundColor: (theme) => isLocked
                    ? (theme.palette.mode === 'dark' ? '#2B2B3F' : '#ECEEF1')
                    : isActive
                      ? accent
                      : (theme.palette.mode === 'dark' ? '#34344E' : '#FFFFFF'),
                  boxShadow: (theme) => isLocked ? 'none' : theme.spanishAmigo.shadows.control,
                  opacity: isLocked ? 0.72 : 1,
                  transition: 'transform .16s ease, box-shadow .16s ease, background-color .16s ease',
                  '@media (prefers-reduced-motion: reduce)': { transition: 'none' },
                  ...(isLocked ? {} : {
                    '&:hover': { transform: 'translate(-2px, -2px)', boxShadow: (theme) => `5px 5px 0 ${theme.palette.mode === 'dark' ? '#000' : '#1A1A1A'}` },
                    '&:active': { transform: 'translate(2px, 2px)', boxShadow: 'none' },
                  }),
                }}
              >
                <Box
                  sx={{
                    width: { xs: 42, sm: 48 },
                    height: { xs: 42, sm: 48 },
                    flexShrink: 0,
                    display: 'grid',
                    placeItems: 'center',
                    borderRadius: '12px',
                    backgroundColor: (theme) => isLocked ? (theme.palette.mode === 'dark' ? '#3B3B50' : '#D8DCE2') : '#FFFFFF',
                    color: isLocked ? 'text.disabled' : '#1A1A1A',
                    border: (theme) => `2px solid ${isLocked ? (theme.palette.mode === 'dark' ? '#626477' : '#A8AFBA') : '#1A1A1A'}`,
                    fontWeight: 900,
                  }}
                >
                  {isLocked ? <Lock size={19} aria-hidden="true" /> : isCompleted ? <CheckCircle2 size={23} color="#008F72" aria-hidden="true" /> : lesson.number}
                </Box>

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontWeight: 900, fontSize: { xs: '0.92rem', sm: '1rem' }, lineHeight: 1.3, color: isActive ? '#1A1A1A' : isLocked ? 'text.secondary' : 'text.primary', overflowWrap: 'anywhere' }}>
                    <Box component="span" sx={{ opacity: 0.65, mr: 0.6 }}>{lesson.number}.</Box>
                    {lesson.title}
                  </Typography>
                </Box>

                <Chip
                  icon={isCompleted ? <Check size={14} /> : isActive ? <Play size={13} fill="currentColor" /> : <Lock size={13} />}
                  label={isCompleted ? 'Done' : isActive ? 'Start' : 'Locked'}
                  size="small"
                  sx={{
                    flexShrink: 0,
                    alignSelf: { xs: 'flex-start', sm: 'center' },
                    gridColumn: { xs: 2, sm: 'auto' },
                    justifySelf: { xs: 'start', sm: 'auto' },
                    display: { xs: isLocked ? 'none' : 'inline-flex', sm: 'inline-flex' },
                    backgroundColor: isActive ? '#1A1A1A' : isCompleted ? (theme => theme.palette.mode === 'dark' ? '#4ECDC4' : '#E6FFF9') : 'transparent',
                    color: isActive ? '#FFFFFF' : isCompleted ? '#1A1A1A' : 'text.secondary',
                    borderColor: isLocked ? 'transparent' : undefined,
                    boxShadow: isLocked ? 'none' : undefined,
                    '& .MuiChip-icon': { color: 'inherit' },
                  }}
                />
              </Box>
            </ButtonBase>
          </Box>
        );
      })}
    </Box>

    {progressPercent === 100 && (
      <Box sx={{ mt: 3, p: 2.5, textAlign: 'center', borderRadius: '14px', border: (theme) => `3px solid ${theme.spanishAmigo.outline.color}`, backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#35304A' : '#FFF4B8' }}>
        <Rocket size={34} color="#FF6B6B" aria-hidden="true" />
        <Typography sx={{ mt: 0.5, fontWeight: 900, fontSize: '1.2rem' }}>¡Felicidades!</Typography>
        <Typography sx={{ color: 'text.secondary', fontWeight: 700, fontSize: '0.86rem' }}>You've completed the journey!</Typography>
      </Box>
    )}
  </Box>
);

export default CourseJourney;
