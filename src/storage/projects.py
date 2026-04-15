"""Storage abstractions and in-memory repository implementations."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectRecord:
    """Typed schema for ProjectRecord."""
    project_id: str
    title: str
    category: str
    municipality_id: str | None
    status: str
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class InMemoryProjectRepository:
    """In-memory implementation for ProjectRepository."""
    def __init__(self) -> None:
        """Initialize the instance and its dependencies."""
        self._projects = [
            ProjectRecord(
                project_id="proj-001",
                title="Urban Air Monitoring Expansion",
                category="Environment",
                municipality_id=None,
                status="pipeline",
                description="Expand municipal air-quality sensors and monitoring coverage.",
                metadata={
                    "indicator_keywords": ["air", "air_quality", "pollution", "monitoring"],
                    "development_plan_alignment": 0.9,
                    "readiness": 0.75,
                    "financing_plausibility": 0.8,
                    "public_investment_types": ["capital_program"],
                },
            ),
            ProjectRecord(
                project_id="proj-002",
                title="Regional Waste Transfer Modernization",
                category="Environment",
                municipality_id=None,
                status="pipeline",
                description="Upgrade transfer stations and collection logistics for waste services.",
                metadata={
                    "indicator_keywords": ["waste", "sanitation", "recycling", "transfer"],
                    "development_plan_alignment": 0.82,
                    "readiness": 0.7,
                    "financing_plausibility": 0.72,
                    "public_investment_types": ["capital_program"],
                },
            ),
            ProjectRecord(
                project_id="proj-003",
                title="Riverbank Flood Resilience Works",
                category="Environment",
                municipality_id="srb-belgrade",
                status="concept",
                description="Localized resilience and drainage works for flood-prone corridors.",
                metadata={
                    "indicator_keywords": ["flood", "drainage", "resilience", "water"],
                    "development_plan_alignment": 0.78,
                    "readiness": 0.45,
                    "financing_plausibility": 0.65,
                    "public_investment_types": ["capital_program"],
                },
            ),
            ProjectRecord(
                project_id="proj-004",
                title="Legacy Industrial Emissions Audit",
                category="Environment",
                municipality_id="other-city",
                status="cancelled",
                description="Legacy audit program retained only for exclusion-path testing.",
                metadata={
                    "indicator_keywords": ["air", "emissions", "industrial"],
                    "development_plan_alignment": 0.55,
                    "readiness": 0.2,
                    "financing_plausibility": 0.3,
                    "public_investment_types": ["operating_program"],
                },
            ),
        ]

    def list_by_category(self, category: str) -> list[ProjectRecord]:
        """List by category."""
        return [project for project in self._projects if project.category == category]
