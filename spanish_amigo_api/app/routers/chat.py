import logging
import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, cast

from app.database import get_db, SessionLocal
from app.models import ChatMessage, CompletedLesson, ChatSession, SystemStatus, User
from app.schemas import ChatRequest, ChatResponse, ExplainRequest, ExplainResponse, SessionResponse, SessionUpdate
from app.services.ai import TutorState, tutor_graph, generate_explanation, extract_text_content, generate_chat_title, astream_with_fallback, plan_turn
from app.services.auth import get_current_user
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

logger = logging.getLogger("spanish-amigo-ai")

router = APIRouter(
    prefix="/chat",
    tags=["Chat"]
)

ANONYMOUS_GLOBAL_CHAT_MESSAGE_LIMIT = 3
MAX_HISTORY_CHARS = 4000


def _plan_turn_with_fresh_db(state_input: dict):
    with SessionLocal() as background_db:
        return plan_turn(cast(TutorState, state_input), background_db)


def _save_memory_with_fresh_db(state_input: dict) -> None:
    from app.services.ai import save_memory_node

    with SessionLocal() as background_db:
        save_memory_node(cast(TutorState, state_input), db=background_db)
        background_db.commit()


def _build_history_messages_with_budget(db_history) -> list:
    history_messages: list[BaseMessage] = []
    current_chars = 0

    for msg in db_history:
        content = msg.content or ""
        if current_chars + len(content) > MAX_HISTORY_CHARS:
            break

        if msg.role == "user":
            history_message = HumanMessage(content=content)
        else:
            history_message = AIMessage(content=content)

        history_messages.insert(0, history_message)
        current_chars += len(content)

    return history_messages


def _is_anonymous_firebase_user(current_user: dict) -> bool:
    firebase_claims = current_user.get("firebase") or {}
    return firebase_claims.get("sign_in_provider") == "anonymous"


def _anonymous_chat_usage_key(user_id: str) -> str:
    return f"anonymous_chat_usage:{user_id}"


def _consume_anonymous_global_chat_message(db: Session, user_id: str, current_user: dict) -> None:
    if not _is_anonymous_firebase_user(current_user):
        return

    usage_key = _anonymous_chat_usage_key(user_id)
    usage_row = db.get(SystemStatus, usage_key)
    message_count = int(usage_row.value) if usage_row else 0

    if message_count >= ANONYMOUS_GLOBAL_CHAT_MESSAGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ANONYMOUS_CHAT_LIMIT_REACHED",
                "message": "Anonymous chat limit reached. Sign in with Google to keep chatting with Lumi.",
            },
        )

    if usage_row:
        usage_row.value = str(message_count + 1)
    else:
        db.add(SystemStatus(key=usage_key, value="1"))
    db.commit()

# 1. Fetch previous chat history for a specific session
@router.get("/history/session/{session_id}", response_model=List[dict])
def get_session_history(session_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Chat session not found"
        )
        
    # Enforce strict tenancy: users can only view their own chat history
    if session.user_id != current_user.get("uid"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot access another user's chat history."
        )

    query = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = db.scalars(query).all()
    
    # Map 'assistant' back to React's expected 'model' role, and 'content' to 'text'
    return [
        {
            "role": "model" if msg.role == "assistant" else "user",
            "text": msg.content
        }
        for msg in messages
    ]

# Legacy: Fetch general chat history (fallback to latest active session or all messages)
@router.get("/history/{user_id}", response_model=List[dict])
def get_chat_history(user_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Enforce strict tenancy: users can only view their own chat history
    if current_user.get("uid") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot access another user's chat history."
        )

    # Find the most recently updated session
    session_query = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    latest_session = db.scalars(session_query).first()
    
    if not latest_session:
        return []
        
    return get_session_history(latest_session.id, db, current_user)

# 2. Send a new message to the AI Spanish tutor
def update_session_title_in_background(session_id: int, first_message: str):
    """Asynchronously generates an AI title and updates the ChatSession in the database."""
    try:
        with SessionLocal() as db:
            title = generate_chat_title(first_message)
            session = db.get(ChatSession, session_id)
            if session:
                session.title = title
                db.commit()
                logger.info(f"✨ [Background Task] Updated chat session {session_id} title to: '{title}'")
    except Exception as e:
        logger.error(f"⚠️ [Background Task] Failed to update chat session title: {e}", exc_info=True)


