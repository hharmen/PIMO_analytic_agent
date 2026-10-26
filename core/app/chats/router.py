"""Эндпоинты чатов. Все требуют входа, и каждый пользователь видит только свои чаты."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.service import run_agent
from app.auth.deps import get_current_user
from app.chats.schemas import (
    ChatCreate,
    ChatOut,
    CheckCreate,
    CheckRunOut,
    MessageCreate,
    MessageOut,
    SendMessageOut,
)
from app.clients.checker_client import CheckerError, check_model
from app.db.models import Chat, CheckRun, Message, User
from app.db.session import get_db

router = APIRouter(prefix="/chats", tags=["chats"], dependencies=[Depends(get_current_user)])

DEFAULT_TITLE = "Новый чат"


def get_own_chat(chat_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Chat:
    """Зависимость: чат по id из адреса, но только если он принадлежит вошедшему пользователю.

    Чужой чат и несуществующий дают один и тот же ответ 404, чтобы нельзя было
    перебором узнать, какие id заняты.
    """
    chat = db.get(Chat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Чат не найден")
    return chat


def _save_check_run(db: Session, chat: Chat, model: dict, result: dict) -> CheckRun:
    run = CheckRun(chat_id=chat.id, model_json=model, result_json=result, status=str(result.get("status", "UNKNOWN")))
    db.add(run)
    return run


@router.get("", response_model=list[ChatOut])
def list_chats(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Chat]:
    """Чаты пользователя, новые сверху."""
    return list(db.scalars(select(Chat).where(Chat.user_id == user.id).order_by(Chat.id.desc())))


@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
def create_chat(
    body: ChatCreate | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Chat:
    title = (body.title.strip() if body and body.title else "") or DEFAULT_TITLE
    chat = Chat(user_id=user.id, title=title)
    db.add(chat)
    db.commit()
    return chat


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat: Chat = Depends(get_own_chat), db: Session = Depends(get_db)) -> Response:
    """Удаляет чат вместе с сообщениями и результатами проверок."""
    db.delete(chat)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
def list_messages(chat: Chat = Depends(get_own_chat)) -> list[Message]:
    """Вся переписка чата по порядку (старые сверху)."""
    return chat.messages


@router.post("/{chat_id}/messages", response_model=SendMessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    body: MessageCreate, chat: Chat = Depends(get_own_chat), db: Session = Depends(get_db)
) -> SendMessageOut:
    """Сохраняет сообщение пользователя, зовёт агента и сохраняет его ответ.

    Ответ возвращается сразу целиком (без потоковой передачи).
    """
    user_message = Message(chat_id=chat.id, role="user", content=body.content)
    db.add(user_message)
    if chat.title == DEFAULT_TITLE:  # первое сообщение становится названием чата
        chat.title = " ".join(body.content.split())[:60]
    db.flush() 

    history = [{"role": m.role, "content": m.content} for m in chat.messages]
    try:
        reply = run_agent(history)
    except Exception:
        db.commit()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Агент не смог ответить. Сообщение сохранено")

    assistant_message = Message(chat_id=chat.id, role="assistant", content=reply.text)
    db.add(assistant_message)
    run = None
    if reply.model is not None and reply.check_result is not None:
        run = _save_check_run(db, chat, reply.model, reply.check_result)
    db.commit()
    return SendMessageOut(
        user_message=user_message,
        assistant_message=assistant_message,
        check_run=CheckRunOut.model_validate(run) if run else None,
    )



@router.get("/{chat_id}/checks", response_model=list[CheckRunOut])
def list_checks(chat: Chat = Depends(get_own_chat)) -> list[CheckRun]:
    """История проверок в этом чате."""
    return chat.check_runs


@router.post("/{chat_id}/checks", response_model=CheckRunOut, status_code=status.HTTP_201_CREATED)
def run_check(body: CheckCreate, chat: Chat = Depends(get_own_chat), db: Session = Depends(get_db)) -> CheckRun:
    """Ручная проверка модели через checker (без агента). Результат сохраняется в историю чата.
    """
    try:
        result = check_model(body.model, body.timeout_seconds, body.property_ids)
    except CheckerError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    run = _save_check_run(db, chat, body.model, result)
    db.commit()
    return run
