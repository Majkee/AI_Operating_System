"""
Tool format converters for different LLM providers.

Handles conversion between Anthropic and OpenAI tool formats:
- Anthropic: {"name", "description", "input_schema"}
- OpenAI Responses API: {"type": "function", "name", "description", "parameters", "strict"}

For GPT-5.2+, strict mode is enabled by default to ensure function calls
reliably adhere to the function schema.

IMPORTANT: OpenAI strict mode requirements:
1. ALL properties must be listed in "required" array
2. additionalProperties must be false
3. Optional params must use ["type", "null"] union instead of being omitted from required
"""

import copy
import json
from typing import Any


def _make_schema_strict_compatible(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a schema to be OpenAI strict mode compatible (recursive).

    OpenAI strict mode requires:
    - ALL properties must be in the 'required' array
    - additionalProperties must be false
    - For optional params, use type union with null: ["string", "null"]
    - Nested objects must also follow these rules

    Args:
        schema: Original JSON schema

    Returns:
        Strict-mode compatible schema
    """
    # Deep copy to avoid mutating original (only at top level)
    schema = copy.deepcopy(schema)
    return _apply_strict_mode(schema)


def _apply_strict_mode(schema: dict[str, Any], original_required: set[str] | None = None) -> dict[str, Any]:
    """Recursively apply strict mode transformations to a schema.

    Args:
        schema: Schema to transform (modified in place)
        original_required: Set of originally required property names (for nullable detection)

    Returns:
        Transformed schema
    """
    properties = schema.get("properties", {})

    if properties:
        # Track which properties were originally required
        if original_required is None:
            original_required = set(schema.get("required", []))

        # Make all properties required
        all_property_names = list(properties.keys())
        schema["required"] = all_property_names

        # Process each property
        for prop_name, prop_schema in properties.items():
            # For properties that weren't originally required, make them nullable
            if prop_name not in original_required:
                current_type = prop_schema.get("type")
                if current_type and current_type != "null":
                    if isinstance(current_type, list):
                        # Already a list, add null if not present
                        if "null" not in current_type:
                            prop_schema["type"] = current_type + ["null"]
                    else:
                        # Single type, convert to list with null
                        prop_schema["type"] = [current_type, "null"]

            # Recursively process nested objects
            if prop_schema.get("type") == "object" or (
                isinstance(prop_schema.get("type"), list) and "object" in prop_schema.get("type", [])
            ):
                nested_required = set(prop_schema.get("required", []))
                _apply_strict_mode(prop_schema, nested_required)

            # Process array items if they are objects
            if prop_schema.get("type") == "array" or (
                isinstance(prop_schema.get("type"), list) and "array" in prop_schema.get("type", [])
            ):
                items = prop_schema.get("items", {})
                if isinstance(items, dict) and items.get("type") == "object":
                    items_required = set(items.get("required", []))
                    _apply_strict_mode(items, items_required)

        # Ensure additionalProperties is false
        schema["additionalProperties"] = False

    return schema


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
        # Deep copy input_schema to avoid mutating original
        parameters = copy.deepcopy(tool["input_schema"])

        # Apply strict mode transformations if enabled
        if strict:
            parameters = _make_schema_strict_compatible(parameters)

        tool_def = {
            "type": "function",
            "name": tool["name"],
            "description": tool["description"],
            "parameters": parameters,
        }

        if strict:
            tool_def["strict"] = True

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
