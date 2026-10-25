from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from fastapi import APIRouter, Depends, HTTPException, status, Response

from app.api.deps import (
    CurrentUser,
    CurrentWgUser,
    OptionalCurrentUser,
    SessionDep,
    get_current_user,
)
from app.enums.message import MsgType
from app.exceptions import AnotheActiveTournamentError
from app.models.message import Message
from app.models.tournament import Tournament
from app.models.tournament_participant import TournamentParticipant
from app.enums.tournament import TournamentType
from app.services.tournament_service import TournamentService
from app.exceptions import (
    AlreadyParticipatingError, 
    ForbiddenTournamentError, 
    SuperuserParticipantError, 
    TournamentNotFoundError, 
    RecruitmentClosedError
)
from app.schemas.tournament_schema import (
    TournamentCreateRequest, 
    TournamentParticipationInviteRead,
    TournamentParticipationRead, 
    TournamentPublicResponse, 
    TournamentUpdate
)


router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.get(
    "/{tournament_id}",
    response_model=TournamentPublicResponse,
    summary="Get public tournament by ID", 
    description="Retrieve public tournament by its ID.",
)
async def get_tournament(
    tournament_id: int,
    session: SessionDep,
    current_user: OptionalCurrentUser,
) -> TournamentPublicResponse:
    query = (
        select(Tournament)
        .options(selectinload(Tournament.owner))
        .where(Tournament.id == tournament_id)
    )

    if current_user is None:
        query = query.where(Tournament.tournament_type == TournamentType.PUBLIC)
    else:
        query = (
            query
            .join(Tournament.invites, isouter=True)
            .where(
                or_(
                    Tournament.tournament_type == TournamentType.PUBLIC,
                    Tournament.owner_id == current_user.id,
                    and_(
                        Message.receiver_id == current_user.id,
                        Message.msg_type == MsgType.TOURNAMENT_INVITE,
                    ),
                )
            )
        )

    tournament = await session.scalar(query)

    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    is_participating = False
    if current_user is not None:
        is_participating = await session.scalar(
            select(TournamentParticipant.user_id).where(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.user_id == current_user.id,
            )
        ) is not None

    return TournamentPublicResponse.model_validate(tournament).model_copy(
        update={
            "is_participating": is_participating,
            "own_tournament": tournament.is_own_tournament(current_user) if current_user else False,
            "owner_name": tournament.owner.name if tournament.owner else None,
        }
    )

@router.get(
    "/{tournament_id}/tournament_participants",
    response_model=list[TournamentParticipationRead],
    dependencies=[Depends(get_current_user)]
)
async def get_tournament_participants(
    tournament_id: int, 
    session: SessionDep,
):

    tournament = await session.scalar(
        select(Tournament)
        .options(selectinload(Tournament.participant_links))
        .where(Tournament.id == tournament_id)
    )

    if tournament is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tournament not found",
        )

    return [
        TournamentParticipationRead(
            user_id=participant_link.user_id,
            place=participant_link.place,
            battle_count=participant_link.battle_count,
            **participant_link.get_avarege_raiting()
        ) for participant_link
        in tournament.participant_links
    ]


@router.post(
    "",
    response_model=TournamentPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tournament",
    description="Create a new tournament with the provided details."
)
async def create_tournament(
    payload: TournamentCreateRequest, 
    session: SessionDep,
    current_user: CurrentUser
) -> Tournament:
    initial_status = TournamentService.determine_tournament_status(
        start_date=payload.start_date,
        recruitment_time=payload.recruitment_time,
        tournament_time=payload.tournament_time,
        now=datetime.now(timezone.utc),
    )
    new_tournament = Tournament(
        **payload.model_dump(),
        status=initial_status,
        owner_id=None if current_user.is_superuser else current_user.id,
        tournament_type=(
            TournamentType.PUBLIC
            if current_user.is_superuser
            else TournamentType.PRIVATE
        ),
    )

    session.add(new_tournament)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing_tournament = await session.scalar(
            select(Tournament).where(Tournament.name == payload.name)
        )
        if existing_tournament is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Имя турнира уже занято",
            ) from exc
        raise

    await session.refresh(new_tournament)
    return new_tournament


@router.get(
    "",
    response_model=list[TournamentPublicResponse],
    summary="Get all public tournaments",
    description="Retrieve a list of all public tournaments."
)
async def get_tournaments(
    session: SessionDep, 
    current_user: OptionalCurrentUser,
) -> list[TournamentPublicResponse]:

    if current_user is not None:
        tournaments = (await session.scalars(
            select(Tournament)
            .join(Tournament.invites, isouter=True)
            .where(
                or_(
                    Tournament.tournament_type == TournamentType.PUBLIC,
                    Tournament.owner_id == current_user.id, 
                    and_(
                        Message.receiver_id == current_user.id,
                        Message.msg_type == MsgType.TOURNAMENT_INVITE,
                    )
                )
            )
        )).unique()

    else:
        tournaments = await session.scalars(
            select(Tournament).where(
                Tournament.tournament_type == TournamentType.PUBLIC
            )
        )

    tournament_list = list(tournaments)
    participating_tournament_ids: set[int] = set()
    if current_user is not None and tournament_list:
        participating_tournament_ids = set(
            await session.scalars(
                select(TournamentParticipant.tournament_id).where(
                    TournamentParticipant.user_id == current_user.id,
                    TournamentParticipant.tournament_id.in_(
                        [tournament.id for tournament in tournament_list]
                    ),
                )
            )
        )

    return [
        TournamentPublicResponse.model_validate(tournament).model_copy(
            update={
                "is_participating": tournament.id in participating_tournament_ids
            }
        )
        for tournament in tournament_list
    ]

    

@router.patch(
    "/{tournament_id}",
    response_model=TournamentPublicResponse,
)
async def update_tournament(
    tournament_id: int,
    payload: TournamentUpdate,
    session: SessionDep,
    current_user: CurrentUser
) -> Tournament:
    tournament = await session.get(Tournament, tournament_id)

    if tournament is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tournament not found",
        )

    if (
        not tournament.is_own_tournament(current_user) or
        not tournament.is_scheduled()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        ) 

    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(tournament, field, value)

    await session.commit()
    await session.refresh(tournament)

    return tournament


@router.delete(
    "/{tournament_id}",
    response_class=Response,
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_tournament(
    tournament_id: int,
    session: SessionDep,
    current_user: CurrentUser
) -> Response:
    tournament = await session.get(Tournament, tournament_id)

    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tournament not found",
        )

    if not current_user.is_superuser and tournament.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        ) 

    await session.delete(tournament)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{tournament_id}/participate",
    response_model=TournamentParticipationInviteRead,
    status_code=status.HTTP_201_CREATED,
)
async def participate(
    tournament_id: int,
    session: SessionDep,
    current_user: CurrentWgUser
) -> TournamentParticipant:

    tournament = await session.get(Tournament, tournament_id)
    
    if tournament is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Турнір не знайдено",
        )
    
    try:
        participation = await TournamentService(session, tournament). \
            add_participant(user=current_user)
    
    except AlreadyParticipatingError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ви вже берете участь у цьому турнірі",
        )
    except AnotheActiveTournamentError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ви можете приймати участь тільки в одному турнірі одночасно",
        )
    except (
        RecruitmentClosedError,
        ForbiddenTournamentError,
        SuperuserParticipantError
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="долучитись до турніру неможливо",
        )

    return participation

    
