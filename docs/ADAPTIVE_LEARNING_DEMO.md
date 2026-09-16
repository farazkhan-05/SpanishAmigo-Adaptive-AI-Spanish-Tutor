# SpanishAmigo adaptive-learning demo

Use a fresh authenticated test learner so the learner's own chat session and learning state are easy to follow.

1. Open Lumi and make a supported taught grammar mistake in a Spanish sentence.
2. Observe Lumi's correction. If the server marks the turn eligible, choose **Practice this skill** and read the server-issued exercise.
3. Submit a new Spanish answer in the targeted-practice dialog.
4. Observe the truthful assessment result. An accepted result updates **My Spanish** automatically; rejected or inconclusive answers do not pretend to update it.
5. Return to **My Spanish** and observe the skill status and practice evidence refresh without a full-page reload.
6. When the response includes a scheduled review, note the learner-friendly **Next review** time.
7. Return when that review becomes due. Review timing is controlled by FSRS and may not become due immediately.
8. Complete the review from the existing **Review now** flow in My Spanish.

Do not manually edit learner mastery, `ReviewItem`, `ReviewHistory`, or `due_at`. The server owns assessment validation, mastery mutation, and FSRS scheduling.

If no practice action appears, the turn was not eligible, the learner is anonymous, or the recommendation has already been used. Try another supported taught grammar mistake in the active session.
