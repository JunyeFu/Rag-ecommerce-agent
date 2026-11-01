"""Owner-bound media tools shared by API and durable Worker."""

from __future__ import annotations

import asyncio
from uuid import UUID

from pydantic import ValidationError
from ragcommerce_agent_runtime import ProviderInvalidResponse, ToolResult
from ragcommerce_contracts import MediaInterpretation


def media_tool_handlers(handlers, media, provider):
    async def interpret(context, args):
        record, content = await asyncio.to_thread(
            media.read_owned, context.user_id, UUID(args.media_ref)
        )
        result = await provider.interpret_media(context, record.kind, record.content_type, content)
        try:
            value = MediaInterpretation.model_validate(
                {
                    **result,
                    "media_id": record.id,
                    "kind": record.kind,
                }
            )
        except ValidationError as error:
            fields = MediaInterpretation.model_fields
            diagnostic = [
                f"{item['loc'][0] if item['loc'] and item['loc'][0] in fields else '$'}:{item['type']}"
                for item in error.errors(
                    include_input=False, include_context=False, include_url=False
                )
            ]
            raise ProviderInvalidResponse("media schema: " + ", ".join(diagnostic)) from error
        return ToolResult({"media_interpretation": value.model_dump(mode="json")})

    return {**handlers, "vision.identify": interpret, "audio.transcribe": interpret}
