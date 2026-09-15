import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Collapse, Dialog, DialogActions, DialogContent,
  DialogTitle, Stack, TextField, Typography,
} from '@mui/material';
import {
  AlertCircle, Brain, CheckCircle2, ChevronDown, ChevronUp, Clock, HelpCircle,
  RotateCcw, Sparkles, TrendingUp,
} from 'lucide-react';
import { getAdaptiveState, getDueReviews, getNextReview, startReview, submitReview } from '../../api/adaptive';
import { useAuth } from '../../context/AuthContext';

const mainPanelSx = {
  border: (theme) => `3px solid ${theme.spanishAmigo.outline.color}`,
  borderRadius: '16px',
  boxShadow: (theme) => theme.spanishAmigo.shadows.card,
  backgroundColor: (theme) => theme.spanishAmigo.surfaces.raised,
};

const skillCardSx = {
  border: (theme) => `1.5px solid ${theme.palette.mode === 'dark' ? '#33334D' : '#E2E4EB'}`,
  borderRadius: '12px',
  backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#1E1E34' : '#FBFBFE',
  p: { xs: 1.5, sm: 1.75 },
  minWidth: 0,
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'space-between',
  transition: 'border-color 0.15s ease, background-color 0.15s ease',
  '&:hover': {
    borderColor: (theme) => theme.spanishAmigo.colors.purple,
  },
};

const formatDate = (value) => {
  if (!value) return null;
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value));
  } catch {
    return null;
  }
};

function getSkillCategory(skillId) {
  if (skillId.startsWith('grammar.')) return 'Grammar';
  if (skillId.startsWith('vocabulary.')) return 'Vocabulary';
  if (skillId.startsWith('pronunciation.')) return 'Pronunciation';
  if (skillId.startsWith('communication.')) return 'Communication';
  if (skillId.startsWith('contextual.')) return 'Conversation';
  return 'Skill';
}

function formatSkillTitle(skill) {
  return skill.display_name;
}

function getSkillStatusInfo(skill) {
  if (skill.assessment_mode === 'speech_required') {
    return {
      label: 'Speaking practice needed',
      color: 'secondary',
      feedback: 'This can only be checked when you speak.',
    };
  }
  if (skill.assessment_mode === 'contextual') {
    return {
      label: 'Practice activity',
      color: 'info',
      feedback: skill.last_practiced_at ? 'Practiced in conversation.' : 'Practice in conversation.',
    };
  }
  const isVocab = skill.skill_id.startsWith('vocabulary.');
  if (typeof skill.mastery_estimate === 'number') {
    if (skill.mastery_estimate >= 0.70) {
      return {
        label: 'Going well',
        color: 'success',
        feedback: isVocab ? "You're using these words correctly." : "You're using this correctly.",
      };
    }
    if (skill.mastery_estimate >= 0.40) {
      return {
        label: 'Needs practice',
        color: 'warning',
        feedback: 'Still developing.',
      };
    }
    return {
      label: 'Needs practice',
      color: 'warning',
      feedback: 'You had some trouble with this recently.',
    };
  }
  if (skill.status === 'evidence_insufficient') {
    return {
      label: 'Needs practice',
      color: 'warning',
      feedback: 'You had some trouble with this recently.',
    };
  }
  return {
    label: 'Not enough practice yet',
    color: 'default',
    feedback: 'Practice exercises to build your skill profile.',
  };
}

