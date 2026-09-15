import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, CircularProgress, Collapse, Dialog, DialogActions, DialogContent,
  DialogTitle, Divider, LinearProgress, Stack, TextField, Typography,
} from '@mui/material';
import { Brain, ChevronDown, ChevronUp, RotateCcw, Sparkles } from 'lucide-react';
import { getAdaptiveState, getDueReviews, getNextReview, startReview, submitReview } from '../../api/adaptive';
import { useAuth } from '../../context/AuthContext';

const cardSx = {
  border: (theme) => `3px solid ${theme.spanishAmigo.outline.color}`,
  borderRadius: '16px',
  boxShadow: (theme) => theme.spanishAmigo.shadows.card,
  backgroundColor: (theme) => theme.spanishAmigo.surfaces.raised,
};

const formatDate = (value) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value)) : 'Not practiced yet';
const percent = (value) => `${Math.round(value * 100)}%`;

function SkillCard({ skill }) {
  const isSpeech = skill.assessment_mode === 'speech_required';
  const isContextual = skill.assessment_mode === 'contextual';
  const hasEstimate = typeof skill.mastery_estimate === 'number';
  const vocabulary = skill.skill_id.startsWith('vocabulary.');

  let status = 'Not assessed yet';
  if (isSpeech) status = 'Speech assessment not available yet';
  else if (isContextual) status = 'Practice context';
  else if (skill.status === 'evidence_insufficient') status = 'More validated evidence is needed';
  else if (hasEstimate) status = 'Evidence-backed estimate';

  return (
    <Box component="article" sx={{ ...cardSx, p: 2, minWidth: 0 }}>
      <Typography component="h3" sx={{ fontWeight: 900, fontSize: '1rem', overflowWrap: 'anywhere' }}>{skill.display_name}</Typography>
      <Typography sx={{ mt: .45, color: 'text.secondary', fontSize: '.78rem', fontWeight: 800 }}>{status}</Typography>
      {hasEstimate && !isSpeech && !isContextual && (
        <Box sx={{ mt: 1.5 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'baseline' }}>
            <Typography sx={{ fontWeight: 900, fontSize: '.8rem' }}>Mastery estimate</Typography>
            <Typography sx={{ fontWeight: 900, fontSize: '1.2rem' }}>{percent(skill.mastery_estimate)}</Typography>
          </Box>
          <LinearProgress variant="determinate" value={skill.mastery_estimate * 100} aria-label={`${skill.display_name} mastery estimate ${percent(skill.mastery_estimate)}`} sx={{ mt: .7 }} />
        </Box>
      )}
      {hasEstimate && typeof skill.estimate_confidence === 'number' && !isSpeech && !isContextual && (
        <Typography sx={{ mt: 1.15, fontSize: '.78rem', color: 'text.secondary', fontWeight: 800 }}>
          Evidence strength: {percent(skill.estimate_confidence)}
        </Typography>
      )}
      {isContextual && <Typography sx={{ mt: 1.15, fontSize: '.78rem', color: 'text.secondary', fontWeight: 800 }}>A learning scenario, not an atomic mastery score.</Typography>}
      {vocabulary && <Typography sx={{ mt: 1.15, fontSize: '.78rem', color: 'text.secondary', fontWeight: 800 }}>Practice is tracked by taught words; one word does not establish this whole domain.</Typography>}
      <Divider sx={{ my: 1.3 }} />
      <Typography sx={{ fontSize: '.76rem', color: 'text.secondary', fontWeight: 800 }}>Accepted evidence: {skill.accepted_evidence_count}</Typography>
      <Typography sx={{ mt: .35, fontSize: '.76rem', color: 'text.secondary', fontWeight: 800 }}>Last practiced: {formatDate(skill.last_practiced_at)}</Typography>
    </Box>
  );
}

