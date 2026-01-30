"""
Tool format converters for different LLM providers.

Handles conversion between Anthropic and OpenAI tool formats:
- Anthropic: {"name", "description", "input_schema"}
- OpenAI Responses API: {"type": "function", "name", "description", "parameters", "strict"}

For GPT-5.2+, strict mode is enabled by default to ensure function calls
reliably adhere to the function schema.
"""

import json
from typing import Any


def convert_tools_for_openai(
    anthropic_tools: list[dict[str, Any]],
    strict: bool = True
) -> list[dict[str, Any]]:
    """Convert Anthropic tool definitions to OpenAI Responses API format.

    Args:
        anthropic_tools: List of Anthropic tool definitions
        strict: Enable strict mode for function calls (recommended for GPT-5.2+)

    Returns:
        List of OpenAI function tool definitions
    """
    converted = []
    for tool in anthropic_tools:
        tool_def = {
            "type": "function",
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        }
        # Enable strict mode for reliable schema adherence
        if strict:
            tool_def["strict"] = True
            # Ensure additionalProperties is false for strict mode
            if "additionalProperties" not in tool_def["parameters"]:
                tool_def["parameters"]["additionalProperties"] = False

        converted.append(tool_def)

    return converted


def convert_openai_tool_calls(output_items: list) -> list[dict[str, Any]]:
    """Convert OpenAI Responses API function_call items to unified format.

    Args:
        output_items: List of output items from OpenAI response

    Returns:
        List of tool calls in unified format: [{id, name, input}, ...]
    """
    tool_calls = []
    for item in output_items:
        # Handle both object-style and dict-style items
        if hasattr(item, 'type'):
            item_type = item.type
            call_id = getattr(item, 'call_id', None)
            name = getattr(item, 'name', None)
            arguments = getattr(item, 'arguments', '{}')
        else:
            item_type = item.get('type')
            call_id = item.get('call_id')
            name = item.get('name')
            arguments = item.get('arguments', '{}')

        if item_type == "function_call" and call_id and name:
            try:
                input_data = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                input_data = {}

            tool_calls.append({
                "id": call_id,
                "name": name,
                "input": input_data
            })

    return tool_calls


def build_openai_tool_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build OpenAI Responses API function_call_output items.

    Args:
        results: List of tool results with tool_use_id and content

    Returns:
        List of function_call_output items for OpenAI API
    """
    return [{
        "type": "function_call_output",
        "call_id": r["tool_use_id"],
        "output": r["content"] if isinstance(r["content"], str) else json.dumps(r["content"])
    } for r in results]


def convert_tools_for_chat_completions(anthropic_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic tool definitions to OpenAI Chat Completions format.

    Similar to Responses API format but used for Chat Completions endpoint
    which is what LM Studio and other OpenAI-compatible APIs use.

    Args:
        anthropic_tools: List of Anthropic tool definitions

    Returns:
        List of OpenAI function tool definitions for Chat Completions
    """
    return [{
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    } for tool in anthropic_tools]


def convert_chat_completions_tool_calls(tool_calls: list) -> list[dict[str, Any]]:
    """Convert Chat Completions tool_calls to unified format.

    Args:
        tool_calls: List of tool_calls from Chat Completions response

    Returns:
        List of tool calls in unified format: [{id, name, input}, ...]
    """
    result = []
    for tc in tool_calls:
        # Handle both object-style and dict-style
        if hasattr(tc, 'id'):
            tc_id = tc.id
            tc_function = tc.function
            name = tc_function.name
            arguments = tc_function.arguments
        else:
            tc_id = tc.get('id')
            tc_function = tc.get('function', {})
            name = tc_function.get('name')
            arguments = tc_function.get('arguments', '{}')

        try:
            input_data = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            input_data = {}

        result.append({
            "id": tc_id,
            "name": name,
            "input": input_data
        })

    return result


def build_chat_completions_tool_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build Chat Completions tool result messages.

    Args:
        results: List of tool results with tool_use_id and content

    Returns:
        List of tool role messages for Chat Completions API
    """
    return [{
        "role": "tool",
        "tool_call_id": r["tool_use_id"],
        "content": r["content"] if isinstance(r["content"], str) else json.dumps(r["content"])
    } for r in results]