@router.post("/send", response_model=ChatResponse)
def send_chat_message(
    payload: ChatRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    # Retrieve verified Firebase UID as primary source of truth
    verified_user_id = current_user.get("uid")

    # Enforce strict tenancy: users can only chat as themselves
    if verified_user_id != payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot send messages on behalf of another user."
        )

    _consume_anonymous_global_chat_message(db, verified_user_id, current_user)

    # Check if the user exists in our database, auto-create them if not
    user = db.get(User, verified_user_id)
    current_email = current_user.get("email")
    if not user:
        user = User(id=verified_user_id, email=current_email)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.email and current_email:
        user.email = current_email
        db.commit()

    # Retrieve or create session
    active_session_id = payload.session_id
    if not active_session_id:
        # Create a temporary title instantly using the first 4 words of the message
        words = payload.message.split()
        temp_title = " ".join(words[:4])
        if len(words) > 4:
            temp_title += "..."
        if not temp_title:
            temp_title = "New conversation"

        session = ChatSession(user_id=verified_user_id, title=temp_title)
        db.add(session)
        db.commit()
        db.refresh(session)
        active_session_id = session.id

        # Schedule AI title generation in the background
        background_tasks.add_task(update_session_title_in_background, session.id, payload.message)
    else:
        # Verify ownership of session
        session = db.get(ChatSession, active_session_id)
        if not session or session.user_id != verified_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Invalid session ID."
            )
        # Touch updated_at so it bubble up to the top of the sidebar list
        session.updated_at = datetime.utcnow()
        db.commit()

    # Fetch completed lesson count for personalization using verified_user_id
    completed_lessons_query = select(CompletedLesson).where(CompletedLesson.user_id == verified_user_id)
    completed_count = len(db.scalars(completed_lessons_query).all())

    # Fetch last 10 messages from Postgres database for context *specifically in this session*
    history_query = (
        select(ChatMessage)
        .where(ChatMessage.session_id == active_session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    db_history = db.scalars(history_query).all()
    history_messages = _build_history_messages_with_budget(db_history)

    # Append the new user message
    new_message = HumanMessage(content=payload.message)
    all_messages = history_messages + [new_message]

    # Invoke our stateful LangGraph AI Tutor flowchart!
    state_input = {
        "messages": all_messages,
        "user_id": verified_user_id,
        "user_name": payload.user_name,
        "user_email": current_email,
        "completed_lessons_count": completed_count,
        "session_id": active_session_id,
        "db": db
    }

    try:
        output = tutor_graph.invoke(state_input)
        last_msg = output["messages"][-1]
        reply_content = extract_text_content(last_msg.content)
        action_required = None

        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                if tc.get("name") == "toggle_theme":
                    action_required = "TOGGLE_THEME"
                    reply_content = "¡Claro! Switched the theme. 😎"
                    break

        return ChatResponse(
            reply=reply_content,
            action_required=action_required,
            session_id=active_session_id
        )
    except Exception as e:
        logger.error(f"Tutor graph execution failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while generating a response. Please try again."
        )


@router.post("/send_stream")
def send_chat_message_stream(
    payload: ChatRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    # Retrieve verified Firebase UID as primary source of truth
    verified_user_id = current_user.get("uid")

    # Enforce strict tenancy: users can only chat as themselves
    if verified_user_id != payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot send messages on behalf of another user."
        )

    _consume_anonymous_global_chat_message(db, verified_user_id, current_user)

    # Check if the user exists in our database, auto-create them if not
    user = db.get(User, verified_user_id)
    current_email = current_user.get("email")
    if not user:
        user = User(id=verified_user_id, email=current_email)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.email and current_email:
        user.email = current_email
        db.commit()

    # Retrieve or create session
    active_session_id = payload.session_id
    if not active_session_id:
        # Create a temporary title instantly using the first 4 words of the message
        words = payload.message.split()
        temp_title = " ".join(words[:4])
        if len(words) > 4:
            temp_title += "..."
        if not temp_title:
            temp_title = "New conversation"

        session = ChatSession(user_id=verified_user_id, title=temp_title)
        db.add(session)
        db.commit()
        db.refresh(session)
        active_session_id = session.id

        # Schedule AI title generation in the background
        background_tasks.add_task(update_session_title_in_background, session.id, payload.message)
    else:
        # Verify ownership of session
        session = db.get(ChatSession, active_session_id)
        if not session or session.user_id != verified_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Invalid session ID."
            )
        # Touch updated_at so it bubble up to the top of the sidebar list
        session.updated_at = datetime.utcnow()
        db.commit()

    # Fetch completed lesson count for personalization using verified_user_id
    completed_lessons_query = select(CompletedLesson).where(CompletedLesson.user_id == verified_user_id)
    completed_count = len(db.scalars(completed_lessons_query).all())

    # Fetch last 10 messages from Postgres database for context *specifically in this session*
    history_query = (
        select(ChatMessage)
        .where(ChatMessage.session_id == active_session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    db_history = db.scalars(history_query).all()
    history_messages = _build_history_messages_with_budget(db_history)

    # Append the new user message
    new_message = HumanMessage(content=payload.message)
    all_messages = history_messages + [new_message]

    # Assemble complete state input
    state_input = {
        "messages": all_messages,
        "user_id": verified_user_id,
        "user_name": payload.user_name,
        "user_email": current_email,
        "completed_lessons_count": completed_count,
        "session_id": active_session_id,
    }

    async def sse_generator():
        try:
            # 1. Yield active session ID immediately so client can bind new conversations instantly
            yield f"data: {json.dumps({'session_id': active_session_id})}\n\n"

            # 2. Complete the same authoritative deterministic/adaptive plan used by
            # /send before response delivery begins.
            turn_plan = await asyncio.to_thread(_plan_turn_with_fresh_db, state_input)

            if turn_plan.guardrail_blocked:
                # Guardrails blocked: stream the off-topic reply word-by-word for premium feel
                reply_text = turn_plan.tutor_messages[-1].content
                words = reply_text.split()
                for i, w in enumerate(words):
                    space = " " if i > 0 else ""
                    yield f"data: {json.dumps({'token': space + w})}\n\n"
                    await asyncio.sleep(0.02)

                # Persist the safety exchange in a background thread (non-blocking)
                state_input["messages"].append(AIMessage(content=reply_text))
                await asyncio.to_thread(_save_memory_with_fresh_db, state_input)
                yield "data: [DONE]\n\n"
                return

            # 3. Retrieval and grounded tutor-context preparation already happened
            # inside the shared planner.
            tutor_messages = turn_plan.tutor_messages

            # 4. Stream response using async generator — zero event-loop blocking
            full_reply_text = ""
            action_required = None

            with SessionLocal() as stream_db:
                async for chunk in astream_with_fallback(tutor_messages, stream_db, bind_toggle_theme=True):
                    content = extract_text_content(chunk.content)
                    if content:
                        full_reply_text += content
                        yield f"data: {json.dumps({'token': content})}\n\n"

                    # Detect theme-toggle tool calls
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            if tc.get("name") == "toggle_theme":
                                action_required = "TOGGLE_THEME"
                                break

            # Handle theme toggle overrides
            if action_required == "TOGGLE_THEME":
                theme_reply = "¡Claro! Switched the theme. 😎"
                yield f"data: {json.dumps({'token': theme_reply})}\n\n"
                yield f"data: {json.dumps({'action_required': 'TOGGLE_THEME'})}\n\n"
                full_reply_text = theme_reply

            # 5. Persist final chat response in a background thread (non-blocking)
            state_input["messages"].append(AIMessage(content=full_reply_text))
            await asyncio.to_thread(_save_memory_with_fresh_db, state_input)

            # 6. Signal stream completion
            yield "data: [DONE]\n\n"

        except Exception as stream_err:
            logger.error(
                "[SSE] Response generator error for session_id=%s user_id=%s: %s",
                active_session_id,
                verified_user_id,
                stream_err,
                exc_info=True,
            )
            yield f"data: {json.dumps({'token': '⚠️ Lo siento, I hit an unexpected error during response generation.'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")



# 3. Fetch all chat sessions for the current user
@router.get("/sessions", response_model=List[SessionResponse])
def get_user_sessions(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("uid")
    query = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = db.scalars(query).all()
    return sessions


# 4. Rename a chat session
@router.put("/sessions/{session_id}", response_model=SessionResponse)
def rename_session(session_id: int, payload: SessionUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("uid")
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot modify another user's session."
        )
    session.title = payload.title
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


# 5. Delete a chat session
@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("uid")
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot delete another user's session."
        )
    db.delete(session)
    db.commit()
    return {"status": "success", "message": "Session deleted successfully"}


@router.post("/explain", response_model=ExplainResponse)
def explain_sentence(payload: ExplainRequest, _current_user: dict = Depends(get_current_user)):
    try:
        explanation_content = generate_explanation(payload.spanish_sentence, payload.english_translation)
        return ExplainResponse(explanation=explanation_content)
    except Exception as e:
        logger.error(f"[Explain] AI explanation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to generate explanation right now. Please try again.")
