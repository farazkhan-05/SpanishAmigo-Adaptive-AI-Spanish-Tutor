import React from 'react';
import { Box } from '@mui/material';
import { useNavigate } from 'react-router-dom';

import CourseJourney from '../components/course/CourseJourney';
import { ContinueLearningPanel, CourseSummaryPanel } from '../components/course/CourseSupportPanels';
import MySpanishPanel from '../components/course/MySpanishPanel';
import { courseData } from '../data/curriculum';
import { useAuth } from '../context/AuthContext';
import { useProgress } from '../context/ProgressContext';

const CourseMap = () => {
  const navigate = useNavigate();
  const { isAnonymous, openSignInPrompt } = useAuth();
  const { completedLessons } = useProgress();

  // Keep lesson availability and progress rules centralized here.
  const progressPercent = Math.round((completedLessons.length / courseData.length) * 100);

  const getLessonStatus = (lessonId, index) => {
    if (completedLessons.includes(lessonId)) return 'completed';
    const prevLessonId = index > 0 ? courseData[index - 1].id : null;
    if (index === 0 || completedLessons.includes(prevLessonId)) return 'active';
    return 'locked';
  };

  const handleLessonClick = (lesson, isLocked) => {
    if (isLocked) return;
    if (isAnonymous && lesson.id > 1) {
      openSignInPrompt('save-progress');
      return;
    }
    navigate(`/lesson/${lesson.id}`);
  };

  const lessons = courseData.map((lesson, index) => ({
    ...lesson,
    number: index + 1,
    status: getLessonStatus(lesson.id, index),
  }));
  const activeLesson = lessons.find((lesson) => lesson.status === 'active');
  const remainingLessons = courseData.length - completedLessons.length;

  return (
    <Box
      component="main"
      sx={{
        position: 'relative',
        // Leave scroll clearance for the fixed chatbot on compact screens.
        pb: { xs: 10, md: 4 },
        '&::before': {
          content: '""',
          position: 'absolute',
          inset: { xs: '-16px -16px auto', sm: '-24px -24px auto' },
          height: { xs: 190, md: 250 },
          borderRadius: { xs: 0, sm: '24px' },
          background: (theme) => theme.palette.mode === 'dark'
            ? 'linear-gradient(135deg, rgba(78,205,196,.12), rgba(167,139,250,.08))'
            : 'linear-gradient(135deg, rgba(78,205,196,.22), rgba(255,230,109,.16))',
          pointerEvents: 'none',
        },
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          display: { xs: 'none', md: 'block' },
          position: 'absolute',
          width: 74,
          height: 74,
          border: '12px solid',
          borderColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(78,205,196,.16)' : 'rgba(78,205,196,.28)',
          borderRadius: '50%',
          top: 34,
          left: -8,
          pointerEvents: 'none',
        }}
      />
      <Box
        aria-hidden="true"
        sx={{
          display: { xs: 'none', lg: 'block' },
          position: 'absolute',
          width: 22,
          height: 22,
          border: '5px solid',
          borderColor: (theme) => theme.spanishAmigo.colors.purple,
          transform: 'rotate(45deg)',
          opacity: 0.45,
          top: 112,
          right: 28,
          pointerEvents: 'none',
        }}
      />

      <Box
        sx={{
          position: 'relative',
          display: 'grid',
          gridTemplateColumns: {
            xs: 'minmax(0, 1fr)',
            sm: 'minmax(0, 1fr) minmax(0, 1fr)',
            md: 'minmax(0, 1fr) 280px',
            lg: '230px minmax(0, 1fr) 230px',
            xl: '250px minmax(0, 1fr) 250px',
          },
          gridTemplateAreas: {
            xs: '"journey" "continue" "summary" "adaptive"',
            sm: '"journey journey" "continue summary" "adaptive adaptive"',
            md: '"journey summary" "continue summary" "adaptive adaptive"',
            lg: '"continue journey summary" "adaptive adaptive adaptive"',
          },
          alignItems: 'start',
          gap: { xs: 2.5, sm: 3, lg: 3.5 },
        }}
      >
        <Box sx={{ gridArea: 'continue', pt: { lg: 14 } }}>
          <ContinueLearningPanel
            lesson={activeLesson}
            isComplete={progressPercent === 100}
            onContinue={() => activeLesson && handleLessonClick(activeLesson, false)}
          />
        </Box>

        <Box sx={{ gridArea: 'journey', minWidth: 0 }}>
          <CourseJourney
            lessons={lessons}
            progressPercent={progressPercent}
            onLessonClick={handleLessonClick}
          />
        </Box>

        <Box sx={{ gridArea: 'summary', pt: { md: 5, lg: 24 } }}>
          <CourseSummaryPanel
            completedCount={completedLessons.length}
            remainingCount={remainingLessons}
            totalCount={courseData.length}
          />
        </Box>

        <Box sx={{ gridArea: 'adaptive', minWidth: 0, mt: { xs: .5, lg: 1 } }}>
          <MySpanishPanel />
        </Box>
      </Box>
    </Box>
  );
};

export default CourseMap;
