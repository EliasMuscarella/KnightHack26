"""Stage 7: LLM rubric + interpretation through Hugging Face Inference Providers (HF_TOKEN),
with Gemini as a fallback (GEMINI_API_KEY). If neither works the stage is skipped and every
interpretation is marked `unavailable`; nothing is ever fabricated.

The model receives ONLY: the old block, the new block, the sentence-level diff, and the sentence
ids. It answers the narrow yes/no rubric questions with cited sentence ids and writes at most
3 short interpretation claims, each with cited sentence ids. Output is forced JSON, validated
against a Pydantic model, retried up to 3 times on invalid JSON, and then passed through the
deterministic citation validator (pipeline/validate.py). Temperature 0, pinned model id.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipeline.config import Settings
from pipeline.rubric import QUESTIONS, RUBRIC_VERSION
from pipeline.schema import Sentence
from pipeline.types import RiskBlock
from pipeline.validate import ValidationResult, validate_llm_output

log = logging.getLogger(__name__)

STAGE_VERSION = "0.2.0"
MAX_ATTEMPTS = 3
MAX_TOKENS = 1200
RETRY_BACKOFF_S = 2.0  # provider errors only (rate limits under parallel calls): 2s, 4s

SYSTEM_PROMPT = """You are a careful analyst comparing the Risk Factors section of a company's two consecutive annual reports (SEC Form 10-K). You answer narrow yes/no questions about ONE risk factor and write at most three short, neutral observations.

Rules you must follow:
- Use ONLY the OLD TEXT, NEW TEXT, and DIFF provided. Do not use outside knowledge.
- Every "yes" answer and every observation MUST cite one or more sentence ids exactly as given (format accession:block:sentence). Cite the sentence(s) that directly support the point.
- Describe what the filing says. Never estimate probabilities, never say a company became riskier or safer, never give investment advice, never use the words likely, unlikely, probability, buy, sell, invest, recommend, or guarantee.
- Observations are one sentence each, at most 40 words, factual, and specific to this risk factor.
- Respond with JSON only, matching the schema exactly."""

USER_TEMPLATE = """RISK FACTOR HEADING: {title}

OLD TEXT (fiscal year {old_fy}):
{old_text}

NEW TEXT (fiscal year {new_fy}):
{new_text}

SENTENCE-LEVEL DIFF (status: added / removed / modified / unchanged):
{diff_text}

QUESTIONS (answer each with true/false and cited sentence ids; a "yes" without a citation is invalid):
{questions}

Respond with this JSON object and nothing else:
{{
  "rubric": [
    {{"question_id": "Q1", "answer": true|false, "cited_sentence_ids": ["..."], "rationale": "<= 25 words"}},
    ... one entry per question ...
  ],
  "claims": [
    {{"text": "<one factual sentence>", "cited_sentence_ids": ["..."]}},
    ... at most 3 ...
  ]
}}"""


SHORT_TITLE_SYSTEM = """You write short labels for risk-factor headings from SEC annual reports, for a finance audience. For each heading, return a label of at most 8 plain-English words that names the topic neutrally (for example "Export controls on China sales" or "Dependence on TSMC manufacturing"). Labels describe the subject; they never say that something is likely, risky, good, or bad, and they never give advice. Respond with JSON only."""

SHORT_TITLE_USER = """Return this JSON object and nothing else:
{{"titles": [{{"change_id": "<id>", "short_title": "<at most 8 words>"}}, ...]}}