function SkillItemCard({ skill, compact = false }) {
  const [showInfo, setShowInfo] = useState(false);
  const isSpeech = skill.assessment_mode === 'speech_required';
  const isContextual = skill.assessment_mode === 'contextual';
  const category = getSkillCategory(skill.skill_id);
  const formattedLastPracticed = formatDate(skill.last_practiced_at);
  const statusInfo = getSkillStatusInfo(skill);
  const title = formatSkillTitle(skill);

  const hasExtraDetail = Boolean(skill.learning_objective || isSpeech || isContextual);

  return (
    <Box component="article" sx={skillCardSx}>
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 0.75, flexWrap: 'wrap' }}>
          <Chip
            label={category}
            size="small"
            sx={{
              fontSize: '0.68rem',
              fontWeight: 800,
              height: 22,
              borderRadius: '6px',
              backgroundColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.06)' : 'rgba(26,26,26,0.06)',
            }}
          />
          <Chip
            label={statusInfo.label}
            size="small"
            color={statusInfo.color === 'default' ? undefined : statusInfo.color}
            variant={statusInfo.color === 'default' ? 'outlined' : 'filled'}
            sx={{
              fontSize: '0.68rem',
              fontWeight: 800,
              height: 22,
              borderRadius: '6px',
            }}
          />
        </Box>

        <Typography component="h4" sx={{ fontWeight: 900, fontSize: compact ? '0.92rem' : '0.96rem', lineHeight: 1.3, overflowWrap: 'anywhere' }}>
          {title}
        </Typography>

        <Typography sx={{ mt: 0.75, fontSize: '0.78rem', color: 'text.secondary', fontWeight: 700, lineHeight: 1.4 }}>
          {statusInfo.feedback}
        </Typography>
      </Box>

      {/* Footer / Context info */}
      <Box sx={{ mt: 1.25, pt: 1, borderTop: '1px solid', borderColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.06)' : 'rgba(26,26,26,0.06)' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            {formattedLastPracticed ? (
              <Typography sx={{ fontSize: '0.72rem', color: 'text.secondary', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 0.4 }}>
                <Clock size={11} aria-hidden="true" />
                {formattedLastPracticed}
              </Typography>
            ) : (
              <Typography sx={{ fontSize: '0.72rem', color: 'text.secondary', fontWeight: 700 }}>
                {statusInfo.label === 'Not enough practice yet' ? 'Not practiced yet' : 'Tracked skill'}
              </Typography>
            )}
          </Box>

          {hasExtraDetail && (
            <Button
              size="small"
              onClick={() => setShowInfo((open) => !open)}
              aria-expanded={showInfo}
              aria-label={`Details for ${skill.display_name}`}
              sx={{
                minWidth: 'auto',
                p: '2px 6px',
                fontSize: '0.68rem',
                fontWeight: 800,
                color: 'text.secondary',
                border: 'none',
                boxShadow: 'none',
                '&:hover': { background: 'transparent', color: 'text.primary' },
              }}
            >
              <HelpCircle size={13} style={{ marginRight: 3 }} />
              {showInfo ? 'Less' : 'Details'}
            </Button>
          )}
        </Box>

        <Collapse in={showInfo} unmountOnExit>
          <Box sx={{ mt: 1, p: 1, borderRadius: '8px', backgroundColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)' }}>
            <Typography sx={{ fontSize: '0.72rem', color: 'text.secondary', fontWeight: 700 }}>
              {isContextual && 'Practiced through conversation scenarios with Lumi.'}
              {isSpeech && 'Requires spoken voice practice to check pronunciation.'}
              {!isContextual && !isSpeech && (skill.learning_objective || 'Practiced and assessed through lesson exercises and review activities.')}
            </Typography>
          </Box>
        </Collapse>
      </Box>
    </Box>
  );
}

