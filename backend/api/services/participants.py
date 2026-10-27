"""
Participant Identification Service - Identifies and categorizes chat and call participants.

Provides:
- Exact matching by username and telegram_user_id
- Fuzzy matching by name
- Role identification (system user, employee, target, contact, unknown)
- Participant lists for chats and calls
"""
import json
import logging
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from anthropic import AsyncAnthropic, APIError, APIConnectionError

from ..models.database import User, Entity, Message, Chat, CallRecording, EntityType
from ..config import get_settings

logger = logging.getLogger("hr-analyzer.participants")
settings = get_settings()


class ParticipantRole(str, Enum):
    """Role of a participant in chat or call"""
    # Basic roles
    system_user = "system_user"   # 🔑 Пользователь системы (User)
    employee = "employee"         # 🏢 Наш сотрудник (Entity type=employee)
    target = "target"             # 👤 Объект анализа (Entity привязан к чату)
    contact = "contact"           # 📇 Известный контакт (Entity)
    unknown = "unknown"           # ❓ Неизвестен

    # Extended roles for AI-powered identification (HR context)
    interviewer = "interviewer"   # 👨‍💼 HR или руководитель, проводящий интервью
    candidate = "candidate"       # 👤 Кандидат на вакансию
    tech_lead = "tech_lead"       # 👨‍💻 Технический руководитель
    hr = "hr"                     # 🎯 HR-специалист
    manager = "manager"           # 📊 Руководитель/менеджер
    colleague = "colleague"       # 🤝 Коллега или член команды
    external = "external"         # 🌐 Внешний участник


@dataclass
class IdentifiedParticipant:
    """Identified participant with role and metadata"""
    telegram_user_id: int
    username: Optional[str]
    display_name: str
    role: ParticipantRole
    entity_id: Optional[int] = None
    user_id: Optional[int] = None
    confidence: float = 1.0
    ai_reasoning: Optional[str] = None


def get_role_icon(role) -> str:
    """
    Get emoji icon for participant role.

    Args:
        role: ParticipantRole enum or string (owner/target/employee/unknown)

    Returns:
        Emoji icon for the role
    """
    # Handle both enum and string roles
    if isinstance(role, ParticipantRole):
        icons = {
            ParticipantRole.system_user: "🔑",
            ParticipantRole.employee: "🏢",
            ParticipantRole.target: "👤",
            ParticipantRole.contact: "📇",
            ParticipantRole.unknown: "❓"
        }
        return icons.get(role, "❓")
    else:
        # String role (from participants dict)
        string_icons = {
            "owner": "🔑",
            "system_user": "🔑",
            "employee": "🏢",
            "target": "👤",
            "contact": "📇",
            "unknown": "❓"
        }
        return string_icons.get(str(role), "❓")


