from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENAI_API_URL = "https://api.openai.com/v1/responses"


class OpenAIClientError(RuntimeError):
    pass


def extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_parts: list[str] = []
    for output_item in payload.get("output", []):
        for content in output_item.get("content", []):
            text = content.get("text")
            if text:
                text_parts.append(text)
    return "\n".join(text_parts).strip()


def ask_openai(question: str, context: str, model: str | None = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIClientError("OPENAI_API_KEY is not set.")

    payload = {
        "model": model or os.environ.get("DOCDB_OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Answer using only the supplied documentation index context. "
                            "If the index is insufficient, say that directly and suggest "
                            "which platform or query filters to broaden."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{context}\n\nUser question:\n{question}",
                    }
                ],
            },
        ],
        "max_output_tokens": 800,
    }

    request = Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OpenAIClientError(f"OpenAI request failed with {exc.code}: {detail}") from exc
    except URLError as exc:
        raise OpenAIClientError(f"OpenAI request failed: {exc.reason}") from exc

    answer = extract_output_text(result)
    if not answer:
        raise OpenAIClientError("OpenAI returned an empty response.")
    return answer

