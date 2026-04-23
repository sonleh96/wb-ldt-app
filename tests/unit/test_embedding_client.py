from types import SimpleNamespace

import src.embeddings.client as embedding_module
from src.config.settings import Settings


class _FakeEmbeddingsAPI:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


class _FakeOpenAI:
    instance: "_FakeOpenAI | None" = None

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.embeddings = _FakeEmbeddingsAPI()
        _FakeOpenAI.instance = self


def test_build_embedding_client_passes_configured_dimensions_to_openai(monkeypatch) -> None:
    monkeypatch.setattr(embedding_module, "OpenAI", _FakeOpenAI)
    settings = Settings(
        embedding_provider="openai",
        openai_api_key="test-key",
        embedding_model="text-embedding-3-large",
        embedding_dimensions=1536,
    )

    client = embedding_module.build_embedding_client(settings)
    vectors = client.embed_texts(["test payload"])

    assert vectors == [[0.1, 0.2, 0.3]]
    assert _FakeOpenAI.instance is not None
    assert _FakeOpenAI.instance.api_key == "test-key"
    assert _FakeOpenAI.instance.embeddings.calls
    assert _FakeOpenAI.instance.embeddings.calls[0]["model"] == "text-embedding-3-large"
    assert _FakeOpenAI.instance.embeddings.calls[0]["input"] == ["test payload"]
    assert _FakeOpenAI.instance.embeddings.calls[0]["dimensions"] == 1536
