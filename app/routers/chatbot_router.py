"""Chatbot module router — company chatbot for all users."""
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.templating import templates
from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.chatbot import ChatSession, ChatMessage

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


# ─── Company knowledge base (placeholder for future AI integration) ───
COMPANY_FAQ = {
    "horaires": "Les horaires de bureau sont du lundi au vendredi, 9h-18h. L'equipe operation est joignable 24/7 pour les urgences en mer.",
    "conges": "Les demandes de conges doivent etre soumises via le module RH au moins 2 semaines a l'avance. Pour les marins, le planning d'embarquement fait foi.",
    "flotte": "La flotte TOWT comprend 4 voiliers-cargos : Anemos, Artemis, Atlantis et Atlas. Chaque navire est equipe pour le transport de marchandises sous voile.",
    "securite": "En cas d'urgence en mer, contactez immediatement le capitaine et le centre de coordination des secours (CROSS). Les procedures de securite sont affichees a bord.",
    "escale": "Les demandes liees aux escales (approvisionnement, maintenance, logistique) doivent etre soumises via le module Ticketing au moins 48h avant l'arrivee.",
    "contact": "Operations: operations@towt.eu | Commercial: commercial@towt.eu | RH: rh@towt.eu | Urgences: +33 2 XX XX XX XX",
    "towt": "TOWT (Transport a la Voile) est une compagnie maritime francaise specialisee dans le transport de marchandises a la voile, alliant performance ecologique et logistique moderne.",
    "embarquement": "Avant chaque embarquement, verifiez la validite de vos documents (passeport, visa, certificats medicaux) dans le module Equipage > Compliance.",
    "tickets": "Pour toute demande liee a une escale, utilisez le module Ticketing accessible depuis le menu lateral. Creez un ticket en precisant le navire, la categorie et la priorite.",
}


def _get_bot_response(message: str) -> str:
    """Simple keyword-based response. Placeholder for future AI integration."""
    msg_lower = message.lower().strip()

    # Check FAQ keywords
    for keyword, response in COMPANY_FAQ.items():
        if keyword in msg_lower:
            return response

    # Greeting
    greetings = ["bonjour", "salut", "hello", "hi", "hey", "bonsoir"]
    if any(g in msg_lower for g in greetings):
        return "Bonjour ! Je suis l'assistant TOWT. Comment puis-je vous aider ? Vous pouvez me poser des questions sur la flotte, les escales, les horaires, la securite, ou tout autre sujet lie a la compagnie."

    # Help
    if "aide" in msg_lower or "help" in msg_lower:
        return ("Voici les sujets sur lesquels je peux vous aider :\n"
                "- **Flotte** : informations sur les navires\n"
                "- **Escale** : procedures d'escale\n"
                "- **Horaires** : horaires de bureau\n"
                "- **Conges** : demandes de conges\n"
                "- **Securite** : procedures de securite\n"
                "- **Contact** : coordonnees des services\n"
                "- **Embarquement** : preparation embarquement\n"
                "- **Tickets** : systeme de ticketing\n\n"
                "Tapez un mot-cle ou posez votre question !")

    # Default
    return ("Je n'ai pas trouve de reponse precise a votre question. "
            "Essayez avec des mots-cles comme : flotte, escale, horaires, conges, securite, contact, embarquement.\n\n"
            "Pour une demande specifique liee a une escale, utilisez le module **Ticketing**.")


# === MAIN PAGE ===
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def chatbot_index(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Load user's sessions
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .options(selectinload(ChatSession.messages))
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()

    # Auto-create a session if none
    active_session = None
    if sessions:
        active_session = sessions[0]

    return templates.TemplateResponse("chatbot/index.html", {
        "request": request, "user": user,
        "sessions": sessions,
        "active_session": active_session,
        "active_module": "chatbot",
    })


# === NEW SESSION ===
@router.post("/session/new", response_class=HTMLResponse)
async def chatbot_new_session(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(
        user_id=user.id,
        title="Nouvelle conversation",
    )
    db.add(session)
    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": f"/chatbot/session/{session.id}"})
    return RedirectResponse(f"/chatbot/session/{session.id}", status_code=303)


# === VIEW SESSION ===
@router.get("/session/{session_id}", response_class=HTMLResponse)
async def chatbot_session(
    request: Request,
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    )
    active_session = result.scalar_one_or_none()
    if not active_session:
        raise HTTPException(status_code=404)

    # Load all sessions for sidebar
    all_sessions = (await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
    )).scalars().all()

    return templates.TemplateResponse("chatbot/index.html", {
        "request": request, "user": user,
        "sessions": all_sessions,
        "active_session": active_session,
        "active_module": "chatbot",
    })


# === SEND MESSAGE ===
@router.post("/session/{session_id}/send", response_class=HTMLResponse)
async def chatbot_send_message(
    request: Request,
    session_id: int,
    message: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404)

    # Save user message
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=message,
    )
    db.add(user_msg)

    # Generate and save bot response
    bot_response = _get_bot_response(message)
    bot_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=bot_response,
    )
    db.add(bot_msg)

    # Update session title from first message
    if session.title == "Nouvelle conversation":
        session.title = message[:60] + ("..." if len(message) > 60 else "")

    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": f"/chatbot/session/{session_id}"})
    return RedirectResponse(f"/chatbot/session/{session_id}", status_code=303)


# === DELETE SESSION ===
@router.post("/session/{session_id}/delete", response_class=HTMLResponse)
async def chatbot_delete_session(
    request: Request,
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404)

    await db.delete(session)
    await db.flush()

    if request.headers.get("HX-Request"):
        return HTMLResponse(headers={"HX-Redirect": "/chatbot"})
    return RedirectResponse("/chatbot", status_code=303)
