"""OpenAI-backed grounded explanation generation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.config.settings import Settings
from src.prompts.explanations import get_active_explanation_prompt
from src.schemas.workflow import NarrativeExplanationOutput

try:
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


class ExplanationGenerationError(RuntimeError):
    """Raised when narrative explanation generation cannot produce valid grounded output."""


class ExplanationGenerator:
    """Generate a structured narrative explanation through an LLM structured-output call."""

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
    def from_settings(cls, settings: Settings, *, client: Any | None = None) -> ExplanationGenerator:
        """Build an explanation generator from application settings."""

        return cls(
            model_name=settings.openai_model,
            prompt_version=settings.explanation_prompt_version,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            client=client,
        )

    def generate(
        self,
        *,
        request: dict[str, Any],
        recommendation_candidates: list[dict[str, Any]],
        selected_projects: list[dict[str, Any]],
        excluded_projects: list[dict[str, Any]],
        evidence_bundle: dict[str, Any],
        ranking: list[dict[str, Any]],
    ) -> NarrativeExplanationOutput:
        """Generate a grounded structured explanation."""

        if not selected_projects:
            raise ExplanationGenerationError("Explanation generation requires selected projects.")

        prompt = get_active_explanation_prompt(self._prompt_version)
        payload = {
            "request": request,
            "recommendation_candidates": recommendation_candidates,
            "selected_projects": selected_projects,
            "excluded_projects": excluded_projects,
            "evidence_bundle": evidence_bundle,
            "ranking": ranking,
        }
        messages = prompt.build_messages(payload)
        raw_output = self._request_structured_output(messages)
        allowed_evidence_ids = {item["evidence_id"] for item in evidence_bundle.get("items", [])}
        return self._normalize_output(
            raw_output=raw_output,
            allowed_evidence_ids=allowed_evidence_ids,
            selected_projects=selected_projects,
        )

    def _build_client(self) -> Any | None:
        """Construct the OpenAI client when dependency and config are available."""

        if not self._api_key:
            return None
        if OpenAI is None:
            raise ExplanationGenerationError(
                "OpenAI dependency is not installed. Install project dependencies before enabling "
                "LLM-backed explanation generation."
            )
        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return OpenAI(**kwargs)

    def _request_structured_output(self, messages: list[dict[str, str]]) -> NarrativeExplanationOutput:
        """Request structured explanation output from the configured client."""

        if self._client is None:
            raise ExplanationGenerationError(
                "Explanation generation is not configured. Set LDT_OPENAI_API_KEY to enable Prompt 13."
            )

        responses_api = getattr(self._client, "responses", None)
        if responses_api is not None and hasattr(responses_api, "parse"):
            try:
                response = responses_api.parse(
                    model=self._model_name,
                    input=messages,
                    text_format=NarrativeExplanationOutput,
                )
            except TypeError:
                response = responses_api.parse(
                    model=self._model_name,
                    input=messages,
                    response_format=NarrativeExplanationOutput,
                )
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise ExplanationGenerationError("OpenAI responses.parse returned no parsed explanation output.")
            try:
                return NarrativeExplanationOutput.model_validate(parsed)
            except ValidationError as exc:
                raise ExplanationGenerationError("Generated explanation failed schema validation.") from exc

        beta_api = getattr(getattr(getattr(self._client, "beta", None), "chat", None), "completions", None)
        if beta_api is not None and hasattr(beta_api, "parse"):
            completion = beta_api.parse(
                model=self._model_name,
                messages=messages,
                response_format=NarrativeExplanationOutput,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise ExplanationGenerationError("OpenAI beta chat parse returned no parsed explanation output.")
            try:
                return NarrativeExplanationOutput.model_validate(parsed)
            except ValidationError as exc:
                raise ExplanationGenerationError("Generated explanation failed schema validation.") from exc

        raise ExplanationGenerationError("OpenAI client does not expose a supported structured-output parse API.")

    def _normalize_output(
        self,
        *,
        raw_output: NarrativeExplanationOutput,
        allowed_evidence_ids: set[str],
        selected_projects: list[dict[str, Any]],
    ) -> NarrativeExplanationOutput:
        """Validate grounded explanation output against known evidence and project inputs."""

        unknown_evidence = sorted(set(raw_output.cited_evidence_ids) - allowed_evidence_ids)
        if unknown_evidence:
            joined = ", ".join(unknown_evidence)
            raise ExplanationGenerationError(
                f"Explanation referenced unknown evidence ids: {joined}."
            )

        selected_titles = [str(project.get("title", "")) for project in selected_projects]
        if selected_titles and not any(title and title in raw_output.executive_summary + " " + raw_output.rationale for title in selected_titles):
            raise ExplanationGenerationError("Explanation must reference at least one selected project title.")

        return NarrativeExplanationOutput(
            executive_summary=raw_output.executive_summary,
            rationale=raw_output.rationale,
            caveats=raw_output.caveats,
            cited_evidence_ids=raw_output.cited_evidence_ids,
        )
