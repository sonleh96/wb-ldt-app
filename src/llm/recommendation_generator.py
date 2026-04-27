"""OpenAI-backed recommendation candidate generation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.config.settings import Settings
from src.prompts.recommendation_candidates import get_active_recommendation_candidate_prompt
from src.schemas.domain import RecommendationCandidate
from src.schemas.workflow import RecommendationGenerationOutput

try:
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover - dependency may be absent in lean test environments
    OpenAI = None  # type: ignore[assignment]


class RecommendationGenerationError(RuntimeError):
    """Raised when recommendation generation cannot produce valid typed output."""


class RecommendationGenerator:
    """Generate typed recommendation candidates through a structured-output LLM call."""

    def __init__(
        self,
        *,
        model_name: str,
        prompt_version: str,
        api_key: str = "",
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        """Initialize the generator."""

        self._model_name = model_name
        self._prompt_version = prompt_version
        self._api_key = api_key
        self._base_url = base_url
        self._client = client if client is not None else self._build_client()

    @classmethod
    def from_settings(cls, settings: Settings, *, client: Any | None = None) -> RecommendationGenerator:
        """Build a recommendation generator from application settings."""

        return cls(
            model_name=settings.openai_model,
            prompt_version=settings.recommendation_prompt_version,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            client=client,
        )

    def generate(
        self,
        *,
        request: dict[str, Any],
        priority_signals: list[dict[str, Any]],
        evidence_bundle: dict[str, Any],
        context_pack: dict[str, Any],
        project_context: list[dict[str, Any]] | None = None,
        indicator_context: dict[str, Any] | None = None,
        top_n_projects: int,
        language: str,
    ) -> RecommendationGenerationOutput:
        """Generate validated recommendation candidates."""

        prompt = get_active_recommendation_candidate_prompt(self._prompt_version)
        prompt_input = {
            "request": request,
            "priority_signals": priority_signals,
            "evidence_bundle": evidence_bundle,
            "context_pack": context_pack,
            "top_n_projects": top_n_projects,
            "language": language,
        }
        if project_context is not None:
            prompt_input["project_context"] = project_context
        if indicator_context is not None:
            prompt_input["indicator_context"] = indicator_context
        messages = prompt.build_messages(prompt_input)
        raw_output = self._request_structured_output(messages)
        return self._normalize_output(
            raw_output=raw_output,
            allowed_evidence_ids={item["evidence_id"] for item in evidence_bundle.get("items", [])},
            prompt_version=prompt.version,
        )

    def _build_client(self) -> Any | None:
        """Construct the OpenAI client when the dependency and config are available."""

        if not self._api_key:
            return None
        if OpenAI is None:
            raise RecommendationGenerationError(
                "OpenAI dependency is not installed. Install project dependencies before enabling "
                "LLM-backed recommendation generation."
            )
        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return OpenAI(**kwargs)

    def _request_structured_output(self, messages: list[dict[str, str]]) -> RecommendationGenerationOutput:
        """Request structured recommendation candidates from the configured client."""

        if self._client is None:
            raise RecommendationGenerationError(
                "Recommendation generation is not configured. Set LDT_OPENAI_API_KEY to enable Prompt 11."
            )

        responses_api = getattr(self._client, "responses", None)
        if responses_api is not None and hasattr(responses_api, "parse"):
            try:
                response = responses_api.parse(
                    model=self._model_name,
                    input=messages,
                    text_format=RecommendationGenerationOutput,
                )
            except TypeError:
                response = responses_api.parse(
                    model=self._model_name,
                    input=messages,
                    response_format=RecommendationGenerationOutput,
                )
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise RecommendationGenerationError("OpenAI responses.parse returned no parsed output.")
            try:
                return RecommendationGenerationOutput.model_validate(parsed)
            except ValidationError as exc:
                raise RecommendationGenerationError(
                    "Generated recommendation candidates failed schema validation."
                ) from exc

        beta_api = getattr(getattr(getattr(self._client, "beta", None), "chat", None), "completions", None)
        if beta_api is not None and hasattr(beta_api, "parse"):
            completion = beta_api.parse(
                model=self._model_name,
                messages=messages,
                response_format=RecommendationGenerationOutput,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise RecommendationGenerationError("OpenAI beta chat parse returned no parsed output.")
            try:
                return RecommendationGenerationOutput.model_validate(parsed)
            except ValidationError as exc:
                raise RecommendationGenerationError(
                    "Generated recommendation candidates failed schema validation."
                ) from exc

        raise RecommendationGenerationError(
            "OpenAI client does not expose a supported structured-output parse API."
        )

    def _normalize_output(
        self,
        *,
        raw_output: RecommendationGenerationOutput,
        allowed_evidence_ids: set[str],
        prompt_version: str,
    ) -> RecommendationGenerationOutput:
        """Validate and normalize LLM output into backend-owned candidate objects."""

        try:
            candidates = [RecommendationCandidate.model_validate(item) for item in raw_output.candidates]
        except ValidationError as exc:
            raise RecommendationGenerationError("Generated recommendation candidates failed schema validation.") from exc

        if not candidates:
            raise RecommendationGenerationError("Recommendation generation returned no candidates.")

        normalized_candidates: list[RecommendationCandidate] = []
        for index, candidate in enumerate(candidates, start=1):
            unknown_evidence = sorted(set(candidate.supporting_evidence_ids) - allowed_evidence_ids)
            if unknown_evidence:
                joined = ", ".join(unknown_evidence)
                raise RecommendationGenerationError(
                    f"Recommendation candidate referenced unknown evidence ids: {joined}."
                )
            normalized_candidates.append(candidate.model_copy(update={"candidate_id": f"cand-{index}"}))

        return RecommendationGenerationOutput(
            candidates=normalized_candidates,
            model_name=self._model_name,
            prompt_version=prompt_version,
        )
