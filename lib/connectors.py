"""Wrapper around the external-tool CLI for Gmail and Shopify access."""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

GMAIL_SOURCE_ID = "gcal"
SHOPIFY_SOURCE_ID = "shopify_developer_app__pipedream"


async def call_tool(source_id: str, tool_name: str, arguments: dict) -> dict:
    """Call an external tool via the external-tool CLI."""
    payload = json.dumps({
        "source_id": source_id,
        "tool_name": tool_name,
        "arguments": arguments,
    })
    logger.info(f"Calling external-tool: {tool_name} with source {source_id}")
    proc = await asyncio.create_subprocess_exec(
        "external-tool", "call", payload,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        error_msg = stderr.decode().strip()
        logger.error(f"external-tool error for {tool_name}: {error_msg}")
        raise RuntimeError(f"external-tool call failed for {tool_name}: {error_msg}")
    result = json.loads(stdout.decode())
    return result