HEADINGS:
{items}"""


def short_title_prompt_sha256() -> str:
    return hashlib.sha256(
        (SHORT_TITLE_SYSTEM + "\n" + SHORT_TITLE_USER).encode("utf-8")
    ).hexdigest()


class RawShortTitle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    change_id: str
    short_title: str


class RawShortTitles(BaseModel):
    model_config = ConfigDict(extra="ignore")
    titles: list[RawShortTitle] = Field(default_factory=list)


def short_titles_raw(client: LLMClient, items: list[tuple[str, str]]) -> dict | None:
    """One temperature-0 call for every (change_id, heading). Returns the parsed raw JSON or None
    after MAX_ATTEMPTS failures. Validation and fallbacks happen in stages_final (not here)."""
    listing = "\n".join(f"{cid}\t{heading}" for cid, heading in items)
    user = SHORT_TITLE_USER.format(items=listing)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = client.complete(SHORT_TITLE_SYSTEM, user)
            parsed = RawShortTitles.model_validate(_extract_json(text))
            return parsed.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("short titles: invalid JSON on attempt %d: %s", attempt, type(e).__name__)
        except Exception as e:  # noqa: BLE001
            log.warning("short titles: provider error on attempt %d: %s", attempt, type(e).__name__)
    return None


def prompt_sha256() -> str:
    return hashlib.sha256(
        (SYSTEM_PROMPT + "\n" + USER_TEMPLATE + "\n" + RUBRIC_VERSION).encode("utf-8")
    ).hexdigest()


class RawRubricItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question_id: str
    answer: bool
    cited_sentence_ids: list[str] = Field(default_factory=list)
    rationale: str | None = None


class RawClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    cited_sentence_ids: list[str] = Field(default_factory=list)


class RawLLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rubric: list[RawRubricItem] = Field(default_factory=list)
    claims: list[RawClaim] = Field(default_factory=list, max_length=10)


JSON_SCHEMA = RawLLMOutput.model_json_schema()


def render_sentence(s: Sentence) -> str:
    return f"[{s.id}] ({s.side}, {s.status}) {s.text}"


def build_user_prompt(
    title: str,
    old: RiskBlock | None,
    new: RiskBlock | None,
    sentences: list[Sentence],
    old_fy: int,
    new_fy: int,
) -> str:
    def block_text(b: RiskBlock | None) -> str:
        if b is None:
            return "(no corresponding risk factor in this filing)"
        return "\n".join(f"[{s.id}] {s.text}" for s in b.sentences)

    diff_lines = []
    for s in sentences:
        if s.status == "unchanged" and s.side == "old":
            continue  # show unchanged once (new side)
        diff_lines.append(render_sentence(s))
    questions = "\n".join(f"{q.id}. {q.text}" for q in QUESTIONS)
    return USER_TEMPLATE.format(
        title=title,
        old_fy=old_fy,
        new_fy=new_fy,
        old_text=block_text(old),
        new_text=block_text(new),
        diff_text="\n".join(diff_lines),
        questions=questions,
    )


# ---------- providers ----------


class ProviderError(Exception):
    pass


@dataclass
class LLMClient:
    provider: str  # "huggingface" | "gemini"
    model_id: str
    _complete: Callable[[str, str], str]

    def complete(self, system: str, user: str) -> str:
        return self._complete(system, user)


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)?$")


def _check_model_id(model: str) -> str:
    if not _MODEL_ID_RE.match(model or ""):
        raise ProviderError(f"Model id must look like 'org/name', got {model!r}")
    return model


def make_hf_client(settings: Settings) -> LLMClient:
    from huggingface_hub import InferenceClient

    client = InferenceClient(token=settings.hf_token, timeout=90)
    model = _check_model_id(settings.llm_model)

    def complete(system: str, user: str) -> str:
        resp = client.chat_completion(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0,
            max_tokens=MAX_TOKENS,
            seed=0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "riskdiff_rubric", "schema": JSON_SCHEMA, "strict": True},
            },
        )
        return resp.choices[0].message.content or ""

    return LLMClient(provider="huggingface", model_id=f"hf:{model}", _complete=complete)


def make_gemini_client(settings: Settings) -> LLMClient:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=90_000)
    )
    model = settings.gemini_model

    def complete(system: str, user: str) -> str:
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.0,
                max_output_tokens=MAX_TOKENS,
                response_mime_type="application/json",
                response_schema=RawLLMOutput,
                seed=0,
            ),
        )
        return resp.text or ""

    return LLMClient(provider="gemini", model_id=f"gemini:{model}", _complete=complete)


PROBE_USER = 'Reply with the JSON object {"rubric": [], "claims": []} and nothing else.'


def probe(client: LLMClient) -> bool:
    try:
        out = client.complete("You reply with JSON only.", PROBE_USER)
        _extract_json(out)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning(
            "LLM provider %s (%s) probe failed: %s: %s",
            client.provider,
            client.model_id,
            type(e).__name__,
            str(e)[:160],
        )
        return False


def select_client(settings: Settings) -> tuple[LLMClient | None, str]:
    """Return (client, reason). Tries Hugging Face first, then Gemini. Never fabricates."""
    reasons = []
    if settings.hf_token:
        try:
            c = make_hf_client(settings)
            if probe(c):
                return c, "huggingface"
            reasons.append("Hugging Face Inference Providers did not respond to a probe request")
        except Exception as e:  # noqa: BLE001
            reasons.append(f"Hugging Face client failed: {type(e).__name__}")
    else:
        reasons.append("HF_TOKEN is not set")
    if settings.gemini_api_key:
        try:
            c = make_gemini_client(settings)
            if probe(c):
                return c, "gemini (fallback)"
            reasons.append("Gemini did not respond to a probe request")
        except Exception as e:  # noqa: BLE001
            reasons.append(f"Gemini client failed: {type(e).__name__}")
    else:
        reasons.append("GEMINI_API_KEY is not set")
    return None, "LLM stage unavailable: " + "; ".join(reasons)


# ---------- per-change call ----------


@dataclass
class LLMResult:
    status: str  # ok | empty | error
    validation: ValidationResult | None
    model_id: str
    attempts: int
    error: str | None = None
    raw: dict | None = None


def allowed_sentences(old: RiskBlock | None, new: RiskBlock | None) -> dict[str, str]:
    out = {s.id: s.text for s in (old.sentences if old else [])}
    out.update({s.id: s.text for s in (new.sentences if new else [])})
    return out


def interpret_change(
    client: LLMClient,
    title: str,
    old: RiskBlock | None,
    new: RiskBlock | None,
    sentences: list[Sentence],
    old_fy: int,
    new_fy: int,
) -> LLMResult:
    allowed = allowed_sentences(old, new)
    user = build_user_prompt(title, old, new, sentences, old_fy, new_fy)
    last_err: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = client.complete(SYSTEM_PROMPT, user)
            parsed = RawLLMOutput.model_validate(_extract_json(text))
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = f"invalid JSON on attempt {attempt}: {type(e).__name__}"
            log.warning("%s for %r", last_err, title[:60])
            continue
        except Exception as e:  # noqa: BLE001
            last_err = f"provider error on attempt {attempt}: {type(e).__name__}: {str(e)[:120]}"
            log.warning("%s for %r", last_err, title[:60])
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_S * 2 ** (attempt - 1))
            continue
        raw = parsed.model_dump()
        v = validate_llm_output(raw, allowed)
        status = "ok" if v.claims else "empty"
        return LLMResult(
            status=status, validation=v, model_id=client.model_id, attempts=attempt, raw=raw
        )
    return LLMResult(
        status="error",
        validation=None,
        model_id=client.model_id,
        attempts=MAX_ATTEMPTS,
        error=last_err,
    )
