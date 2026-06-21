# api/routers/ai_chat.py
#
# AI ENDPOINTS:
# POST /ai/query        — text query to AI medication assistant
# POST /ai/voice        — voice query (audio upload → transcribe → AI → TTS)
# POST /ai/insights     — get personalised health insights for a profile

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
from core.security import sanitize_for_llm, strip_llm_output_html
from schemas.all_schemas import AIQueryRequest, AIQueryResponse, VoiceQueryResponse
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
    """
    Sends a text question to the AI medication assistant.

    SECURITY:
    - Input sanitized (prompt injection defense) in AIQueryRequest validator
    - LLM output HTML-stripped in the RAG pipeline before reaching here
    - Rate limited by user_id (LLM quota)
    - Confidence gate: if no verified drug data found, returns safe fallback
    - Audit logged in the service layer
    """
    from ai.rag.pipeline import RAGPipeline
    from services.medication_service import MedicationService
    from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome

    audit = AuditLogger(db=db)

    # Fetch profile medications for context (if profile_id provided)
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
            pass  # If profile fetch fails, continue without context

    # Fetch conversation history from Redis if conversation_id provided
    conversation_history = []
    conversation_id = body.conversation_id or str(uuid.uuid4())
    if body.conversation_id and redis:
        try:
            import json
            history_key = f"conversation:{current_user.id}:{body.conversation_id}"
            history_json = await redis.get(history_key)
            if history_json:
                conversation_history = json.loads(history_json)
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

    # Store updated conversation history in Redis (last 5 turns, TTL 1 hour)
    if redis:
        try:
            import json
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
    """
    Accepts a voice recording, transcribes it with Whisper,
    runs the AI pipeline, and returns both text and audio response.

    SECURITY:
    - File size validated (max 25MB)
    - MIME type validated from file bytes (not filename extension)
    - Audio saved to /tmp with UUID filename (no path traversal)
    - Temp file deleted after processing
    """
    import os
    import tempfile

    from monitoring.audit import AuditEventType, AuditLogger, AuditOutcome

    audit = AuditLogger(db=db)

    # Validate file size
    max_bytes = settings.MAX_AUDIO_FILE_SIZE_MB * 1024 * 1024
    content = await audio_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise InvalidAudioError(
            f"Audio file too large. Maximum size is {settings.MAX_AUDIO_FILE_SIZE_MB}MB."
        )

    # Validate MIME type from the actual file bytes (not the filename)
    # python-magic reads the file header bytes — cannot be spoofed by renaming
    allowed_audio_types = {
        b"\xff\xfb": "mp3",      # MP3
        b"\x49\x44\x33": "mp3",  # MP3 with ID3 tag
        b"\x52\x49\x46\x46": "wav",  # WAV (RIFF header)
        b"\x00\x00\x00": "m4a",  # M4A/MP4
        b"\x1a\x45\xdf\xa3": "webm",  # WebM
        b"\x4f\x67\x67\x53": "ogg",  # OGG
    }

    file_header = content[:4]
    file_type_valid = any(content.startswith(sig) for sig in allowed_audio_types)
    if not file_type_valid:
        raise InvalidAudioError("Invalid audio format. Supported: MP3, WAV, M4A, WebM, OGG.")

    # Save to temp file with UUID name — never use the original filename
    # Original filename could contain path traversal: "../../etc/passwd"
    temp_dir = "/tmp/pillara_audio"
    os.makedirs(temp_dir, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}.audio"
    temp_path = os.path.join(temp_dir, temp_filename)

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

        # Sanitize the transcription before sending to LLM
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
            is_voice=True,  # Formats response for TTS
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
            # TTS failure is non-fatal — return text response without audio

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
        # Always delete the temp audio file — clean up PHI
        try:
            os.unlink(temp_path)
        except Exception:
            pass