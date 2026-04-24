from asyncio import gather
from typing import Optional
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel

from backend.db.dal import DALPhotobooks, DALPhotobookShare, DALUsers
from backend.db.dal.base import FilterOp
from backend.db.dal.schemas import DAOPhotobookShareCreate
from backend.db.data_models import (
    DAOPhotobooks,
    DAOPhotobookShare,
    DAOUsers,
    ShareRole,
)
from backend.lib.request.context import RequestContext
from backend.route_handler.base import RouteHandler, enforce_response_model


class SharePhotobookRequest(BaseModel):
    raw_emails_to_share: list[str]
    invited_user_ids: list[UUID] = []
    custom_message: str = ""
    role: ShareRole = ShareRole.VIEWER


class SharePhotobookResponse(BaseModel):
    success: bool
    message: str
    photobook_id: UUID
    user_id: UUID


class AutoCompleteUser(BaseModel):
    email: Optional[str]
    username: Optional[str]
    user_id: UUID


class SharePhotobookAutocompleteResponse(BaseModel):
    users: list[AutoCompleteUser]
    raw_emails: list[str]


class ShareAPIHandler(RouteHandler):
    def register_routes(self) -> None:
        self.route(
            "/api/share/photobooks/{photobook_id}",
            "share_photobook",
            methods=["POST"],
        )
        self.route(
            "/api/share/get_share_autocomplete_options",
            "get_share_autocomplete_options",
            methods=["GET"],
        )

    async def _find_autocomplete_user_from_id(
        self, user_id: UUID
    ) -> Optional[AutoCompleteUser]:
        async with self.app.new_db_session() as db_session:
            user: Optional[DAOUsers] = await DALUsers.get_by_id(
                db_session, user_id
            )
            if user:
                return AutoCompleteUser(
                    email=user.email,
                    username=user.name,
                    user_id=user.id,
                )
            return None

    @enforce_response_model
    async def get_share_autocomplete_options(
        self,
        request: Request,
    ) -> SharePhotobookAutocompleteResponse:
        request_context: RequestContext = await self.get_request_context(
            request
        )
        user_id: UUID = request_context.user_id
        async with self.app.new_db_session() as db_session:
            photobook_shares: list[DAOPhotobookShare] = (
                await DALPhotobookShare.list_all(
                    db_session,
                    filters={"user_id": (FilterOp.EQ, user_id)},
                )
            )
            raw_emails: list[str] = [
                share.email for share in photobook_shares if share.email
            ]
            users_with_none: list[Optional[AutoCompleteUser]] = await gather(
                *[
                    self._find_autocomplete_user_from_id(share.invited_user_id)
                    for share in photobook_shares
                    if share.invited_user_id
                ]
            )
            users: list[AutoCompleteUser] = [
                user for user in users_with_none if user is not None
            ]
            return SharePhotobookAutocompleteResponse(
                users=users,
                raw_emails=raw_emails,
            )

    @enforce_response_model
    async def share_photobook(
        self,
        photobook_id: UUID,
        request: Request,
        payload: SharePhotobookRequest,
    ) -> SharePhotobookResponse:
        request_context: RequestContext = await self.get_request_context(
            request
        )
        user_id: UUID = request_context.user_id
        async with self.app.new_db_session() as db_session:
            # Validate photobook ownership
            photobook: DAOPhotobooks | None = await DALPhotobooks.get_by_id(
                db_session, photobook_id
            )
            if not photobook or photobook.user_id != user_id:
                raise RuntimeError("Photobook not found or access denied")

            for email in payload.raw_emails_to_share:
                # Here you would implement the logic to share the photobook
                # For example, create a share entry in the database
                await DALPhotobookShare.create(
                    db_session,
                    DAOPhotobookShareCreate(
                        photobook_id=photobook_id,
                        email=email,
                        invited_user_id=None,  # Assuming email sharing
                        role=payload.role,
                        custom_message=payload.custom_message,
                    ),
                )
            for user_id in payload.invited_user_ids:
                await DALPhotobookShare.create(
                    db_session,
                    DAOPhotobookShareCreate(
                        photobook_id=photobook_id,
                        email=None,  # Assuming user ID sharing
                        invited_user_id=user_id,
                        role=payload.role,
                        custom_message=payload.custom_message,
                    ),
                )
            return SharePhotobookResponse(
                success=True,
                message="Photobook shared successfully",
                photobook_id=photobook_id,
                user_id=user_id,
            )

        # Here you would implement the logic to share the photobook
        # For example, create a share entry in the database
        pass
