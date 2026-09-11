"""Compatibility facade for the retired google-generativeai API surface.

SHELF-SCOUTER keeps its existing inference call shape while the runtime is
backed by the supported ``google-genai`` SDK. This lets the application migrate
without changing its shelf-analysis or admission logic in the same change.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

from google import genai as _genai
from google.genai import types as _types


_api_key = ""


def configure(*, api_key: str | None = None, **_: Any) -> None:
    """Preserve the legacy configure() entry point using the new SDK client."""
    global _api_key
    _api_key = api_key or ""


class _LegacySchema:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in self.kwargs.items():
            if isinstance(value, _LegacySchema):
                result[key] = value.to_dict()
            elif isinstance(value, dict):
                result[key] = {
                    k: (v.to_dict() if isinstance(v, _LegacySchema) else v)
                    for k, v in value.items()
                }
            elif isinstance(value, list):
                result[key] = [v.to_dict() if isinstance(v, _LegacySchema) else v for v in value]
            else:
                result[key] = value
        return result


class _LegacyFunctionDeclaration:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _LegacyTool:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _LegacyPart:
    pass


class _LegacyType:
    OBJECT = "OBJECT"
    ARRAY = "ARRAY"
    STRING = "STRING"
    INTEGER = "INTEGER"


protos = SimpleNamespace(
    Tool=_LegacyTool,
    FunctionDeclaration=_LegacyFunctionDeclaration,
    Schema=_LegacySchema,
    Part=_LegacyPart,
    Type=_LegacyType,
)


class _LegacyGenerationConfig:
    def __new__(cls, **kwargs: Any) -> _types.GenerateContentConfig:
        return _types.GenerateContentConfig(**kwargs)


types = SimpleNamespace(
    GenerationConfig=_LegacyGenerationConfig,
)


def _convert_schema(schema: _LegacySchema | dict[str, Any] | None) -> dict[str, Any] | None:
    if schema is None:
        return None
    if isinstance(schema, _LegacySchema):
        value = schema.to_dict()
    else:
        value = dict(schema)

    # The legacy proto enum names are accepted by the API, but the new SDK's
    # JSON-schema path is clearer and avoids coupling this facade to enum types.
    type_value = value.get("type")
    if isinstance(type_value, str):
        value["type"] = type_value.lower()

    for key, child in list(value.items()):
        if isinstance(child, dict):
            value[key] = _convert_schema(child)
        elif isinstance(child, list):
            value[key] = [
                _convert_schema(item) if isinstance(item, dict) else item
                for item in child
            ]
    return value


def _convert_tools(tools: list[Any] | None) -> list[Any] | None:
    if tools is None:
        return None
    converted = []
    for tool in tools:
        if isinstance(tool, _LegacyTool):
            declarations = []
            for declaration in tool.kwargs.get("function_declarations", []):
                if not isinstance(declaration, _LegacyFunctionDeclaration):
                    declarations.append(declaration)
                    continue
                kwargs = declaration.kwargs
                declarations.append(
                    _types.FunctionDeclaration(
                        name=kwargs.get("name"),
                        description=kwargs.get("description"),
                        parameters_json_schema=_convert_schema(kwargs.get("parameters")),
                    )
                )
            converted.append(_types.Tool(function_declarations=declarations))
        else:
            converted.append(tool)
    return converted


def _convert_contents(contents: Any) -> Any:
    if not isinstance(contents, list):
        return contents

    converted = []
    for item in contents:
        if isinstance(item, dict) and "inline_data" in item:
            blob = item["inline_data"]
            data = blob.get("data", "")
            if isinstance(data, str):
                data = base64.b64decode(data)
            converted.append(
                _types.Part.from_bytes(
                    data=data,
                    mime_type=blob.get("mime_type", "application/octet-stream"),
                )
            )
        else:
            converted.append(item)
    return converted


def _convert_tool_config(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    function_config = value.get("function_calling_config")
    if not isinstance(function_config, dict):
        return value
    return _types.ToolConfig(
        function_calling_config=_types.FunctionCallingConfig(
            mode=function_config.get("mode", "AUTO"),
            allowed_function_names=function_config.get("allowed_function_names"),
        )
    )


class GenerativeModel:
    """Small compatibility wrapper backed entirely by google-genai."""

    def __init__(
        self,
        model_name: str,
        *,
        generation_config: Any = None,
        system_instruction: str | None = None,
        tools: list[Any] | None = None,
        **_: Any,
    ) -> None:
        self.model_name = model_name
        self.generation_config = generation_config
        self.system_instruction = system_instruction
        self.tools = tools
        self._client = _genai.Client(api_key=_api_key or None)

    def generate_content(self, contents: Any, *, tool_config: Any = None, **kwargs: Any) -> Any:
        config_kwargs: dict[str, Any] = {}
        if self.generation_config is not None:
            if isinstance(self.generation_config, _types.GenerateContentConfig):
                config_kwargs.update(self.generation_config.model_dump(exclude_none=True))
            elif isinstance(self.generation_config, dict):
                config_kwargs.update(self.generation_config)
        if self.system_instruction is not None:
            config_kwargs["system_instruction"] = self.system_instruction
        converted_tools = _convert_tools(self.tools)
        if converted_tools is not None:
            config_kwargs["tools"] = converted_tools
        if tool_config is not None:
            config_kwargs["tool_config"] = _convert_tool_config(tool_config)
        config_kwargs.update(kwargs)

        config = _types.GenerateContentConfig(**config_kwargs)
        return self._client.models.generate_content(
            model=self.model_name,
            contents=_convert_contents(contents),
            config=config,
        )


__all__ = ["GenerativeModel", "configure", "protos", "types"]