function ReviewDialog({ review, attempt, onClose, onSubmit, submitting, result, error }) {
  const [answer, setAnswer] = useState('');
  const [showWhy, setShowWhy] = useState(false);
  const canSubmit = answer.trim().length > 0 && !submitting && !result;
  const resultMessage = result?.status === 'accepted'
    ? result.result === 'correct'
      ? 'Your response was accepted as correct. Your learning state has been refreshed.'
      : result.result === 'incorrect'
        ? 'Your response was accepted as incorrect. Your learning state has been refreshed for future practice.'
        : 'Your response was accepted and your learning state has been refreshed.'
    : result ? 'This answer was recorded, but it did not create accepted evidence. Try future practice when you are ready.' : null;
  return (
    <Dialog open={Boolean(review && attempt)} onClose={submitting ? undefined : onClose} fullWidth maxWidth="sm" aria-labelledby="review-title">
      <DialogTitle id="review-title">Review: {review?.display_name}</DialogTitle>
      <DialogContent>
        <Typography sx={{ fontWeight: 900, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{attempt?.exercise_text}</Typography>
        <Button onClick={() => setShowWhy((open) => !open)} endIcon={showWhy ? <ChevronUp size={16} /> : <ChevronDown size={16} />} sx={{ mt: 1, px: 0, minHeight: 36 }} aria-expanded={showWhy}>
          Why this exercise?
        </Button>
        <Collapse in={showWhy}><Alert severity="info" sx={{ mb: 2 }}>{review?.rationale}</Alert></Collapse>
        <TextField autoFocus fullWidth multiline minRows={3} value={answer} onChange={(event) => setAnswer(event.target.value)} disabled={submitting || Boolean(result)} label="Your answer" inputProps={{ maxLength: 2000 }} helperText="Your answer is assessed by the server after submission." />
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        {resultMessage && <Alert severity={result.status === 'accepted' ? 'success' : 'warning'} sx={{ mt: 2 }}>{resultMessage}</Alert>}
      </DialogContent>
      <DialogActions sx={{ p: 2.5, pt: 1 }}>
        <Button onClick={onClose} disabled={submitting}>{result ? 'Close' : 'Cancel'}</Button>
        {!result && <Button variant="contained" onClick={() => onSubmit(answer.trim())} disabled={!canSubmit}>{submitting ? 'Submitting…' : 'Submit answer'}</Button>}
      </DialogActions>
    </Dialog>
  );
}

const MySpanishPanel = () => {
  const { user } = useAuth();
  const [state, setState] = useState([]); const [due, setDue] = useState([]); const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [starting, setStarting] = useState('');
  const [review, setReview] = useState(null); const [attempt, setAttempt] = useState(null); const [submitError, setSubmitError] = useState(''); const [submitting, setSubmitting] = useState(false); const [result, setResult] = useState(null);
  const refresh = useCallback(async () => {
    if (!user) return;
    setError('');
    try {
      const [skillState, dueReviews, nextReview] = await Promise.all([getAdaptiveState(user), getDueReviews(user), getNextReview(user)]);
      setState(skillState); setDue(dueReviews); setNext(nextReview);
    } catch (requestError) { setError(requestError.message || 'Adaptive learning is unavailable right now.'); }
    finally { setLoading(false); }
  }, [user]);
  useEffect(() => { refresh(); }, [refresh]);
  const begin = async (dueReview) => {
    setStarting(dueReview.review_id); setError('');
    try { const started = await startReview(user, dueReview.review_id); setReview(dueReview); setAttempt(started); setSubmitError(''); setResult(null); }
    catch (requestError) { setError(requestError.message || 'Unable to start this review.'); }
    finally { setStarting(''); }
  };
  const sendAnswer = async (learnerAnswer) => {
    if (!review || !attempt || submitting) return;
    setSubmitting(true); setSubmitError('');
    try { const submission = await submitReview(user, review.review_id, attempt.attempt_id, learnerAnswer); setResult(submission); await refresh(); }
    catch (requestError) { setSubmitError(requestError.message || 'Unable to submit your answer. Please try again.'); }
    finally { setSubmitting(false); }
  };
  const reviewedState = useMemo(() => [...state].sort((a, b) => (b.accepted_evidence_count - a.accepted_evidence_count) || a.display_name.localeCompare(b.display_name)), [state]);
  if (loading) return <Box component="section" aria-label="Loading My Spanish" sx={{ ...cardSx, p: 3, display: 'flex', justifyContent: 'center' }}><CircularProgress aria-label="Loading adaptive learning" /></Box>;
  return <Box component="section" aria-labelledby="my-spanish-title" sx={{ ...cardSx, p: { xs: 2, sm: 2.5 } }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: 1 }}><Box sx={{ width: 40, height: 40, display: 'grid', placeItems: 'center', border: '2px solid #1A1A1A', borderRadius: '10px', backgroundColor: (theme) => theme.spanishAmigo.colors.purple, color: '#1A1A1A' }}><Brain size={21} aria-hidden="true" /></Box><Box><Typography id="my-spanish-title" component="h2" sx={{ fontSize: { xs: '1.25rem', sm: '1.45rem' }, fontWeight: 900 }}>My Spanish</Typography><Typography sx={{ fontSize: '.8rem', color: 'text.secondary', fontWeight: 800 }}>Validated evidence and the practice the planner has scheduled.</Typography></Box></Box>
    {error && <Alert severity="error" action={<Button color="inherit" size="small" onClick={refresh}>Retry</Button>} sx={{ my: 2 }}>{error}</Alert>}
    <Box sx={{ mt: 2, p: 2, border: '2px solid', borderColor: 'divider', borderRadius: '12px', backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#2E4050' : '#DDF9F6' }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1.5}><Box><Typography sx={{ fontWeight: 900 }}>Due reviews: {due.length}</Typography><Typography sx={{ fontSize: '.78rem', color: 'text.secondary', fontWeight: 800 }}>{due.length ? 'Review is scheduled from validated evidence.' : next ? `Next review: ${formatDate(next.due_at)}` : 'No reviews due right now'}</Typography></Box><RotateCcw size={24} aria-hidden="true" /></Stack>
      {due.length > 0 && <Stack spacing={1.25} sx={{ mt: 1.75 }}>{due.map((item) => <Box key={item.review_id} sx={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 1, pt: 1.25, borderTop: '1px solid', borderColor: 'divider' }}><Box><Typography sx={{ fontWeight: 900, fontSize: '.9rem' }}>{item.display_name}</Typography><Typography sx={{ fontSize: '.75rem', color: 'text.secondary', fontWeight: 800 }}>{item.rationale} · due {formatDate(item.due_at)}</Typography></Box><Button variant="contained" size="small" onClick={() => begin(item)} disabled={Boolean(starting)} startIcon={starting === item.review_id ? <CircularProgress size={14} /> : <Sparkles size={15} />}>{starting === item.review_id ? 'Starting…' : 'Start review'}</Button></Box>)}</Stack>}
    </Box>
    <Typography component="h3" sx={{ mt: 3, mb: 1.5, fontWeight: 900 }}>Skill evidence</Typography>
    <Typography sx={{ mb: 1.5, fontSize: '.78rem', color: 'text.secondary', fontWeight: 800 }}>Course completion above tracks lessons. These cards only describe available validated skill evidence.</Typography>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(3, minmax(0, 1fr))' }, gap: 2 }}>{reviewedState.map((skill) => <SkillCard key={skill.skill_id} skill={skill} />)}</Box>
    <ReviewDialog review={review} attempt={attempt} onClose={() => { setReview(null); setAttempt(null); setResult(null); setSubmitError(''); }} onSubmit={sendAnswer} submitting={submitting} result={result} error={submitError} />
  </Box>;
};

export default MySpanishPanel;
