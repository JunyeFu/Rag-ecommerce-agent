"""Versioned thin API for health, media, unified turns, decisions and SSE replay."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from ragcommerce_contracts import (
    CONTRACT_VERSION,
    AgentDecision,
    CartMutation,
    CartView,
    CreateListRequest,
    CreateThreadRequest,
    DecisionAccepted,
    DeletionResult,
    HealthResponse,
    MediaCreated,
    OfferCollection,
    PatchListRequest,
    ProductView,
    ResolvedOffer,
    ResolveOfferRequest,
    ShoppingListsResponse,
    ShoppingListView,
    ThreadCreated,
    ThreadSnapshot,
    TurnAccepted,
    TurnRequest,
)

from .commerce import CommercePort
from .erasure import UserDataEraser
from .media import InMemoryMediaStore, MediaRejected
from .ops import InMemoryOpsStore, register_ops_routes
from .security import RateLimitExceeded, SlidingWindowLimiter, parse_development_user
from .service import (
    DecisionConflict,
    IdempotencyConflict,
    OwnershipError,
    TurnService,
    public_event,
)


def health() -> HealthResponse:
    return HealthResponse(status="ok", contract_version=CONTRACT_VERSION)


def create_app(
    service: TurnService | None = None,
    media_store: InMemoryMediaStore | None = None,
    limiter: SlidingWindowLimiter | None = None,
    commerce: CommercePort | None = None,
    ops_store: InMemoryOpsStore | None = None,
    data_eraser: UserDataEraser | None = None,
    execute_background: bool = True,
) -> FastAPI:
    application = FastAPI(
        title="RAG Commerce Shopping Agent API",
        version=CONTRACT_VERSION,
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.turn_service = service
    application.state.media_store = media_store
    application.state.rate_limiter = limiter or SlidingWindowLimiter()
    application.state.commerce = commerce
    application.state.ops_store = ops_store
    application.state.data_eraser = data_eraser
    application.state.execute_background = execute_background

    def identity(x_user_id: Annotated[str | None, Header(alias="X-User-ID")] = None) -> UUID:
        try:
            user_id = parse_development_user(x_user_id)
            application.state.rate_limiter.check(user_id)
            return user_id
        except ValueError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
        except RateLimitExceeded as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc

    def configured_service() -> TurnService:
        value = application.state.turn_service
        if value is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Agent provider and persistence are not configured",
            )
        return value

    def configured_media() -> InMemoryMediaStore:
        value = application.state.media_store
        if value is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "media persistence is not configured",
            )
        return value

    def configured_commerce() -> CommercePort:
        value = application.state.commerce
        if value is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "commercial service is not configured",
            )
        return value

    def configured_data_eraser() -> UserDataEraser:
        value = application.state.data_eraser
        if value is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "transactional user-data erasure is not configured",
            )
        return value

    async def create_thread(
        request: CreateThreadRequest, x_user_id: Annotated[str | None, Header()] = None
    ) -> ThreadCreated:
        user_id = identity(x_user_id)
        try:
            record = configured_service().create_thread(user_id, request.goal)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        return ThreadCreated(thread_id=record.id, mission_id=record.mission_id)

    async def get_thread(
        thread_id: UUID, x_user_id: Annotated[str | None, Header()] = None
    ) -> ThreadSnapshot:
        try:
            return configured_service().snapshot(identity(x_user_id), thread_id)
        except OwnershipError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    async def upload_media(
        request: Request,
        content: Annotated[bytes, Body(media_type="application/octet-stream")],
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> MediaCreated:
        user_id = identity(x_user_id)
        declared_length = request.headers.get("content-length")
        if declared_length:
            try:
                if int(declared_length) > InMemoryMediaStore.AUDIO_LIMIT:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "media too large")
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid Content-Length") from exc
        try:
            record = configured_media().create(
                user_id, request.headers.get("content-type", ""), content
            )
        except MediaRejected as exc:
            code = (
                status.HTTP_413_CONTENT_TOO_LARGE
                if "size limit" in str(exc)
                else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )
            raise HTTPException(code, str(exc)) from exc
        return MediaCreated(
            media_id=record.id,
            kind=record.kind,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            expires_at=record.expires_at,
        )

    async def delete_media(
        media_id: UUID, x_user_id: Annotated[str | None, Header()] = None
    ) -> DeletionResult:
        user_id = identity(x_user_id)
        if not configured_media().delete(user_id, media_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
        return DeletionResult(deleted=True)

    async def delete_my_data(
        x_deletion_confirmation: Annotated[
            str | None, Header(alias="X-Deletion-Confirmation")
        ] = None,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> DeletionResult:
        user_id = identity(x_user_id)
        if x_deletion_confirmation != "delete-my-data":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "X-Deletion-Confirmation must equal delete-my-data",
            )
        configured_data_eraser().erase(user_id)
        return DeletionResult(deleted=True)

    async def create_turn(
        thread_id: UUID,
        request: TurnRequest,
        background_tasks: BackgroundTasks,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> TurnAccepted:
        user_id = identity(x_user_id)
        if idempotency_key is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")
        try:
            record, replayed = await configured_service().submit(
                user_id, thread_id, idempotency_key, request.text, request.media_ids
            )
        except OwnershipError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except IdempotencyConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        if not replayed and application.state.execute_background:
            background_tasks.add_task(configured_service().execute, record.run_id)
        return TurnAccepted(run_id=record.run_id, replayed=replayed, event_count=len(record.events))

    async def decide(
        run_id: UUID,
        decision: AgentDecision,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> DecisionAccepted:
        user_id = identity(x_user_id)
        try:
            record = await configured_service().decide(
                user_id, run_id, decision.tool_name, decision.approved
            )
        except OwnershipError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except DecisionConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return DecisionAccepted(
            run_id=record.run_id,
            approved=decision.approved,
            event_count=len(record.events),
        )

    async def events(
        run_id: UUID,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        user_id = identity(x_user_id)
        try:
            record = configured_service().require_run(user_id, run_id)
        except OwnershipError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        try:
            cursor = int(last_event_id or "0")
            if cursor < 0:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Last-Event-ID must be non-negative"
            ) from exc
        if cursor > len(record.events):
            raise HTTPException(status.HTTP_409_CONFLICT, "Last-Event-ID is ahead of the run")

        async def stream() -> AsyncIterator[str]:
            delivered = cursor
            while True:
                current = configured_service().require_run(user_id, run_id)
                for event in current.events:
                    if event.id <= delivered:
                        continue
                    event_name, payload = public_event(event)
                    yield (
                        f"id: {event.id}\n"
                        f"event: {event_name}\n"
                        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    )
                    delivered = event.id
                if current.execution_status in {
                    "COMPLETED",
                    "FAILED",
                    "WAITING_APPROVAL",
                    "WAITING_CLARIFICATION",
                }:
                    break
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    async def get_offers(
        product_id: UUID,
        fresh: bool = False,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> OfferCollection:
        return configured_commerce().get_offers(identity(x_user_id), product_id, fresh)

    async def get_product(
        product_id: UUID, x_user_id: Annotated[str | None, Header()] = None
    ) -> ProductView:
        return configured_commerce().get_product(identity(x_user_id), product_id)

    async def resolve_offer(
        offer_id: UUID,
        request: ResolveOfferRequest,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> ResolvedOffer:
        return configured_commerce().resolve_offer(identity(x_user_id), offer_id, request)

    async def get_lists(
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> ShoppingListsResponse:
        return configured_commerce().get_lists(identity(x_user_id))

    async def create_list(
        request: CreateListRequest,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> ShoppingListView:
        return configured_commerce().create_list(identity(x_user_id), request)

    async def patch_list(
        list_id: UUID,
        request: PatchListRequest,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> ShoppingListView:
        return configured_commerce().patch_list(identity(x_user_id), list_id, request)

    async def get_cart(x_user_id: Annotated[str | None, Header()] = None) -> CartView:
        return configured_commerce().get_cart(identity(x_user_id))

    async def mutate_cart(
        request: CartMutation,
        x_user_id: Annotated[str | None, Header()] = None,
    ) -> CartView:
        return configured_commerce().mutate_cart(identity(x_user_id), request)

    application.get(
        "/health", response_model=HealthResponse, tags=["system"], operation_id="getHealth"
    )(health)
    application.post(
        "/v1/threads",
        response_model=ThreadCreated,
        status_code=status.HTTP_201_CREATED,
        tags=["threads"],
        operation_id="createThread",
    )(create_thread)
    application.get(
        "/v1/threads/{thread_id}",
        response_model=ThreadSnapshot,
        tags=["threads"],
        operation_id="getThread",
    )(get_thread)
    application.post(
        "/v1/media",
        response_model=MediaCreated,
        status_code=status.HTTP_201_CREATED,
        tags=["media"],
        operation_id="createMedia",
    )(upload_media)
    application.delete(
        "/v1/media/{media_id}",
        response_model=DeletionResult,
        tags=["media"],
        operation_id="deleteMedia",
    )(delete_media)
    application.delete(
        "/v1/users/me/data",
        response_model=DeletionResult,
        tags=["privacy"],
        operation_id="deleteMyData",
    )(delete_my_data)
    application.post(
        "/v1/threads/{thread_id}/turns",
        response_model=TurnAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["agent"],
        operation_id="createTurn",
    )(create_turn)
    application.get(
        "/v1/agent-runs/{run_id}/events",
        response_class=StreamingResponse,
        tags=["agent"],
        operation_id="getAgentRunEvents",
    )(events)
    application.post(
        "/v1/agent-runs/{run_id}/decisions",
        response_model=DecisionAccepted,
        tags=["agent"],
        operation_id="createAgentRunDecision",
    )(decide)
    application.get(
        "/v1/products/{product_id}",
        response_model=ProductView,
        tags=["commerce"],
        operation_id="getProduct",
    )(get_product)
    application.get(
        "/v1/products/{product_id}/offers",
        response_model=OfferCollection,
        tags=["commerce"],
        operation_id="getProductOffers",
    )(get_offers)
    application.post(
        "/v1/offers/{offer_id}/resolve",
        response_model=ResolvedOffer,
        tags=["commerce"],
        operation_id="resolveOffer",
    )(resolve_offer)
    application.get(
        "/v1/lists",
        response_model=ShoppingListsResponse,
        tags=["commerce"],
        operation_id="getLists",
    )(get_lists)
    application.post(
        "/v1/lists",
        response_model=ShoppingListView,
        status_code=status.HTTP_201_CREATED,
        tags=["commerce"],
        operation_id="createList",
    )(create_list)
    application.patch(
        "/v1/lists/{list_id}",
        response_model=ShoppingListView,
        tags=["commerce"],
        operation_id="patchList",
    )(patch_list)
    application.get(
        "/v1/cart",
        response_model=CartView,
        tags=["commerce"],
        operation_id="getCart",
    )(get_cart)
    application.post(
        "/v1/cart",
        response_model=CartView,
        tags=["commerce"],
        operation_id="createCartMutation",
    )(mutate_cart)

    register_ops_routes(application)
    application.patch(
        "/v1/cart",
        response_model=CartView,
        tags=["commerce"],
        operation_id="patchCart",
    )(mutate_cart)

    @application.middleware("http")
    async def auth_mode_header(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Auth-Mode"] = "development-header"
        return response

    return application


app = create_app()
