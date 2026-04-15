"""OpenAI-backed project review generation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.config.settings import Settings
from src.prompts.project_reviews import get_active_project_review_prompt
from src.schemas.domain import ProjectReview

try:
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


class ProjectReviewGenerationError(RuntimeError):
    """Raised when project review generation cannot produce valid output."""


class ProjectReviewGenerator:
    """Generate structured project reviews through an LLM structured-output call."""

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
    def from_settings(cls, settings: Settings, *, client: Any | None = None) -> ProjectReviewGenerator:
        """Build a project review generator from settings."""

        return cls(
            model_name=settings.openai_model,
            prompt_version=settings.project_review_prompt_version,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            client=client,
        )

    def generate(
        self,
        *,
        run_context: dict[str, Any],
        project: dict[str, Any],
        review_evidence: list[dict[str, Any]],
    ) -> ProjectReview:
        """Generate a structured, evidence-backed project review."""

        prompt = get_active_project_review_prompt(self._prompt_version)
        messages = prompt.build_messages(
            {"run_context": run_context, "project": project, "review_evidence": review_evidence}
        )
        raw_output = self._request_structured_output(messages)
        allowed_ids = {item["evidence_id"] for item in review_evidence}
        return self._normalize_output(raw_output=raw_output, project_id=str(project["project_id"]), allowed_ids=allowed_ids)

    def _build_client(self) -> Any | None:
        """Construct the OpenAI client when dependency and config are available."""

        if not self._api_key:
            return None
        if OpenAI is None:
            raise ProjectReviewGenerationError(
                "OpenAI dependency is not installed. Install project dependencies before enabling project reviews."
            )
        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return OpenAI(**kwargs)

    def _request_structured_output(self, messages: list[dict[str, str]]) -> ProjectReview:
        """Request structured project review output."""

        if self._client is None:
            raise ProjectReviewGenerationError(
                "Project review generation is not configured. Set LDT_OPENAI_API_KEY to enable Prompt 14."
            )

        responses_api = getattr(self._client, "responses", None)
        if responses_api is not None and hasattr(responses_api, "parse"):
            try:
                response = responses_api.parse(model=self._model_name, input=messages, text_format=ProjectReview)
            except TypeError:
                response = responses_api.parse(model=self._model_name, input=messages, response_format=ProjectReview)
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise ProjectReviewGenerationError("OpenAI responses.parse returned no parsed project review output.")
            try:
                return ProjectReview.model_validate(parsed)
            except ValidationError as exc:
                raise ProjectReviewGenerationError("Generated project review failed schema validation.") from exc

        beta_api = getattr(getattr(getattr(self._client, "beta", None), "chat", None), "completions", None)
        if beta_api is not None and hasattr(beta_api, "parse"):
            completion = beta_api.parse(model=self._model_name, messages=messages, response_format=ProjectReview)
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise ProjectReviewGenerationError("OpenAI beta chat parse returned no parsed project review output.")
            try:
                return ProjectReview.model_validate(parsed)
            except ValidationError as exc:
                raise ProjectReviewGenerationError("Generated project review failed schema validation.") from exc

        raise ProjectReviewGenerationError("OpenAI client does not expose a supported structured-output parse API.")

    def _normalize_output(self, *, raw_output: ProjectReview, project_id: str, allowed_ids: set[str]) -> ProjectReview:
        """Normalize the generated project review."""

        if raw_output.project_id != project_id:
            raw_output = raw_output.model_copy(update={"project_id": project_id})

        unknown_ids = sorted(set(raw_output.citation_ids) - allowed_ids)
        if unknown_ids:
            raise ProjectReviewGenerationError(
                f"Project review referenced unknown evidence ids: {', '.join(unknown_ids)}."
            )
        return raw_output
