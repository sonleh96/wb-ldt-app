"""Deterministic project filtering before ranking."""

from dataclasses import dataclass, field

from src.storage.projects import ProjectRecord


@dataclass(frozen=True)
class FilteredProject:
    """Project plus deterministic filter diagnostics."""

    project: ProjectRecord
    exclusion_reasons: list[str] = field(default_factory=list)
    missing_information_flags: list[str] = field(default_factory=list)

    @property
    def is_excluded(self) -> bool:
        """Return whether the project is hard-excluded."""

        return bool(self.exclusion_reasons)


class ProjectFilter:
    """Apply deterministic eligibility filters to project records."""

    def filter_projects(
        self,
        *,
        projects: list[ProjectRecord],
        municipality_id: str,
        category: str,
    ) -> list[FilteredProject]:
        """Return projects with exclusion and missing-information diagnostics."""

        filtered: list[FilteredProject] = []
        for project in projects:
            exclusion_reasons: list[str] = []
            missing_information_flags: list[str] = []

            if project.category != category:
                exclusion_reasons.append("category_mismatch")

            if project.municipality_id not in {None, municipality_id}:
                exclusion_reasons.append("municipality_mismatch")

            if project.status.lower() in {"cancelled", "archived"}:
                exclusion_reasons.append("inactive_project_status")

            if not project.description:
                missing_information_flags.append("missing_project_description")

            for field_name in ("indicator_keywords", "public_investment_types"):
                if not project.metadata.get(field_name):
                    missing_information_flags.append(f"missing_{field_name}")

            for field_name in ("development_plan_alignment", "readiness", "financing_plausibility"):
                if field_name not in project.metadata:
                    missing_information_flags.append(f"missing_{field_name}")

            filtered.append(
                FilteredProject(
                    project=project,
                    exclusion_reasons=exclusion_reasons,
                    missing_information_flags=sorted(set(missing_information_flags)),
                )
            )
        return filtered