async def exact_match(
    username: Optional[str],
    telegram_user_id: Optional[int],
    org_id: Optional[int],
    db: AsyncSession
) -> Tuple[ParticipantRole, Optional[object]]:
    """
    Find exact match by username or telegram_user_id.

    Returns:
        Tuple of (role, matched_object) where matched_object is User or Entity
    """
    # Search in Users table
    if username:
        # First try primary telegram_username
        query = select(User).where(
            User.telegram_username == username
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if user:
            logger.debug(f"Exact match found: User {user.id} by primary username '{username}'")
            return ParticipantRole.system_user, user

        # Then try additional_telegram_usernames (JSON array)
        query = select(User).where(
            User.additional_telegram_usernames.contains([username])
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if user:
            logger.debug(f"Exact match found: User {user.id} by additional_telegram_username '{username}'")
            return ParticipantRole.system_user, user

    if telegram_user_id:
        query = select(User).where(
            User.telegram_id == telegram_user_id
        )
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if user:
            logger.debug(f"Exact match found: User {user.id} by telegram_id {telegram_user_id}")
            return ParticipantRole.system_user, user

    # Search in Entities table (scoped to organization)
    if org_id:
        # Search by telegram_user_id
        if telegram_user_id:
            query = select(Entity).where(
                Entity.org_id == org_id,
                Entity.telegram_user_id == telegram_user_id
            )
            result = await db.execute(query)
            entity = result.scalar_one_or_none()
            if entity:
                logger.debug(f"Exact match found: Entity {entity.id} by telegram_user_id {telegram_user_id}")
                # Note: Entity type field exists but "employee" is not in EntityType enum
                # We'll treat any Entity as contact for now
                return ParticipantRole.contact, entity

    logger.debug(f"No exact match for username='{username}', telegram_user_id={telegram_user_id}")
    return ParticipantRole.unknown, None


async def fuzzy_match_name(
    first_name: Optional[str],
    last_name: Optional[str],
    org_id: Optional[int],
    db: AsyncSession
) -> Tuple[ParticipantRole, Optional[Entity], float]:
    """
    Find Entity by fuzzy name matching.

    Returns:
        Tuple of (role, entity, confidence) where confidence is 0.0-1.0
    """
    if not first_name and not last_name:
        return ParticipantRole.unknown, None, 0.0

    if not org_id:
        return ParticipantRole.unknown, None, 0.0

    # Build full name for search
    full_name_parts = []
    if first_name:
        full_name_parts.append(first_name.strip())
    if last_name:
        full_name_parts.append(last_name.strip())

    if not full_name_parts:
        return ParticipantRole.unknown, None, 0.0

    full_name = " ".join(full_name_parts)

    # Search entities with ILIKE (case-insensitive)
    query = select(Entity).where(
        Entity.org_id == org_id,
        Entity.name.ilike(f"%{full_name}%")
    )
    result = await db.execute(query)
    entities = result.scalars().all()

    if not entities:
        logger.debug(f"No fuzzy match for name '{full_name}'")
        return ParticipantRole.unknown, None, 0.0

    # Calculate confidence based on match quality
    best_match = None
    best_confidence = 0.0

    for entity in entities:
        entity_name_lower = entity.name.lower()
        search_name_lower = full_name.lower()

        # Exact match (case-insensitive)
        if entity_name_lower == search_name_lower:
            confidence = 0.95
        # Entity name contains search name
        elif search_name_lower in entity_name_lower:
            confidence = 0.85
        # Search name contains entity name
        elif entity_name_lower in search_name_lower:
            confidence = 0.80
        # Partial match
        else:
            confidence = 0.70

        if confidence > best_confidence:
            best_confidence = confidence
            best_match = entity

    if best_match:
        logger.debug(f"Fuzzy match found: Entity {best_match.id} '{best_match.name}' with confidence {best_confidence:.2f}")
        return ParticipantRole.contact, best_match, best_confidence

    return ParticipantRole.unknown, None, 0.0


async def identify_participants(
    chat_id: int,
    org_id: Optional[int],
    db: AsyncSession,
    target_entity_id: Optional[int] = None,
    use_ai_fallback: bool = False
) -> List[IdentifiedParticipant]:
    """
    Identify all unique participants in a chat.

    Args:
        chat_id: Chat ID
        org_id: Organization ID for scoping Entity searches
        db: Database session
        target_entity_id: Optional entity_id from Chat.entity_id to mark as target
        use_ai_fallback: If True, use AI to identify unknown participants (requires ANTHROPIC_API_KEY)

    Returns:
        List of IdentifiedParticipant objects
    """
    # Get chat to retrieve entity_id if not provided
    if target_entity_id is None:
        query = select(Chat).where(Chat.id == chat_id)
        result = await db.execute(query)
        chat = result.scalar_one_or_none()
        if chat:
            target_entity_id = chat.entity_id

    # Get unique senders from messages
    query = select(
        Message.telegram_user_id,
        Message.username,
        Message.first_name,
        Message.last_name,
        func.max(Message.timestamp).label("last_seen")
    ).where(
        Message.chat_id == chat_id
    ).group_by(
        Message.telegram_user_id,
        Message.username,
        Message.first_name,
        Message.last_name
    ).order_by(
        func.max(Message.timestamp).desc()
    )

    result = await db.execute(query)
    unique_senders = result.all()

    identified = []

    for sender in unique_senders:
        telegram_user_id = sender.telegram_user_id
        username = sender.username
        first_name = sender.first_name or ""
        last_name = sender.last_name or ""

        # Build display name
        display_name_parts = []
        if first_name:
            display_name_parts.append(first_name)
        if last_name:
            display_name_parts.append(last_name)
        display_name = " ".join(display_name_parts) if display_name_parts else username or f"User {telegram_user_id}"

        # Try exact match first
        role, matched_obj = await exact_match(username, telegram_user_id, org_id, db)

        participant = IdentifiedParticipant(
            telegram_user_id=telegram_user_id,
            username=username,
            display_name=display_name,
            role=role,
            confidence=1.0
        )

        if role == ParticipantRole.system_user and isinstance(matched_obj, User):
            participant.user_id = matched_obj.id
        elif role == ParticipantRole.contact and isinstance(matched_obj, Entity):
            participant.entity_id = matched_obj.id
            # Check if this entity is the target
            if target_entity_id and matched_obj.id == target_entity_id:
                participant.role = ParticipantRole.target
        elif role == ParticipantRole.unknown:
            # Try fuzzy match by name
            fuzzy_role, entity, confidence = await fuzzy_match_name(
                first_name, last_name, org_id, db
            )
            if entity:
                participant.role = fuzzy_role
                participant.entity_id = entity.id
                participant.confidence = confidence
                # Check if this entity is the target
                if target_entity_id and entity.id == target_entity_id:
                    participant.role = ParticipantRole.target

        identified.append(participant)
        logger.debug(f"Identified participant: {display_name} ({username}) as {participant.role} (confidence: {participant.confidence:.2f})")

    # Use AI to identify unknown participants if enabled
    if use_ai_fallback:
        unknown_participants = [p for p in identified if p.role == ParticipantRole.unknown]
        known_participants = [p for p in identified if p.role != ParticipantRole.unknown]

        if unknown_participants:
            logger.info(f"Using AI to identify {len(unknown_participants)} unknown participants in chat {chat_id}")
            try:
                updated_unknown = await ai_identify_unknown_participants(
                    chat_id=chat_id,
                    unknown_participants=unknown_participants,
                    known_participants=known_participants,
                    db=db
                )
                # Replace unknown participants with AI-identified ones
                identified = known_participants + updated_unknown
            except Exception as e:
                logger.error(f"AI identification failed: {e}", exc_info=True)
                # Continue with original identified list on error

    return identified


async def identify_call_participants(
    call_id: int,
    org_id: Optional[int],
    db: AsyncSession,
    use_ai_fallback: bool = False
) -> List[IdentifiedParticipant]:
    """
    Identify participants in a call recording.

    Searches speakers by email in User.email, User.additional_emails, and Entity.email.
    If use_ai_fallback=True, uses AI to identify unknown speakers by analyzing transcript.

    Args:
        call_id: Call recording ID
        org_id: Organization ID for scoping Entity searches
        db: Database session
        use_ai_fallback: If True, use AI to identify unknown speakers from transcript context

    Returns:
        List of IdentifiedParticipant objects
    """
    # Get call recording
    query = select(CallRecording).where(CallRecording.id == call_id)
    result = await db.execute(query)
    call = result.scalar_one_or_none()

    if not call or not call.speakers:
        logger.debug(f"No call or speakers found for call_id={call_id}")
        return []

    identified = []
    target_entity_id = call.entity_id

    # Extract unique speakers from JSON
    # Format: [{speaker: "Speaker 1", start: 0.0, end: 5.2, text: "..."}, ...]
    unique_speakers = {}

    for segment in call.speakers:
        speaker_name = segment.get("speaker", "Unknown")
        if speaker_name not in unique_speakers:
            unique_speakers[speaker_name] = segment

    # Process each unique speaker
    speaker_index = 0
    for speaker_name, segment in unique_speakers.items():
        speaker_index += 1

        # Try to extract email from speaker name or segment
        # Common formats: "john@example.com", "John Doe (john@example.com)", etc.
        email = None
        if "@" in speaker_name:
            # Extract email using simple pattern
            parts = speaker_name.split()
            for part in parts:
                if "@" in part:
                    email = part.strip("()<>[]\"'")
                    break

        participant = IdentifiedParticipant(
            telegram_user_id=0,  # Calls don't have telegram_user_id
            username=None,
            display_name=speaker_name,
            role=ParticipantRole.unknown,
            confidence=1.0
        )

        # Try to match by email
        if email:
            # Search in Users by primary email
            query = select(User).where(User.email == email)
            result = await db.execute(query)
            user = result.scalar_one_or_none()

            if user:
                participant.role = ParticipantRole.system_user
                participant.user_id = user.id
                participant.display_name = user.name
                logger.debug(f"Matched call speaker '{speaker_name}' to User {user.id} by primary email")
            else:
                # Search in Users by additional_emails (JSON array)
                query = select(User).where(
                    User.additional_emails.contains([email])
                )
                result = await db.execute(query)
                user = result.scalar_one_or_none()

                if user:
                    participant.role = ParticipantRole.system_user
                    participant.user_id = user.id
                    participant.display_name = user.name
                    logger.debug(f"Matched call speaker '{speaker_name}' to User {user.id} by additional_email")
                elif org_id:
                    # Search in Entities (scoped to organization)
                    query = select(Entity).where(
                        Entity.org_id == org_id,
                        Entity.email == email
                    )
                    result = await db.execute(query)
                    entity = result.scalar_one_or_none()

                    if entity:
                        participant.role = ParticipantRole.contact
                        participant.entity_id = entity.id
                        participant.display_name = entity.name

                        # Check if this is the target entity
                        if target_entity_id and entity.id == target_entity_id:
                            participant.role = ParticipantRole.target

                        logger.debug(f"Matched call speaker '{speaker_name}' to Entity {entity.id} by email")

        # If no email match, try fuzzy match by name
        if participant.role == ParticipantRole.unknown and org_id:
            # Parse name from speaker
            name_parts = speaker_name.replace("(", " ").replace(")", " ").split()
            # Filter out email-like parts
            name_parts = [p for p in name_parts if "@" not in p]

            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = name_parts[-1]

                fuzzy_role, entity, confidence = await fuzzy_match_name(
                    first_name, last_name, org_id, db
                )

                if entity:
                    participant.role = fuzzy_role
                    participant.entity_id = entity.id
                    participant.confidence = confidence
                    participant.display_name = entity.name

                    # Check if this is the target entity
                    if target_entity_id and entity.id == target_entity_id:
                        participant.role = ParticipantRole.target

                    logger.debug(f"Fuzzy matched call speaker '{speaker_name}' to Entity {entity.id} (confidence: {confidence:.2f})")

        identified.append(participant)

    # Use AI to identify unknown speakers if enabled
    if use_ai_fallback and call.transcript:
        unknown_speakers = [p for p in identified if p.role == ParticipantRole.unknown]
        known_speakers = [p for p in identified if p.role != ParticipantRole.unknown]

        if unknown_speakers:
            logger.info(f"Using AI to identify {len(unknown_speakers)} unknown speakers in call {call_id}")
            try:
                updated_unknown = await ai_identify_call_speakers(
                    call=call,
                    unknown_speakers=unknown_speakers,
                    known_speakers=known_speakers
                )
                # Replace unknown speakers with AI-identified ones
                identified = known_speakers + updated_unknown
            except Exception as e:
                logger.error(f"AI call speaker identification failed: {e}", exc_info=True)
                # Continue with original identified list on error

    return identified


# ========================================================================
# AI-POWERED PARTICIPANT IDENTIFICATION
# ========================================================================

async def ai_identify_unknown_participants(
    chat_id: int,
    unknown_participants: List[IdentifiedParticipant],
    known_participants: List[IdentifiedParticipant],
    db: AsyncSession
) -> List[IdentifiedParticipant]:
    """
    AI определяет роли неизвестных участников по контексту переписки.
    Вызывается как fallback когда exact_match и fuzzy_match не сработали.

    Args:
        chat_id: ID чата для анализа
        unknown_participants: Участники с неизвестными ролями
        known_participants: Участники с известными ролями
        db: Сессия базы данных

    Returns:
        Обновленный список участников с AI-определенными ролями
    """
    if not unknown_participants:
        return []

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not configured, skipping AI identification")
        return unknown_participants

    # Get last 50 messages from chat for context
    messages_query = select(Message).where(
        Message.chat_id == chat_id
    ).order_by(
        Message.timestamp.desc()
    ).limit(50)

    messages_result = await db.execute(messages_query)
    messages = messages_result.scalars().all()
    messages = list(reversed(messages))  # chronological order

    if not messages:
        logger.warning(f"No messages found for chat {chat_id}")
        return unknown_participants

    # Format conversation for prompt
    conversation_text = _format_messages_for_ai(messages)

    # Build prompt
    prompt = _build_role_identification_prompt(
        unknown_participants=unknown_participants,
        known_participants=known_participants,
        conversation=conversation_text
    )

    # Call Claude API
    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Parse JSON response
        response_text = response.content[0].text
        logger.debug(f"AI response: {response_text}")

        # Extract JSON from response (it might be wrapped in markdown)
        json_start = response_text.find('[')
        json_end = response_text.rfind(']') + 1
        if json_start >= 0 and json_end > json_start:
            json_text = response_text[json_start:json_end]
            identifications = json.loads(json_text)
        else:
            raise ValueError("No valid JSON array found in response")

        # Update participants with AI results
        participant_map = {p.telegram_user_id: p for p in unknown_participants}

        for item in identifications:
            user_id = item.get('telegram_user_id')
            if user_id in participant_map:
                participant = participant_map[user_id]

                # Map role string to ParticipantRole enum
                role_str = item.get('role', 'unknown').lower()
                try:
                    participant.role = ParticipantRole(role_str)
                except ValueError:
                    logger.warning(f"Invalid role '{role_str}', using UNKNOWN")
                    participant.role = ParticipantRole.unknown

                # Set confidence (AI predictions are less certain than exact matches)
                # Clamp between 0.5 and 0.8
                raw_confidence = item.get('confidence', 0.6)
                participant.confidence = min(0.8, max(0.5, raw_confidence))
                participant.ai_reasoning = item.get('reasoning', '')

        logger.info(f"AI identified {len(identifications)} participants")
        return unknown_participants

    except (APIError, APIConnectionError) as e:
        logger.error(f"AI identification API error: {e}", exc_info=True)
        return unknown_participants
    except json.JSONDecodeError as e:
        logger.error(f"AI identification JSON parsing failed: {e}", exc_info=True)
        return unknown_participants
    except ValueError as e:
        logger.error(f"AI identification value error: {e}", exc_info=True)
        return unknown_participants


async def ai_identify_call_speakers(
    call: "CallRecording",
    unknown_speakers: List[IdentifiedParticipant],
    known_speakers: List[IdentifiedParticipant]
) -> List[IdentifiedParticipant]:
    """
    AI определяет роли неизвестных спикеров по контексту транскрипта звонка.
    Вызывается как fallback когда email/name matching не сработал.

    Args:
        call: CallRecording object with transcript
        unknown_speakers: Спикеры с неизвестными ролями
        known_speakers: Спикеры с известными ролями

    Returns:
        Обновленный список спикеров с AI-определенными ролями
    """
    if not unknown_speakers:
        return []

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not configured, skipping AI speaker identification")
        return unknown_speakers

    if not call.transcript:
        logger.warning(f"No transcript found for call {call.id}")
        return unknown_speakers

    # Build prompt for call speaker identification
    prompt = _build_call_speaker_identification_prompt(
        unknown_speakers=unknown_speakers,
        known_speakers=known_speakers,
        transcript=call.transcript[:8000],  # Limit transcript length
        call_title=call.title or "Звонок"
    )

    # Call Claude API
    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Parse JSON response
        response_text = response.content[0].text
        logger.debug(f"AI call speaker response: {response_text}")

        # Extract JSON from response
        json_start = response_text.find('[')
        json_end = response_text.rfind(']') + 1
        if json_start >= 0 and json_end > json_start:
            json_text = response_text[json_start:json_end]
            identifications = json.loads(json_text)
        else:
            raise ValueError("No valid JSON array found in response")

        # Update speakers with AI results
        speaker_map = {p.display_name: p for p in unknown_speakers}

        for item in identifications:
            speaker_name = item.get('speaker_name')
            if speaker_name in speaker_map:
                participant = speaker_map[speaker_name]

                # Map role string to ParticipantRole enum
                role_str = item.get('role', 'unknown').lower()
                try:
                    participant.role = ParticipantRole(role_str)
                except ValueError:
                    logger.warning(f"Invalid role '{role_str}', using UNKNOWN")
                    participant.role = ParticipantRole.unknown

                # Set confidence (AI predictions are less certain)
                raw_confidence = item.get('confidence', 0.6)
                participant.confidence = min(0.8, max(0.5, raw_confidence))
                participant.ai_reasoning = item.get('reasoning', '')

        logger.info(f"AI identified {len(identifications)} call speakers")
        return unknown_speakers

    except (APIError, APIConnectionError) as e:
        logger.error(f"AI call speaker identification API error: {e}", exc_info=True)
        return unknown_speakers
    except json.JSONDecodeError as e:
        logger.error(f"AI call speaker identification JSON parsing failed: {e}", exc_info=True)
        return unknown_speakers
    except ValueError as e:
        logger.error(f"AI call speaker identification value error: {e}", exc_info=True)
        return unknown_speakers


def _build_call_speaker_identification_prompt(
    unknown_speakers: List[IdentifiedParticipant],
    known_speakers: List[IdentifiedParticipant],
    transcript: str,
    call_title: str
) -> str:
    """Build prompt for AI call speaker role identification."""

    # Format known speakers
    known_text = ""
    if known_speakers:
        known_lines = ["Известные спикеры с определёнными ролями:"]
        for p in known_speakers:
            known_lines.append(f"- {p.display_name} - {p.role.value}")
        known_text = "\n".join(known_lines)

    # Format unknown speakers
    unknown_lines = ["Неизвестные спикеры:"]
    for p in unknown_speakers:
        unknown_lines.append(f"- speaker_name=\"{p.display_name}\"")
    unknown_text = "\n".join(unknown_lines)

    prompt = f"""Определи роли неизвестных спикеров по контексту транскрипта звонка.

Название звонка: {call_title}

{known_text}

{unknown_text}

ТРАНСКРИПТ ЗВОНКА:
{transcript}

РОЛИ И ИХ ПРИЗНАКИ:
- interviewer: HR или руководитель, проводит интервью, задаёт вопросы про опыт и навыки, представляется от компании
- candidate: Кандидат на вакансию, отвечает на вопросы про опыт, рассказывает про себя, спрашивает про условия
- tech_lead: Технический руководитель, задаёт технические вопросы, оценивает технические навыки
- hr: HR-специалист, обсуждает условия работы, зарплату, график
- manager: Руководитель, принимает решения, обсуждает задачи
- colleague: Коллега или член команды
- external: Внешний участник (клиент, подрядчик)

ЗАДАЧА:
Проанализируй транскрипт и определи наиболее вероятную роль для каждого неизвестного спикера.
Верни результат в виде JSON массива:

[
  {{
    "speaker_name": "Speaker 1",
    "role": "candidate",
    "confidence": 0.75,
    "reasoning": "Отвечает на вопросы про опыт, рассказывает про свои проекты"
  }}
]

ВАЖНО:
- Confidence должен быть между 0.5 и 0.8 (AI prediction никогда не бывает 100% точным)
- Если не можешь определить роль - используй "unknown" с низким confidence (0.5)
- Верни ТОЛЬКО валидный JSON массив, без дополнительного текста
- Обязательно включи ВСЕХ неизвестных спикеров из списка выше"""

    return prompt


def _format_messages_for_ai(messages: List[Message], max_messages: int = 50) -> str:
    """Format messages for AI analysis."""
    lines = []
    for msg in messages[-max_messages:]:
        sender = msg.first_name or msg.username or f"User{msg.telegram_user_id}"
        timestamp = msg.timestamp.strftime("%H:%M") if msg.timestamp else "??:??"
        content = msg.content[:200] if msg.content else "[медиа]"  # truncate long messages
        lines.append(f"[{timestamp}] {sender}: {content}")
    return "\n".join(lines)


def _build_role_identification_prompt(
    unknown_participants: List[IdentifiedParticipant],
    known_participants: List[IdentifiedParticipant],
    conversation: str
) -> str:
    """Build prompt for AI role identification."""

    # Format known participants
    known_text = ""
    if known_participants:
        known_lines = ["Известные участники с определёнными ролями:"]
        for p in known_participants:
            known_lines.append(
                f"- {p.display_name} (@{p.username or 'no_username'}) - "
                f"{p.role.value} (сообщений: много)"
            )
        known_text = "\n".join(known_lines)

    # Format unknown participants
    unknown_lines = ["Неизвестные участники:"]
    for p in unknown_participants:
        unknown_lines.append(
            f"- telegram_user_id={p.telegram_user_id}, "
            f"имя={p.display_name}, "
            f"username={p.username or 'нет'}"
        )
    unknown_text = "\n".join(unknown_lines)

    prompt = f"""Определи роли неизвестных участников по контексту переписки.

{known_text}

{unknown_text}

ПЕРЕПИСКА (последние 50 сообщений):
{conversation}

РОЛИ И ИХ ПРИЗНАКИ:
- interviewer: HR или руководитель, проводит интервью, задаёт вопросы про опыт и навыки
- candidate: Кандидат на вакансию, отвечает на вопросы про опыт, рассказывает про себя, спрашивает про компанию/условия
- tech_lead: Технический руководитель, задаёт технические вопросы, оценивает технические навыки
- hr: HR-специалист, обсуждает условия работы, зарплату, график, модерирует беседу
- manager: Руководитель, принимает решения, обсуждает задачи и цели
- colleague: Коллега или член команды
- external: Внешний участник (клиент, подрядчик и т.д.)

ЗАДАЧА:
Проанализируй переписку и определи наиболее вероятную роль для каждого неизвестного участника.
Верни результат в виде JSON массива:

[
  {{
    "telegram_user_id": 123456,
    "role": "candidate",
    "confidence": 0.8,
    "reasoning": "Отвечает на вопросы про опыт работы, рассказывает про проекты, спрашивает про условия"
  }}
]

ВАЖНО:
- Confidence должен быть между 0.5 и 0.8 (AI prediction никогда не бывает 100% точным)
- Если не можешь определить роль - используй "unknown" с низким confidence (0.5)
- Верни ТОЛЬКО валидный JSON массив, без дополнительного текста
- Обязательно включи ВСЕ неизвестные участники из списка выше"""

    return prompt


# =============================================================================
# Simple participant identification functions for pre-loaded objects
# =============================================================================

def identify_participants_from_objects(
    chat,
    messages: List,
    use_ai_fallback: bool = False
) -> dict:
    """
    Identify participants from pre-loaded chat and messages objects.
    
    This is a simpler version that doesn't require database access.
    Used by AI services that already have chat and messages loaded.
    
    Args:
        chat: Chat object with loaded owner and entity relationships
        messages: List of Message objects
        use_ai_fallback: Currently ignored (for compatibility)
    
    Returns:
        Dict mapping telegram_user_id to participant info dict
    """
    participants = {}
    
    # 1. Identify owner (HR manager who owns this chat)
    if hasattr(chat, 'owner') and chat.owner and hasattr(chat.owner, 'telegram_id') and chat.owner.telegram_id:
        participants[chat.owner.telegram_id] = {
            "name": chat.owner.name,
            "role": "owner",
            "entity_id": None,
            "entity_type": None
        }
    
    # 2. Identify target entity (the person/company this chat is about)
    if hasattr(chat, 'entity') and chat.entity and hasattr(chat.entity, 'telegram_user_id') and chat.entity.telegram_user_id:
        entity_type = chat.entity.type.value if hasattr(chat.entity.type, 'value') else str(chat.entity.type)
        participants[chat.entity.telegram_user_id] = {
            "name": chat.entity.name,
            "role": "target",
            "entity_id": chat.entity.id,
            "entity_type": entity_type
        }
    
    # 3. Collect all unique participants from messages
    for msg in messages:
        if msg.telegram_user_id not in participants:
            # Extract name from message metadata
            name = f"{msg.first_name or ''} {msg.last_name or ''}".strip()
            if not name:
                name = msg.username or f"User{msg.telegram_user_id}"
            
            participants[msg.telegram_user_id] = {
                "name": name,
                "role": "unknown",
                "entity_id": None,
                "entity_type": None
            }
    
    return participants


def get_role_label(role: str, entity_type: Optional[str] = None) -> str:
    """
    Get human-readable label for participant role in Russian.
    
    Args:
        role: Participant role (owner/target/employee/unknown)
        entity_type: Entity type if applicable (candidate/client/contractor)
    
    Returns:
        Role label in Russian
    """
    if role == "owner":
        return "HR Manager"
    elif role == "target":
        if entity_type == "candidate":
            return "кандидат"
        elif entity_type == "client":
            return "клиент"
        elif entity_type == "contractor":
            return "подрядчик"
        elif entity_type == "lead":
            return "лид"
        elif entity_type == "partner":
            return "партнер"
        else:
            return "контакт"
    elif role == "employee":
        return "сотрудник"
    else:
        return "неизвестный"


def format_participant_list(participants: dict) -> str:
    """
    Format participants list for AI context.
    
    Args:
        participants: Dict from identify_participants_from_objects()
    
    Returns:
        Formatted markdown string listing all participants
    """
    lines = ["## Участники чата:"]
    
    for telegram_id, info in participants.items():
        # Use simple role icons (compatible with existing get_role_icon)
        role_icons = {
            "owner": "🔑",
            "target": "👤",
            "employee": "🏢",
            "unknown": "❓"
        }
        icon = role_icons.get(info["role"], "❓")
        name = info["name"]
        label = get_role_label(info["role"], info.get("entity_type"))
        
        lines.append(f"- {icon} {name} ({label})")
    
    return "\n".join(lines)


def format_message_with_role(message, participants: dict) -> str:
    """
    Format a single message with participant role icon.
    
    Args:
        message: Message object
        participants: Dict from identify_participants_from_objects()
    
    Returns:
        Formatted message string
    """
    participant = participants.get(message.telegram_user_id)
    
    if participant:
        role_icons = {
            "owner": "🔑",
            "target": "👤",
            "employee": "🏢",
            "unknown": "❓"
        }
        icon = role_icons.get(participant["role"], "❓")
        name = participant["name"]
    else:
        icon = "❓"
        name = f"{message.first_name or ''} {message.last_name or ''}".strip()
        if not name:
            name = message.username or "Unknown"
    
    timestamp = message.timestamp.strftime("%d.%m %H:%M") if message.timestamp else ""
    content = message.content or "[медиа]"
    
    return f"[{timestamp}] {icon} {name}: {content}"