function ReviewDialog({ review, attempt, onClose, onSubmit, submitting, result, error }) {
  const [answer, setAnswer] = useState('');
  const [showWhy, setShowWhy] = useState(false);
  const canSubmit = answer.trim().length > 0 && !submitting && !result;

  const resultMessage = result?.status === 'accepted'
    ? result.result === 'correct'
      ? 'Great job! Your answer was correct. Your progress has been updated.'
      : result.result === 'incorrect'
        ? "Good try! We'll include this in future practice to help you master it."
        : 'Your answer was recorded and your progress has been updated.'
    : result ? "This answer was recorded. Keep practicing in upcoming lessons and reviews!" : null;

  return (
    <Dialog
      open={Boolean(review && attempt)}
      onClose={submitting ? undefined : onClose}
      fullWidth
      maxWidth="sm"
      aria-labelledby="review-title"
      PaperProps={{
        sx: {
          borderRadius: '16px',
          border: (theme) => `3px solid ${theme.spanishAmigo.outline.color}`,
          boxShadow: (theme) => theme.spanishAmigo.shadows.card,
        },
      }}
    >
      <DialogTitle id="review-title" sx={{ fontWeight: 900 }}>Review: {review?.display_name}</DialogTitle>
      <DialogContent>
        <Typography sx={{ fontWeight: 900, fontSize: '1.05rem', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', mb: 1 }}>
          {attempt?.exercise_text}
        </Typography>
        {review?.rationale && (
          <>
            <Button
              onClick={() => setShowWhy((open) => !open)}
              endIcon={showWhy ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              sx={{ mb: 1.5, px: 0, minHeight: 36, fontSize: '0.8rem' }}
              aria-expanded={showWhy}
            >
              Why this exercise?
            </Button>
            <Collapse in={showWhy}>
              <Alert severity="info" sx={{ mb: 2, borderRadius: '10px' }}>{review?.rationale}</Alert>
            </Collapse>
          </>
        )}
        <TextField
          autoFocus
          fullWidth
          multiline
          minRows={3}
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          disabled={submitting || Boolean(result)}
          label="Your answer"
          inputProps={{ maxLength: 2000 }}
          helperText="Type your answer in Spanish."
        />
        {error && <Alert severity="error" sx={{ mt: 2, borderRadius: '10px' }}>{error}</Alert>}
        {resultMessage && (
          <Alert severity={result.status === 'accepted' ? 'success' : 'info'} sx={{ mt: 2, borderRadius: '10px' }}>
            {resultMessage}
          </Alert>
        )}
      </DialogContent>
      <DialogActions sx={{ p: 2.5, pt: 1 }}>
        <Button onClick={onClose} disabled={submitting}>{result ? 'Close' : 'Cancel'}</Button>
        {!result && (
          <Button
            variant="contained"
            onClick={() => onSubmit(answer.trim())}
            disabled={!canSubmit}
            sx={{
              backgroundColor: (theme) => theme.spanishAmigo.colors.coral,
              color: '#fff',
            }}
          >
            {submitting ? 'Submitting…' : 'Submit answer'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

const MySpanishPanel = () => {
  const { user } = useAuth();
  const [state, setState] = useState([]);
  const [due, setDue] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null);
  const [starting, setStarting] = useState('');
  const [showAllSkills, setShowAllSkills] = useState(false);

  const [review, setReview] = useState(null);
  const [attempt, setAttempt] = useState(null);
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const refresh = useCallback(async () => {
    if (!user) return;
    setError('');
    try {
      const [skillState, dueReviews, nextReview] = await Promise.all([
        getAdaptiveState(user),
        getDueReviews(user),
        getNextReview(user),
      ]);
      setState(skillState);
      setDue(dueReviews);
      setNext(nextReview);
      setLastRefreshedAt(new Date());
    } catch (requestError) {
      setError(requestError.message || 'Adaptive learning is unavailable right now.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleManualRefresh = async () => {
    if (refreshing || loading) return;
    setRefreshing(true);
    await refresh();
  };

  const begin = async (dueReview) => {
    setStarting(dueReview.review_id);
    setError('');
    try {
      const started = await startReview(user, dueReview.review_id);
      setReview(dueReview);
      setAttempt(started);
      setSubmitError('');
      setResult(null);
    } catch (requestError) {
      setError(requestError.message || 'Unable to start this review.');
    } finally {
      setStarting('');
    }
  };

  const sendAnswer = async (learnerAnswer) => {
    if (!review || !attempt || submitting) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      const submission = await submitReview(user, review.review_id, attempt.attempt_id, learnerAnswer);
      setResult(submission);
      await refresh();
    } catch (requestError) {
      setSubmitError(requestError.message || 'Unable to submit your answer. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Identify skills with learner evidence or practice history
  const skillsWithEvidence = useMemo(() => {
    return state.filter((s) => (s.accepted_evidence_count || 0) > 0 || typeof s.mastery_estimate === 'number' || Boolean(s.last_practiced_at));
  }, [state]);

  const hasEvidence = skillsWithEvidence.length > 0;

  // Real "Needs Practice" skills: low estimate, developing, or insufficient evidence
  const needsPracticeSkills = useMemo(() => {
    if (!hasEvidence) return [];
    return skillsWithEvidence.filter((skill) => {
      if (skill.assessment_mode === 'speech_required' || skill.assessment_mode === 'contextual') return false;
      if (typeof skill.mastery_estimate === 'number') {
        return skill.mastery_estimate < 0.70;
      }
      return skill.status === 'evidence_insufficient';
    });
  }, [skillsWithEvidence, hasEvidence]);

  // Real "Going Well" skills: solid or high mastery
  const goingWellSkills = useMemo(() => {
    if (!hasEvidence) return [];
    return skillsWithEvidence.filter((skill) => {
      if (skill.assessment_mode === 'speech_required' || skill.assessment_mode === 'contextual') return false;
      if (typeof skill.mastery_estimate === 'number') {
        return skill.mastery_estimate >= 0.70;
      }
      return false;
    });
  }, [skillsWithEvidence, hasEvidence]);

  // Complete sorted state for full taxonomy (prioritize assessed skills, then alphabetical)
  const fullSortedSkills = useMemo(() => {
    return [...state].sort((a, b) => {
      const countDiff = (b.accepted_evidence_count || 0) - (a.accepted_evidence_count || 0);
      if (countDiff !== 0) return countDiff;
      return a.display_name.localeCompare(b.display_name);
    });
  }, [state]);

  if (loading) {
    return (
      <Box component="section" aria-label="Loading My Spanish" sx={{ ...mainPanelSx, p: 3, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress aria-label="Loading adaptive learning" />
      </Box>
    );
  }

  return (
    <Box component="section" aria-labelledby="my-spanish-title" sx={{ ...mainPanelSx, p: { xs: 2, sm: 2.5 } }}>
      {/* Header Section */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1.5, mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
          <Box
            sx={{
              width: 40,
              height: 40,
              display: 'grid',
              placeItems: 'center',
              border: '2px solid #1A1A1A',
              borderRadius: '10px',
              backgroundColor: (theme) => theme.spanishAmigo.colors.purple,
              color: '#1A1A1A',
              flexShrink: 0,
            }}
          >
            <Brain size={22} aria-hidden="true" />
          </Box>
          <Box>
            <Typography id="my-spanish-title" component="h2" sx={{ fontSize: { xs: '1.25rem', sm: '1.45rem' }, fontWeight: 900, lineHeight: 1.2 }}>
              My Spanish
            </Typography>
            <Typography sx={{ fontSize: '.8rem', color: 'text.secondary', fontWeight: 700, mt: 0.25 }}>
              SpanishAmigo learns from your practice and shows what you&apos;re doing well, what needs more practice, and what to review.
            </Typography>
          </Box>
        </Box>
      </Box>

      {/* Error alert */}
      {error && (
        <Alert
          severity="error"
          action={<Button color="inherit" size="small" onClick={refresh}>Retry</Button>}
          sx={{ mb: 2, borderRadius: '12px' }}
        >
          {error}
        </Alert>
      )}

      {/* Section A: Reviews Area */}
      <Box
        sx={{
          p: { xs: 1.75, sm: 2 },
          border: '2px solid',
          borderColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(78,205,196,0.3)' : 'rgba(26,26,26,0.15)',
          borderRadius: '12px',
          backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#2E4050' : '#DDF9F6',
          mb: 2.5,
        }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} gap={1.5}>
          <Box sx={{ minWidth: 0 }}>
            <Typography component="h3" sx={{ fontWeight: 900, fontSize: '0.96rem' }}>
              {error
                ? 'Reviews unavailable right now'
                : due.length > 0
                  ? `${due.length} ${due.length === 1 ? 'thing ready to review' : 'things ready to review'}`
                  : 'Reviews'}
            </Typography>
            <Typography sx={{ fontSize: '.78rem', color: 'text.secondary', fontWeight: 700, mt: 0.25 }}>
              {error
                ? 'Unable to load reviews.'
                : due.length > 0
                  ? 'Keep what you’ve learned fresh with quick practice.'
                  : next
                    ? `Nothing to review right now · Next review: ${formatDate(next.due_at)}`
                    : 'Nothing to review yet.'}
            </Typography>
          </Box>

          {/* Refresh Action with feedback */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, alignSelf: { xs: 'flex-end', sm: 'center' } }}>
            {lastRefreshedAt && !refreshing && (
              <Typography sx={{ fontSize: '0.7rem', color: 'text.secondary', fontWeight: 700, display: { xs: 'none', sm: 'block' } }}>
                Updated just now
              </Typography>
            )}
            <Button
              variant="outlined"
              size="small"
              onClick={handleManualRefresh}
              disabled={refreshing || loading}
              aria-label="Refresh My Spanish"
              aria-busy={refreshing}
              startIcon={
                refreshing ? (
                  <CircularProgress size={13} color="inherit" />
                ) : (
                  <RotateCcw size={14} />
                )
              }
              sx={{
                minHeight: 34,
                px: 1.5,
                py: 0.5,
                fontSize: '0.74rem',
                fontWeight: 800,
                borderRadius: '8px',
                borderWidth: '2px',
                backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#1A1A2E' : '#FFFFFF',
                '&:hover': { borderWidth: '2px' },
                '&:active': { transform: 'scale(0.97)' },
              }}
            >
              {refreshing ? 'Updating…' : 'Refresh'}
            </Button>
          </Box>
        </Stack>

        {/* List of due reviews */}
        {!error && due.length > 0 && (
          <Stack spacing={1.25} sx={{ mt: 1.75 }}>
            {due.map((item) => (
              <Box
                key={item.review_id}
                sx={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 1.25,
                  pt: 1.25,
                  borderTop: '1px solid',
                  borderColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(26,26,26,0.12)',
                }}
              >
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography sx={{ fontWeight: 900, fontSize: '.9rem' }}>{item.display_name}</Typography>
                  <Typography sx={{ fontSize: '.75rem', color: 'text.secondary', fontWeight: 700 }}>
                    {item.rationale || 'Ready for review'} {item.due_at ? `· due ${formatDate(item.due_at)}` : ''}
                  </Typography>
                </Box>
                <Button
                  variant="contained"
                  size="small"
                  onClick={() => begin(item)}
                  disabled={Boolean(starting)}
                  startIcon={starting === item.review_id ? <CircularProgress size={13} color="inherit" /> : <Sparkles size={14} />}
                  sx={{
                    minHeight: 34,
                    px: 1.5,
                    py: 0.5,
                    fontSize: '0.76rem',
                    backgroundColor: (theme) => theme.spanishAmigo.colors.coral,
                    color: '#fff',
                    flexShrink: 0,
                  }}
                >
                  {starting === item.review_id ? 'Starting…' : 'Review now'}
                </Button>
              </Box>
            ))}
          </Stack>
        )}
      </Box>

      {/* Brand-New Learner State */}
      {!hasEvidence ? (
        <Box
          sx={{
            p: { xs: 2.5, sm: 3 },
            borderRadius: '14px',
            border: (theme) => `1.5px dashed ${theme.palette.mode === 'dark' ? '#3A3A54' : '#CCD0DD'}`,
            backgroundColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.02)' : '#FAFAFD',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 1.25,
          }}
        >
          <Box
            sx={{
              width: 44,
              height: 44,
              display: 'grid',
              placeItems: 'center',
              borderRadius: '50%',
              backgroundColor: (theme) => theme.spanishAmigo.colors.yellow,
              color: '#1A1A1A',
              border: '2px solid #1A1A1A',
            }}
          >
            <Sparkles size={22} aria-hidden="true" />
          </Box>
          <Typography component="h3" sx={{ fontWeight: 900, fontSize: '1.05rem' }}>
            Your skill profile will appear as you practice.
          </Typography>
          <Typography sx={{ color: 'text.secondary', fontSize: '0.84rem', fontWeight: 700, maxWidth: 460, lineHeight: 1.5 }}>
            Complete lessons or practice with Lumi to get started.
          </Typography>
          <Button
            variant="outlined"
            size="small"
            onClick={() => setShowAllSkills((prev) => !prev)}
            endIcon={showAllSkills ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            aria-expanded={showAllSkills}
            sx={{
              mt: 1,
              minHeight: 38,
              px: 2,
              fontSize: '0.8rem',
              fontWeight: 800,
              borderRadius: '10px',
              borderWidth: '2px',
              backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#1E1E34' : '#FFFFFF',
            }}
          >
            {showAllSkills ? 'Hide all skills' : 'Explore all skills'}
          </Button>
        </Box>
      ) : (
        /* Learner with Data */
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
          {/* Section B: Needs Practice (only rendered when real data exists) */}
          {needsPracticeSkills.length > 0 && (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.25 }}>
                <AlertCircle size={17} color="#FF6B6B" aria-hidden="true" />
                <Typography component="h3" sx={{ fontWeight: 900, fontSize: '1.02rem' }}>
                  Needs Practice
                </Typography>
              </Box>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'repeat(2, minmax(0, 1fr))' },
                  gap: 1.5,
                }}
              >
                {needsPracticeSkills.map((skill) => (
                  <SkillItemCard key={skill.skill_id} skill={skill} compact />
                ))}
              </Box>
            </Box>
          )}

          {/* Section C: Going Well / Recent Progress (only rendered when real data exists) */}
          {goingWellSkills.length > 0 && (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.25 }}>
                <TrendingUp size={17} color="#4ECDC4" aria-hidden="true" />
                <Typography component="h3" sx={{ fontWeight: 900, fontSize: '1.02rem' }}>
                  Going Well
                </Typography>
              </Box>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'repeat(2, minmax(0, 1fr))' },
                  gap: 1.5,
                }}
              >
                {goingWellSkills.map((skill) => (
                  <SkillItemCard key={skill.skill_id} skill={skill} compact />
                ))}
              </Box>
            </Box>
          )}

          {/* Secondary Control: Explore all skills */}
          <Box sx={{ display: 'flex', justifyContent: 'center', pt: 0.5 }}>
            <Button
              variant="outlined"
              size="small"
              onClick={() => setShowAllSkills((prev) => !prev)}
              endIcon={showAllSkills ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              aria-expanded={showAllSkills}
              sx={{
                minHeight: 38,
                px: 2.25,
                fontSize: '0.8rem',
                fontWeight: 800,
                borderRadius: '10px',
                borderWidth: '2px',
                backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#1E1E34' : '#FFFFFF',
              }}
            >
              {showAllSkills ? 'Hide all skills' : 'Explore all skills'}
            </Button>
          </Box>
        </Box>
      )}

      {/* Full Taxonomy Expanded */}
      <Collapse in={showAllSkills} unmountOnExit>
        <Box sx={{ mt: 2.5, pt: 2, borderTop: '1px solid', borderColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(26,26,26,0.08)' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.75 }}>
            <CheckCircle2 size={16} color="#4ECDC4" aria-hidden="true" />
            <Typography component="h3" sx={{ fontWeight: 900, fontSize: '0.94rem' }}>
              All skills ({fullSortedSkills.length})
            </Typography>
          </Box>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: 'minmax(0, 1fr)',
                sm: 'repeat(2, minmax(0, 1fr))',
                lg: 'repeat(3, minmax(0, 1fr))',
              },
              gap: 1.5,
            }}
          >
            {fullSortedSkills.map((skill) => (
              <SkillItemCard key={skill.skill_id} skill={skill} />
            ))}
          </Box>
        </Box>
      </Collapse>

      {/* Review Dialog */}
      <ReviewDialog
        review={review}
        attempt={attempt}
        onClose={() => {
          setReview(null);
          setAttempt(null);
          setResult(null);
          setSubmitError('');
        }}
        onSubmit={sendAnswer}
        submitting={submitting}
        result={result}
        error={submitError}
      />
    </Box>
  );
};

export default MySpanishPanel;
