import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, TextField, Typography, Paper, CircularProgress, Fade } from '@mui/material';
import { Bot, X, Send, User, Mic, Volume2, VolumeX, Menu, Plus, Trash2, Edit3, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useAuth } from '../../context/AuthContext';
import { authFetch } from '../../api/authFetch';
import { normalizeApiError, throwApiError } from '../../api/apiError';
import { getTargetedPracticeRecommendation, startTargetedPractice, submitTargetedPractice } from '../../api/adaptive';

const GlobalChatbot = ({ darkMode, onToggleTheme }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [recommendation, setRecommendation] = useState(null);
  const [practiceAttempt, setPracticeAttempt] = useState(null);
  const [practiceAnswer, setPracticeAnswer] = useState('');
  const [practiceResult, setPracticeResult] = useState(null);
  const [practiceError, setPracticeError] = useState('');
  const [practiceLoading, setPracticeLoading] = useState(false);
  const [practiceSubmitting, setPracticeSubmitting] = useState(false);

  // Multi-session State
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);

  const messagesEndRef = useRef(null);
  const spanishVoicesRef = useRef([]);
  const previousUidRef = useRef(null);
  const previousIsAnonymousRef = useRef(null);
  const activeSessionIdRef = useRef(null);
  const isSendingRef = useRef(false);

  // Fetch real-time context
  const { user, isAnonymous, openSignInPrompt } = useAuth();

  const bindActiveSessionId = useCallback((sessionId) => {
    activeSessionIdRef.current = sessionId;
    setActiveSessionId(sessionId);
  }, []);

  // Text-to-Speech (TTS)
  useEffect(() => {
    if (!window.speechSynthesis) return undefined;

    const synth = window.speechSynthesis;
    const previousOnVoicesChanged = synth.onvoiceschanged;

    const loadSpanishVoices = () => {
      spanishVoicesRef.current = synth
        .getVoices()
        .filter(v => v.lang.startsWith('es-') || v.name.includes('Spanish'));
    };

    const handleVoicesChanged = (event) => {
      if (typeof previousOnVoicesChanged === 'function') {
        previousOnVoicesChanged.call(synth, event);
      }
      loadSpanishVoices();
    };

    loadSpanishVoices();
    synth.onvoiceschanged = handleVoicesChanged;

    return () => {
      if (synth.onvoiceschanged === handleVoicesChanged) {
        synth.onvoiceschanged = previousOnVoicesChanged;
      }
    };
  }, []);

  const speakText = (text) => {
    if (!window.speechSynthesis || isMuted) return;

    window.speechSynthesis.cancel();
    // Remove markdown + emojis/symbol pictographs so TTS reads only meaningful words.
    const cleanText = text
      .replace(/[*_#`]/g, '')
      .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!cleanText) return;
    const utterance = new SpeechSynthesisUtterance(cleanText);
    const spanishVoice = spanishVoicesRef.current[0]
      || window.speechSynthesis.getVoices().find(v => v.lang.startsWith('es-') || v.name.includes('Spanish'));
    if (spanishVoice) {
      utterance.voice = spanishVoice;
    } else {
      utterance.lang = 'es-ES';
    }
    window.speechSynthesis.speak(utterance);
  };

  // Hide the flag from the UI without changing the model's actual response.
  const sanitizeDisplayText = (text) => text.replace(/🇪🇸/g, '').replace(/\s+/g, ' ').trim();

  // Speech-to-Text (STT)
  const handleListen = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Your browser does not support voice input.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'es-ES';
    recognition.interimResults = false;

    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setInputText(prev => prev ? `${prev} ${transcript}` : transcript);
    };
    recognition.onerror = (event) => {
      console.error("Speech error:", event.error);
      setIsListening(false);
    };
    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  // Auto-scroll
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isOpen, isLoading]);

  // Fetch all user chat sessions
  const fetchSessions = useCallback(async () => {
    if (!user) return [];
    try {
      const response = await authFetch('/chat/sessions', {
        user
      });
      await throwApiError(response, "Failed to load sessions");
      const data = await response.json();
      setSessions(data);
      return data;
    } catch (error) {
      console.error("Error fetching chat sessions:", error);
      return [];
    }
  }, [user]);

  // Load history for a specific session
  const loadSessionHistory = async (sessionId) => {
    setIsHistoryLoading(true);
    setMessages([]); // Instant wipe to prevent previous conversation leak
    setIsLoading(false); // Stop any active typing loader
    try {
      const response = await authFetch(`/chat/history/session/${sessionId}`, {
        user
      });
      await throwApiError(response, "Failed to load session history");
      const history = await response.json();
      setMessages(history);
    } catch (error) {
      console.error("Error loading session history:", error);
      setMessages([{
        role: 'model',
        text: "¡Lo siento! I'm having trouble loading this conversation. 🔌"
      }]);
    } finally {
      setIsHistoryLoading(false);
    }
  };

  // Create a brand new chat (reset state)
  const handleStartNewChat = useCallback(() => {
    bindActiveSessionId(null);
    setIsLoading(false); // Reset active response spinner
    setMessages([]);
    setIsDrawerOpen(false);
  }, [bindActiveSessionId]);

  const resetChatForCurrentUser = useCallback((reason = "identity-switch") => {
    setSessions([]);
    bindActiveSessionId(null);
    setMessages([]);
    setRecommendation(null);
    setPracticeAttempt(null);
    setPracticeResult(null);
    setPracticeError('');
    setIsLoading(false);
    setIsHistoryLoading(false);
    setIsDrawerOpen(false);
    setEditingSessionId(null);
    setEditingTitle('');
    if (reason === "identity-switch" || reason === "auth-upgrade") {
      handleStartNewChat();
    }
  }, [bindActiveSessionId, handleStartNewChat]);

  // Delete a session
  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this conversation?")) return;

    try {
      const response = await authFetch(`/chat/sessions/${sessionId}`, {
        method: 'DELETE',
        user
      });
      await throwApiError(response, "Failed to delete session");

      const updated = sessions.filter(s => s.id !== sessionId);
      setSessions(updated);

      if (activeSessionId === sessionId) {
        if (updated.length > 0) {
          bindActiveSessionId(updated[0].id);
          loadSessionHistory(updated[0].id);
        } else {
          handleStartNewChat();
        }
      }
    } catch (error) {
      console.error("Error deleting session:", error);
      alert("Failed to delete the session. Please try again.");
    }
  };

  // Rename a session
  const handleRenameSession = async (sessionId, newTitle, e) => {
    e.stopPropagation();
    if (!newTitle.trim()) return;
    try {
      const response = await authFetch(`/chat/sessions/${sessionId}`, {
        method: 'PUT',
        user,
        body: { title: newTitle }
      });
      await throwApiError(response, "Failed to rename session");

      const updatedSession = await response.json();
      setSessions(prev => prev.map(s => s.id === sessionId ? updatedSession : s));
      setEditingSessionId(null);
    } catch (error) {
      console.error("Error renaming session:", error);
      alert("Failed to rename the session.");
    }
  };

  // Load sessions when widget is opened, but default to a brand new conversation on initial load
  useEffect(() => {
    if (isOpen && user) {
      // If we don't have an active session yet (initial reload/open), start fresh immediately (0ms wait)
      if (!activeSessionId) {
        handleStartNewChat();
      }
      // Quietly populate the drawer's session history in the background without blocking the UI
      fetchSessions();
    }
  }, [activeSessionId, fetchSessions, handleStartNewChat, isOpen, user]);

  // Treat auth identity changes as a hard chat-session boundary.
  useEffect(() => {
    const currentUid = user?.uid || null;
    const previousUid = previousUidRef.current;

    if (previousUid && currentUid && previousUid !== currentUid) {
      resetChatForCurrentUser("identity-switch");
      if (isOpen) {
        fetchSessions();
      }
    }

    previousUidRef.current = currentUid;
  }, [fetchSessions, isOpen, resetChatForCurrentUser, user]);

  // Also reset when guest account is upgraded to a permanent account.
  useEffect(() => {
    const previousIsAnonymous = previousIsAnonymousRef.current;
    if (previousIsAnonymous === true && isAnonymous === false) {
      resetChatForCurrentUser("auth-upgrade");
      if (isOpen) {
        fetchSessions();
      }
    }
    previousIsAnonymousRef.current = isAnonymous;
  }, [fetchSessions, isAnonymous, isOpen, resetChatForCurrentUser]);

  const handleSelectSession = (sessionId) => {
    bindActiveSessionId(sessionId);
    loadSessionHistory(sessionId);
    setIsDrawerOpen(false);
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!inputText.trim() || isLoading || isSendingRef.current) return;

    const userMessage = inputText.trim();
    setRecommendation(null);
    setPracticeError('');
    isSendingRef.current = true;
    setIsLoading(true);
    setInputText('');
    setMessages(prev => [...prev, { role: 'user', text: userMessage }]);

    try {
      const userName = user?.displayName || user?.email?.split('@')[0] || "Amigo";
      const requestPayload = {
        user_id: user.uid,
        message: userMessage,
        user_name: userName,
        session_id: activeSessionIdRef.current
      };

      const sendRequest = async ({ bodyOverride = {}, forceRefreshToken = false } = {}) => authFetch('/chat/send_stream', {
        method: 'POST',
        user,
        forceRefreshToken,
        body: {
          ...requestPayload,
          ...bodyOverride
        }
      });
      let response = await sendRequest();

      // If sign-in just completed, retry once with a forced fresh token.
      if (response.status === 403 && !isAnonymous) {
        response = await sendRequest({
          forceRefreshToken: true
        });
      }

      if (response.status === 403) {
        const apiError = await normalizeApiError(response, "Access denied. Please sign in again.");
        let backendMessage = apiError.message;
        const detailCode = apiError.code;

        const isInvalidSession = backendMessage.includes("Invalid session ID") || detailCode === "SESSION_OWNERSHIP_MISMATCH";
        if (!isAnonymous && isInvalidSession) {
          bindActiveSessionId(null);
          const recoveredResponse = await sendRequest({
            bodyOverride: { session_id: null },
            forceRefreshToken: true
          });
          if (recoveredResponse.ok) {
            response = recoveredResponse;
          } else {
            backendMessage = "Your previous session belonged to a different account. Started a new conversation. Please send your message again.";
            setMessages(prev => [
              ...prev,
              {
                role: 'model',
                text: backendMessage
              }
            ]);
            return;
          }
        }

        if (response.status === 403) {
          if (isAnonymous) {
            openSignInPrompt('chat-limit');
            setMessages(prev => [
              ...prev,
              {
                role: 'model',
                text: "You've used your 3 free Lumi chat messages. Sign in with Google to keep chatting and save your progress."
              }
            ]);
          } else {
            setMessages(prev => [
              ...prev,
              {
                role: 'model',
                text: backendMessage || "Your sign-in just finished. Please try one more message now."
              }
            ]);
          }
          return;
        }
      }

      await throwApiError(response, "Backend chat service error");

      // Set up response body reader for SSE processing
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let finished = false;
      let accumulatedReply = '';
      let buffer = '';
      let hasAppendedModelPlaceholder = false;

      while (!finished) {
        const { value, done } = await reader.read();
        finished = done;
        if (value) {
          const chunkStr = decoder.decode(value, { stream: !done });
          buffer += chunkStr;

          const events = buffer.split(/\r?\n\r?\n/);
          buffer = events.pop() || '';

          for (const event of events) {
            const dataStr = event
              .split(/\r?\n/)
              .map(line => line.trim())
              .filter(line => line.startsWith('data: '))
              .map(line => line.slice(6))
              .join('\n');

            if (!dataStr) continue;
            if (dataStr === '[DONE]') {
              finished = true;
              buffer = '';
              break;
            }

            try {
              const parsed = JSON.parse(dataStr);

              // 1. Dynamic Session ID Sync
              if (parsed.session_id && parsed.session_id !== activeSessionIdRef.current) {
                bindActiveSessionId(parsed.session_id);
                fetchSessions();
              }

              // 2. Theme Toggle Action Trigger
              if (parsed.action_required === "TOGGLE_THEME" && typeof onToggleTheme === "function") {
                onToggleTheme();
              }

              // 3. Process Text Token Chunks
              if (parsed.token) {
                accumulatedReply += parsed.token;

                if (!hasAppendedModelPlaceholder) {
                  // Append placeholder model bubble
                  setMessages(prev => [...prev, { role: 'model', text: accumulatedReply }]);
                  hasAppendedModelPlaceholder = true;
                } else {
                  // Stream update last model bubble text
                  setMessages(prev => {
                    const updated = [...prev];
                    if (updated.length > 0) {
                      updated[updated.length - 1] = {
                        role: 'model',
                        text: accumulatedReply
                      };
                    }
                    return updated;
                  });
                }
              }
            } catch {
              buffer = `${event}\n\n${buffer}`;
              break;
            }
          }
        }
      }
      // Intentionally do not auto-speak on reply.
      // Speech should only play when user taps the sound icon on a message.
      if (activeSessionIdRef.current && !isAnonymous) {
        try {
          const nextRecommendation = await getTargetedPracticeRecommendation(user, activeSessionIdRef.current);
          setRecommendation(nextRecommendation.available ? nextRecommendation : null);
        } catch (recommendationError) {
          console.error("Targeted practice recommendation error:", recommendationError);
          setRecommendation(null);
          setPracticeError('We could not check for a follow-up practice activity.');
        }
      }
    } catch (error) {
      console.error("Chat sending error:", error);
      setMessages(prev => [...prev, { role: 'model', text: "Lo siento, I am having trouble reaching my server right now. 🔌" }]);
    } finally {
      isSendingRef.current = false;
      setIsLoading(false);
    }
  };

  const handleStartPractice = async () => {
    if (!recommendation || practiceLoading) return;
    setPracticeLoading(true);
    setPracticeError('');
    try {
      const started = await startTargetedPractice(user, recommendation.source_event_id);
      setPracticeAttempt(started);
      setPracticeAnswer('');
      setPracticeResult(null);
      setRecommendation(null);
    } catch (error) {
      setPracticeError(error.message || 'This practice activity is no longer available.');
    } finally {
      setPracticeLoading(false);
    }
  };

  const handleSubmitPractice = async (answer) => {
    if (!practiceAttempt || practiceSubmitting) return;
    setPracticeSubmitting(true);
    setPracticeError('');
    try {
      const result = await submitTargetedPractice(user, practiceAttempt.attempt_id, answer);
      setPracticeResult(result);
      if (result.mastery_updated) {
        window.dispatchEvent(new CustomEvent('spanish-amigo:adaptive-updated'));
      }
    } catch (error) {
      setPracticeError(error.message || 'We could not record that answer. Please try again.');
    } finally {
      setPracticeSubmitting(false);
    }
  };

  return (
    <>
      {/* Floating Action Button */}
      <Box sx={{ position: 'fixed', bottom: { xs: 16, md: 24 }, right: { xs: 16, md: 24 }, zIndex: 1000 }}>
        {!isOpen && (
          <IconButton
            onClick={() => setIsOpen(true)}
            sx={{
              background: '#4ECDC4',
              color: '#1A1A1A',
              width: { xs: 52, md: 56 },
              height: { xs: 52, md: 56 },
              border: '3px solid #1A1A1A',
              boxShadow: '4px 4px 0px #1A1A1A',
              borderRadius: '14px',
              transition: 'all 0.15s ease',
              '&:hover': {
                background: '#5FE0D8',
                transform: 'translate(-2px, -2px)',
                boxShadow: '6px 6px 0px #1A1A1A',
              },
              '&:active': {
                transform: 'translate(4px, 4px)',
                boxShadow: '0px 0px 0px #1A1A1A',
              },
            }}
          >
            <Bot size={26} />
          </IconButton>
        )}
      </Box>

      {/* Chat Window */}
      <Fade in={isOpen}>
        <Paper
          elevation={0}
          sx={{
            position: 'fixed',
            top: { xs: '56px', sm: 'auto' },
            bottom: { xs: 0, sm: 24 },
            right: { xs: 0, sm: 24 },
            left: { xs: 0, sm: 'auto' },
            width: { xs: '100%', sm: 360 },
            height: { xs: 'auto', sm: 520 },
            maxHeight: { xs: 'none', sm: 'calc(100vh - 48px)' },
            display: isOpen ? 'flex' : 'none',
            flexDirection: 'column',
            zIndex: 1000,
            borderRadius: { xs: 0, sm: '16px' },
            overflow: 'hidden',
            background: darkMode ? '#252542' : '#FFFDF2',
            border: { xs: 'none', sm: `3px solid ${darkMode ? '#555' : '#1A1A1A'}` },
            boxShadow: { xs: 'none', sm: `6px 6px 0px ${darkMode ? '#000' : '#1A1A1A'}` },
          }}
        >

          {/* Header */}
          <Box
            sx={{
              background: '#4ECDC4',
              p: 1.5,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              color: '#1A1A1A',
              borderBottom: `3px solid ${darkMode ? '#555' : '#1A1A1A'}`,
              flexShrink: 0,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <IconButton
                onClick={() => setIsDrawerOpen(!isDrawerOpen)}
                size="small"
                sx={{
                  color: '#1A1A1A',
                  background: isDrawerOpen ? '#FF6B6B' : 'transparent',
                  border: isDrawerOpen ? '2px solid #1A1A1A' : 'none',
                  borderRadius: '6px',
                  p: 0.5,
                  mr: 0.5,
                  '&:hover': {
                    background: '#FF8787'
                  }
                }}
              >
                <Menu size={18} />
              </IconButton>
              <Box sx={{ background: '#FFFFFF', p: 0.7, borderRadius: '8px', border: `2px solid #1A1A1A`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Bot size={20} />
              </Box>
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 900, lineHeight: 1.2, fontSize: '0.9rem' }}>Lumi</Typography>
                <Typography variant="caption" sx={{ opacity: 0.8, fontSize: '0.65rem', fontWeight: 700 }}>Your language buddy</Typography>
              </Box>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <IconButton onClick={() => setIsMuted(!isMuted)} size="small" sx={{ color: '#1A1A1A', mr: 0.5 }}>
                {isMuted ? <VolumeX size={16} /> : <Volume2 size={16} />}
              </IconButton>
              <IconButton
                onClick={() => setIsOpen(false)}
                sx={{
                  color: '#1A1A1A',
                  width: { xs: 36, sm: 28 },
                  height: { xs: 36, sm: 28 },
                }}
              >
                <X size={20} />
              </IconButton>
            </Box>
          </Box>

          <Box sx={{ flex: 1, minHeight: 0, position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

            {/* Slide-out History Drawer */}
            <Box
              sx={{
                position: 'absolute',
                top: 0,
                left: 0,
                bottom: 0,
                width: '100%',
                zIndex: 10,
                background: darkMode ? '#1A1A2E' : '#FFFDF2',
                borderRight: isDrawerOpen ? `3px solid ${darkMode ? '#555' : '#1A1A1A'}` : 'none',
                transform: isDrawerOpen ? 'translateX(0)' : 'translateX(-100%)',
                transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden'
              }}
            >
              <Box sx={{ p: 1.5, borderBottom: `3px solid ${darkMode ? '#555' : '#1A1A1A'}`, background: darkMode ? '#252542' : '#FFE66D', flexShrink: 0 }}>
                <button
                  onClick={handleStartNewChat}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    background: '#FF6B6B',
                    color: '#FFFFFF',
                    fontWeight: '900',
                    fontSize: '0.8rem',
                    border: '3px solid #1A1A1A',
                    boxShadow: '3px 3px 0px #1A1A1A',
                    borderRadius: '10px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    transition: 'all 0.1s ease',
                  }}
                  onMouseDown={(e) => {
                    e.currentTarget.style.transform = 'translate(2px, 2px)';
                    e.currentTarget.style.boxShadow = '1px 1px 0px #1A1A1A';
                  }}
                  onMouseUp={(e) => {
                    e.currentTarget.style.transform = 'none';
                    e.currentTarget.style.boxShadow = '3px 3px 0px #1A1A1A';
                  }}
                >
                  <Plus size={16} /> New conversation
                </button>
              </Box>

              <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto', p: 1.5, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                {sessions.length === 0 ? (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="caption" sx={{ color: darkMode ? '#888' : '#666', fontWeight: 700 }}>
                      No conversations yet.
                    </Typography>
                  </Box>
                ) : (
                  sessions.map((sess) => {
                    const isActive = sess.id === activeSessionId;
                    const isEditing = sess.id === editingSessionId;

                    return (
                      <Box
                        key={sess.id}
                        onClick={() => !isEditing && handleSelectSession(sess.id)}
                        sx={{
                          p: 1.2,
                          borderRadius: '10px',
                          cursor: isEditing ? 'default' : 'pointer',
                          background: isActive ? '#4ECDC4' : (darkMode ? '#252542' : '#FFFFFF'),
                          color: '#1A1A1A',
                          border: `2px solid ${darkMode ? '#555' : '#1A1A1A'}`,
                          boxShadow: isActive ? 'none' : `3px 3px 0px ${darkMode ? '#000' : '#1A1A1A'}`,
                          transform: isActive ? 'translate(2px, 2px)' : 'none',
                          transition: 'all 0.15s ease',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 1,
                          '&:hover': {
                            background: isActive ? '#4ECDC4' : '#FF8787',
                            transform: 'translate(-1px, -1px)',
                            boxShadow: isActive ? 'none' : `4px 4px 0px ${darkMode ? '#000' : '#1A1A1A'}`,
                          }
                        }}
                      >
                        {isEditing ? (
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, width: '100%' }} onClick={(e) => e.stopPropagation()}>
                            <input
                              type="text"
                              value={editingTitle}
                              onChange={(e) => setEditingTitle(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleRenameSession(sess.id, editingTitle, e);
                                if (e.key === 'Escape') setEditingSessionId(null);
                              }}
                              autoFocus
                              style={{
                                width: '100%',
                                padding: '3px 6px',
                                borderRadius: '6px',
                                border: '2px solid #1A1A1A',
                                fontSize: '0.75rem',
                                fontWeight: '700',
                                background: '#FFF'
                              }}
                            />
                            <IconButton onClick={(e) => handleRenameSession(sess.id, editingTitle, e)} size="small" sx={{ p: 0.5, color: '#1A1A1A' }}>
                              <Check size={14} />
                            </IconButton>
                            <IconButton onClick={() => setEditingSessionId(null)} size="small" sx={{ p: 0.5, color: '#1A1A1A' }}>
                              <X size={14} />
                            </IconButton>
                          </Box>
                        ) : (
                          <>
                            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.2, overflow: 'hidden', width: '75%' }}>
                              <Typography variant="body2" sx={{ fontWeight: 900, fontSize: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: isActive ? '#1A1A1A' : (darkMode ? '#F8FAFC' : '#1A1A1A') }}>
                                {sess.title}
                              </Typography>
                              <Typography variant="caption" sx={{ fontSize: '0.6rem', opacity: 0.7, fontWeight: 700, color: isActive ? '#1A1A1A' : (darkMode ? '#CBD5E1' : '#666') }}>
                                {new Date(sess.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                              </Typography>
                            </Box>
                            <Box sx={{ display: 'flex', gap: 0.2 }}>
                              <IconButton
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingSessionId(sess.id);
                                  setEditingTitle(sess.title);
                                }}
                                size="small"
                                sx={{
                                  p: 0.4,
                                  color: isActive ? '#1A1A1A' : (darkMode ? '#F8FAFC' : '#1A1A1A'),
                                  '&:hover': { background: 'rgba(0,0,0,0.1)' }
                                }}
                              >
                                <Edit3 size={12} />
                              </IconButton>
                              <IconButton
                                onClick={(e) => handleDeleteSession(sess.id, e)}
                                size="small"
                                sx={{
                                  p: 0.4,
                                  color: isActive ? '#1A1A1A' : (darkMode ? '#F8FAFC' : '#1A1A1A'),
                                  '&:hover': { background: 'rgba(0,0,0,0.1)', color: '#FF6B6B' }
                                }}
                              >
                                <Trash2 size={12} />
                              </IconButton>
                            </Box>
                          </>
                        )}
                      </Box>
                    );
                  })
                )}
              </Box>
            </Box>

            {/* Messages Area */}
            <Box sx={{ flex: 1, minHeight: 0, p: 1.5, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 1.5, backgroundColor: darkMode ? '#1A1A2E' : '#FFFDF2' }}>
              {isHistoryLoading ? (
                <Box sx={{ display: 'flex', flex: 1, flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 1.5 }}>
                  <CircularProgress size={28} sx={{ color: '#4ECDC4' }} />
                  <Typography variant="caption" sx={{ fontWeight: 800, color: darkMode ? '#888' : '#666' }}>
                    Loading conversation...
                  </Typography>
                </Box>
              ) : messages.length === 0 ? (
                <Box sx={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', height: '100%', p: 2, textAlign: 'center' }}>
                  <Typography variant="body2" sx={{ color: darkMode ? '#8E8EA8' : '#718096', fontSize: '0.85rem' }}>
                    Ask Lumi anything about Spanish.
                  </Typography>
                </Box>
              ) : (
                <>
                  {messages.map((msg, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        display: 'flex',
                        justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        gap: 1
                      }}
                    >
                      {msg.role === 'model' && (
                        <Box sx={{ width: 28, height: 28, borderRadius: '8px', background: '#4ECDC4', border: '2px solid #1A1A1A', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#1A1A1A', flexShrink: 0 }}>
                          <Bot size={14} />
                        </Box>
                      )}
                      <Box
                        sx={{
                          maxWidth: '82%',
                          p: 1.5,
                          borderRadius: '10px',
                          background: msg.role === 'user' ? '#FF6B6B' : (darkMode ? '#3A3A5C' : '#FFFFFF'),
                          color: msg.role === 'user' ? '#FFFFFF' : (darkMode ? '#F8FAFC' : '#1A1A1A'),
                          border: `2px solid ${darkMode ? '#555' : '#1A1A1A'}`,
                          boxShadow: `2px 2px 0px ${darkMode ? '#000' : '#1A1A1A'}`,
                          typography: 'body2',
                          lineHeight: 1.5,
                          fontSize: '0.8rem',
                          '& p': { m: 0, mb: 0.5, '&:last-child': { mb: 0 } },
                          '& ul, & ol': { m: 0, pl: 2, mb: 0.5 },
                          '& li': { mb: 0.25 },
                          '& strong': { fontWeight: 800, color: msg.role === 'user' ? 'white' : (darkMode ? '#FFE66D' : '#1A1A1A') }
                        }}
                      >
                        {msg.role === 'model' ? (
                          <Box sx={{ position: 'relative', pr: 3 }}>
                            <ReactMarkdown>{sanitizeDisplayText(msg.text)}</ReactMarkdown>
                            <IconButton
                              onClick={() => speakText(sanitizeDisplayText(msg.text))}
                              size="small"
                              sx={{ position: 'absolute', top: -8, right: -16, color: '#A0AEC0', '&:hover': { color: '#6C63FF' } }}
                            >
                              <Volume2 size={16} />
                            </IconButton>
                          </Box>
                        ) : (
                          <Box sx={{ whiteSpace: 'pre-wrap' }}>{msg.text}</Box>
                        )}
                      </Box>
                      {msg.role === 'model' && idx === messages.length - 1 && recommendation && (
                        <Box sx={{ maxWidth: '82%', alignSelf: 'flex-start', mt: -0.5 }}>
                          <Typography sx={{ fontSize: '0.72rem', color: 'text.secondary', fontWeight: 800, mb: 0.5 }}>
                            {recommendation.display_name}
                          </Typography>
                          <Button
                            variant="contained"
                            size="small"
                            onClick={handleStartPractice}
                            disabled={practiceLoading}
                            startIcon={practiceLoading ? <CircularProgress size={13} color="inherit" /> : <Sparkles size={14} />}
                            sx={{ background: '#6C63FF', color: '#fff', fontWeight: 900, border: '2px solid #1A1A1A', boxShadow: '2px 2px 0 #1A1A1A' }}
                          >
                            {practiceLoading ? 'Preparing…' : 'Practice this skill'}
                          </Button>
                          <Typography sx={{ mt: 0.6, fontSize: '0.72rem', color: 'text.secondary', lineHeight: 1.35 }}>
                            {recommendation.reason}
                          </Typography>
                        </Box>
                      )}
                      {msg.role === 'user' && (
                        <Box sx={{ width: 28, height: 28, borderRadius: '8px', background: darkMode ? '#3A3A5C' : '#FFE66D', border: `2px solid ${darkMode ? '#555' : '#1A1A1A'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#1A1A1A', flexShrink: 0 }}>
                          <User size={14} />
                        </Box>
                      )}
                    </Box>
                  ))}
                  {isLoading && messages[messages.length - 1]?.role === 'user' && (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ width: 28, height: 28, borderRadius: '8px', background: '#4ECDC4', border: '2px solid #1A1A1A', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#1A1A1A', flexShrink: 0 }}>
                        <Bot size={14} />
                      </Box>
                      <Box sx={{ p: 1.5, borderRadius: '10px', background: darkMode ? '#3A3A5C' : '#FFFFFF', border: `2px solid ${darkMode ? '#555' : '#1A1A1A'}`, boxShadow: `2px 2px 0px ${darkMode ? '#000' : '#1A1A1A'}` }}>
                        <CircularProgress size={14} sx={{ color: '#4ECDC4' }} />
                      </Box>
                    </Box>
                  )}
                  <div ref={messagesEndRef} />
                </>
              )}
            </Box>

            {practiceError && !practiceAttempt && (
              <Alert severity="info" onClose={() => setPracticeError('')} sx={{ mx: 1.5, mb: 1, borderRadius: '10px', flexShrink: 0 }}>
                {practiceError}
              </Alert>
            )}

            {/* Input Area */}
            <Box
              component="form"
              onSubmit={handleSend}
              sx={{
                p: 1.5,
                pb: {
                  xs: 'calc(12px + env(safe-area-inset-bottom, 0px))',
                  sm: 1.5,
                },
                background: darkMode ? '#252542' : '#FFE66D',
                borderTop: `3px solid ${darkMode ? '#555' : '#1A1A1A'}`,
                display: 'flex',
                gap: 1,
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              <IconButton
                onClick={handleListen}
                disabled={isLoading || isListening}
                size="small"
                sx={{
                  color: isListening ? '#FF6B6B' : (darkMode ? '#FFFFFF' : '#1A1A1A'),
                  backgroundColor: isListening ? 'rgba(255, 107, 107, 0.15)' : 'transparent',
                  animation: isListening ? 'pulse 1.5s infinite' : 'none',
                  flexShrink: 0,
                  '@keyframes pulse': {
                    '0%': { transform: 'scale(1)', boxShadow: '0 0 0 0 rgba(255, 107, 107, 0.7)' },
                    '70%': { transform: 'scale(1.1)', boxShadow: '0 0 0 8px rgba(255, 107, 107, 0)' },
                    '100%': { transform: 'scale(1)', boxShadow: '0 0 0 0 rgba(255, 107, 107, 0)' }
                  }
                }}
              >
                <Mic size={18} />
              </IconButton>
              <TextField
                fullWidth
                size="small"
                placeholder="Message Lumi..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                disabled={isLoading}
                sx={{
                  '& .MuiOutlinedInput-root': {
                    borderRadius: '10px',
                    backgroundColor: darkMode ? '#1A1A2E' : '#FFFFFF',
                    color: darkMode ? '#F8FAFC' : '#1A1A1A',
                    fontSize: '0.85rem',
                    '& fieldset': { border: `2px solid ${darkMode ? '#555' : '#1A1A1A'}` },
                  },
                  '& input': {
                    color: darkMode ? '#F8FAFC' : '#1A1A1A',
                    py: 1,
                  }
                }}
              />
              <IconButton
                type="submit"
                disabled={!inputText.trim() || isLoading}
                sx={{
                  background: '#FF6B6B',
                  color: '#FFFFFF',
                  border: '2px solid #1A1A1A',
                  boxShadow: '2px 2px 0px #1A1A1A',
                  borderRadius: '10px',
                  minWidth: '36px',
                  height: '36px',
                  flexShrink: 0,
                  transition: 'all 0.15s ease',
                  '&:hover': { background: '#FF8787', transform: 'translate(-1px, -1px)', boxShadow: '3px 3px 0px #1A1A1A' },
                  '&:active': { transform: 'translate(2px, 2px)', boxShadow: '0px 0px 0px #1A1A1A' },
                  '&:disabled': { background: '#D1D5DB', color: '#9CA3AF', border: '2px solid #9CA3AF', boxShadow: 'none' }
                }}
              >
                <Send size={16} />
              </IconButton>
            </Box>
          </Box>
        </Paper>
      </Fade>
      <Dialog
        open={Boolean(practiceAttempt)}
        onClose={practiceSubmitting ? undefined : () => { setPracticeAttempt(null); setPracticeResult(null); setPracticeError(''); }}
        fullWidth
        maxWidth="sm"
        aria-labelledby="targeted-practice-title"
      >
        <DialogTitle id="targeted-practice-title" sx={{ fontWeight: 900 }}>
          Practice: {practiceAttempt?.display_name}
        </DialogTitle>
        <DialogContent>
          <Typography sx={{ fontWeight: 900, whiteSpace: 'pre-wrap', lineHeight: 1.5, mb: 2 }}>
            {practiceAttempt?.exercise_text}
          </Typography>
          <TextField
            fullWidth
            multiline
            minRows={3}
            label="Your answer"
            placeholder="Write your answer in Spanish"
            disabled={practiceSubmitting || Boolean(practiceResult)}
            value={practiceAnswer}
            onChange={(event) => setPracticeAnswer(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && practiceAnswer.trim()) {
                event.preventDefault();
                handleSubmitPractice(practiceAnswer.trim());
              }
            }}
            inputProps={{ maxLength: 2000 }}
            helperText="Your answer is assessed by Lumi and recorded only if it passes the learning checks."
          />
          {practiceError && <Alert severity="error" sx={{ mt: 2, borderRadius: '10px' }}>{practiceError}</Alert>}
          {practiceResult && (
            <Alert severity={practiceResult.status === 'accepted' ? 'success' : 'info'} sx={{ mt: 2, borderRadius: '10px' }}>
              {practiceResult.status === 'accepted'
                ? practiceResult.result === 'correct'
                  ? 'Correct — your practice was recorded and your skill profile was updated.'
                  : 'Your answer needs more practice, and the result was recorded.'
                : 'Your answer was not accepted for a learning update, so your skill profile was not changed.'}
              {practiceResult.due_at && ` Next review: ${new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(practiceResult.due_at))}.`}
            </Alert>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2.5, pt: 1 }}>
          <Button onClick={() => { setPracticeAttempt(null); setPracticeResult(null); setPracticeError(''); }} disabled={practiceSubmitting}>
            {practiceResult ? 'Close' : 'Cancel'}
          </Button>
          {!practiceResult && (
            <Button
              variant="contained"
              disabled={practiceSubmitting}
              onClick={() => practiceAnswer.trim() && handleSubmitPractice(practiceAnswer.trim())}
              sx={{ background: '#FF6B6B', color: '#fff' }}
            >
              {practiceSubmitting ? 'Checking…' : 'Submit answer'}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
};

export default GlobalChatbot;


