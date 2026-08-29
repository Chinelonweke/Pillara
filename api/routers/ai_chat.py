import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from api.dependencies import (
    CurrentUser,
    DBSession,
    RedisClient,
    VerifiedUser,
    rate_limit_api,
    rate_limit_llm,
)
from core.config import settings
from core.exceptions import InvalidAudioError
from core.security import sanitize_for_llm
from schemas.all_schemas import AIQueryRequest, AIQueryResponse, VoiceQueryResponse, SuccessResponse
from monitoring.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/query",
    response_model=AIQueryResponse,
    summary="Ask the AI medication assistant a question",
    dependencies=[Depends(rate_limit_api), Depends(rate_limit_llm)],
)
async def ai_query(
    body: AIQueryRequest,
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
    redis: RedisClient,
) -> AIQueryResponse:
    from ai.rag.pipeline import RAGPipeline
    from services.medication_service import MedicationService
    from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome

    audit = AuditLogger(db=db)

    # Fetch profile medications for context
    profile_medication_names = []
    if body.profile_id:
        med_service = MedicationService(db=db)
        try:
            medications = await med_service.list_medications(
                profile_id=body.profile_id,
                user_id=current_user.id,
                request_id=request.state.request_id,
            )
            profile_medication_names = [m.name for m in medications if m.is_active]
        except Exception:
            pass

    # Fetch conversation history — slice at load time to prevent unbounded memory
    conversation_history = []
    conversation_id = body.conversation_id or str(uuid.uuid4())
    if body.conversation_id and redis:
        try:
            history_key = f"conversation:{current_user.id}:{body.conversation_id}"
            history_json = await redis.get(history_key)
            if history_json:
                conversation_history = json.loads(history_json)[-10:]
        except Exception:
            pass

    # Run the RAG pipeline
    pipeline = RAGPipeline(redis=redis)
    result = await pipeline.query(
        user_query=body.query,
        profile_medications=profile_medication_names,
        conversation_history=conversation_history,
        is_voice=False,
        request_id=request.state.request_id,
    )

    # Store updated conversation history in Redis (last 10 turns, TTL 1 hour)
    if redis:
        try:
            conversation_history.append({"role": "user", "content": body.query})
            conversation_history.append({"role": "assistant", "content": result.response_text})
            history_key = f"conversation:{current_user.id}:{conversation_id}"
            await redis.setex(history_key, 3600, json.dumps(conversation_history[-10:]))
        except Exception:
            pass

    await audit.log(
        event_type=AuditEventType.AI_QUERY_MADE,
        outcome=AuditOutcome.SUCCESS,
        user_id=current_user.id,
        profile_id=body.profile_id,
        request_id=request.state.request_id,
        details={
            "intent": result.query_intent,
            "confidence_gate_passed": result.confidence_gate_passed,
            "provider": result.provider_used,
            "latency_ms": result.latency_ms,
            "prompt_tokens": getattr(result, "prompt_tokens", 0),
            "completion_tokens": getattr(result, "completion_tokens", 0),
            "estimated_cost_usd": round(
                (getattr(result, "prompt_tokens", 0) / 1_000_000 * 0.59) +
                (getattr(result, "completion_tokens", 0) / 1_000_000 * 0.79),
                6
            ),
        },
    )

    return AIQueryResponse(
        response_text=result.response_text,
        disclaimer=result.disclaimer,
        confidence_gate_passed=result.confidence_gate_passed,
        fallback_triggered=result.fallback_triggered,
        query_intent=result.query_intent,
        provider_used=result.provider_used,
        latency_ms=result.latency_ms,
        conversation_id=conversation_id,
    )


