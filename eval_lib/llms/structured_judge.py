from __future__ import annotations

import json


def build_judge_response_format():
    try:
        from pydantic import BaseModel, ConfigDict, Field
    except ImportError as exc:
        raise RuntimeError(
            "Structured judge providers require pydantic. "
            "Install it with `python -m pip install pydantic` or `uv pip install pydantic`."
        ) from exc

    class CriterionScore(BaseModel):
        model_config = ConfigDict(extra="forbid")

        name: str
        score: float

    class JudgeResponse(BaseModel):
        model_config = ConfigDict(populate_by_name=True, extra="forbid")

        score: float
        passed: bool = Field(alias="pass")
        refusal_detected: bool
        justification: str
        criteria_scores: list[CriterionScore]

    return JudgeResponse


def structured_judge_response_to_json(parsed: object) -> str:
    if hasattr(parsed, "model_dump"):
        data = parsed.model_dump(by_alias=True)
    elif isinstance(parsed, dict):
        data = parsed
    else:
        raise RuntimeError(f"Unexpected OpenAI parsed response type: {type(parsed).__name__}")

    criteria_scores = data.get("criteria_scores", {})
    if isinstance(criteria_scores, list):
        data["criteria_scores"] = {
            str(item.get("name")): item.get("score")
            for item in criteria_scores
            if isinstance(item, dict) and item.get("name") is not None
        }
    return json.dumps(data)
