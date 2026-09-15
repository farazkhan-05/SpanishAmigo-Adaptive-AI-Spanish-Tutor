import { authFetch } from './authFetch';
import { throwApiError } from './apiError';

async function adaptiveRequest(user, path, options, fallbackMessage) {
  const response = await authFetch(path, { user, ...options });
  await throwApiError(response, fallbackMessage);
  return response.json();
}

export const getAdaptiveState = (user) => adaptiveRequest(
  user, '/adaptive/state', { method: 'GET' }, 'Unable to load your Spanish profile.'
);

export const getDueReviews = (user) => adaptiveRequest(
  user, '/adaptive/reviews/due', { method: 'GET' }, 'Unable to load due reviews.'
);

export const getNextReview = (user) => adaptiveRequest(
  user, '/adaptive/reviews/next', { method: 'GET' }, 'Unable to load the next review.'
);

export const startReview = (user, reviewId) => adaptiveRequest(
  user, `/adaptive/reviews/${encodeURIComponent(reviewId)}/start`, { method: 'POST' }, 'Unable to start this review.'
);

// The API intentionally permits only the server-issued attempt ID and the learner's answer.
export const submitReview = (user, reviewId, attemptId, learnerAnswer) => adaptiveRequest(
  user,
  `/adaptive/reviews/${encodeURIComponent(reviewId)}/submit`,
  { method: 'POST', body: { attempt_id: attemptId, learner_answer: learnerAnswer } },
  'Unable to submit this review.'
);