@router.post(
    "/voice",
    response_model=VoiceQueryResponse,
    summary="Ask a question by voice",
    dependencies=[Depends(rate_limit_api), Depends(rate_limit_llm)],
)
async def voice_query(
    request: Request,
    current_user: VerifiedUser,
    db: DBSession,
    redis: RedisClient,
    audio_file: UploadFile = File(..., description="Audio file (MP3, WAV, M4A, max 25MB)"),
    profile_id: Optional[str] = Form(None),
    language: str = Form("en"),
) -> VoiceQueryResponse:
    import os
    from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome

    audit = AuditLogger(db=db)

    # Validate file size
    max_bytes = settings.MAX_AUDIO_FILE_SIZE_MB * 1024 * 1024
    content = await audio_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise InvalidAudioError(
            f"Audio file too large. Maximum size is {settings.MAX_AUDIO_FILE_SIZE_MB}MB."
        )

    # Validate MIME type from actual file bytes — cannot be spoofed by renaming
    allowed_audio_sigs = [
        b"\xff\xfb",             # MP3
        b"\x49\x44\x33",        # MP3 with ID3 tag
        b"\x52\x49\x46\x46",    # WAV (RIFF header)
        b"\x00\x00\x00",        # M4A/MP4
        b"\x1a\x45\xdf\xa3",    # WebM
        b"\x4f\x67\x67\x53",    # OGG
    ]
    if not any(content.startswith(sig) for sig in allowed_audio_sigs):
        raise InvalidAudioError("Invalid audio format. Supported: MP3, WAV, M4A, WebM, OGG.")

    # Save to temp file with UUID name — never use original filename (path traversal risk)
    temp_dir = "/tmp/pillara_audio"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}.audio")

    try:
        with open(temp_path, "wb") as f:
            f.write(content)

        # Transcribe with Whisper (runs locally — no PHI sent externally)
        from ai.stt.whisper_client import WhisperClient
        whisper = WhisperClient()
        transcription = await whisper.transcribe(
            audio_path=temp_path,
            language=language,
        )

        if not transcription or not transcription.strip():
            raise InvalidAudioError("Could not transcribe audio. Please speak clearly and try again.")

        clean_query = sanitize_for_llm(transcription)

        # Fetch profile medications
        profile_medication_names = []
        if profile_id:
            from services.medication_service import MedicationService
            med_service = MedicationService(db=db)
            try:
                medications = await med_service.list_medications(
                    profile_id=profile_id,
                    user_id=current_user.id,
                    request_id=request.state.request_id,
                )
                profile_medication_names = [m.name for m in medications if m.is_active]
            except Exception:
                pass

        # Run RAG pipeline with voice formatting
        from ai.rag.pipeline import RAGPipeline
        pipeline = RAGPipeline(redis=redis)
        result = await pipeline.query(
            user_query=clean_query,
            profile_medications=profile_medication_names,
            is_voice=True,
            request_id=request.state.request_id,
        )

        # Convert response to speech
        audio_url = None
        try:
            from ai.tts.tts_client import TTSClient
            tts = TTSClient()
            audio_url = await tts.synthesize(text=result.response_text)
        except Exception as tts_error:
            logger.warning("tts_failed", error=str(tts_error))

        await audit.log(
            event_type=AuditEventType.VOICE_QUERY_MADE,
            outcome=AuditOutcome.SUCCESS,
            user_id=current_user.id,
            profile_id=profile_id,
            request_id=request.state.request_id,
            details={
                "intent": result.query_intent,
                "confidence_gate_passed": result.confidence_gate_passed,
                "provider": result.provider_used,
            },
        )

        return VoiceQueryResponse(
            transcription=transcription,
            response_text=result.response_text,
            audio_url=audio_url,
            disclaimer=result.disclaimer,
            confidence_gate_passed=result.confidence_gate_passed,
            provider_used=result.provider_used,
            latency_ms=result.latency_ms,
        )

    finally:
        # Always delete temp audio file — clean up PHI
        try:
            os.unlink(temp_path)
        except Exception:
            pass


@router.post(
    "/feedback",
    response_model=SuccessResponse,
    summary="Submit feedback on an AI response",
)
async def submit_feedback(
    body: dict,
    current_user: CurrentUser,
    db: DBSession,
) -> SuccessResponse:
    from monitoring.analytics import track

    rating = body.get("rating", "unknown")
    conversation_id = body.get("conversation_id", "unknown")

    track("ai_feedback", user_id=str(current_user.id), properties={
        "rating": rating,
        "conversation_id": conversation_id,
    })

    logger.info(
        "ai_feedback_received",
        user_id=current_user.id,
        rating=rating,
        conversation_id=conversation_id,
    )

    return SuccessResponse(message="Feedback recorded. Thank you.")