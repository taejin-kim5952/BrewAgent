from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingConfig(BaseModel):
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"
    batch_size: int = 32
    dimension: int = 384


class ChunkingConfig(BaseModel):
    default_strategy: str = "sliding_window"
    chunk_size: int = 512
    chunk_overlap: int = 64
    code_chunk_size: int = 1024
    table_chunk_size: int = 256


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model_fast: str = "gemma3:4b"
    model_full: str = "gemma3:12b"
    timeout_seconds: int = 120


class RoutingConfig(BaseModel):
    complexity_threshold_fast: float = 0.3
    complexity_threshold_full: float = 0.7
    force_local: bool = True


class RetrievalConfig(BaseModel):
    top_k: int = 10
    vector_weight: float = 0.7
    bm25_weight: float = 0.3
    rerank_top_k: int = 5
    max_context_tokens: int = 4096


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"


class StorageConfig(BaseModel):
    base_dir: str = "../storage"

    @property
    def path(self) -> Path:
        return Path(self.base_dir).resolve()

    @property
    def indices_dir(self) -> Path:
        return self.path / "indices"

    @property
    def metadata_db(self) -> Path:
        return self.path / "metadata.db"

    @property
    def interactions_db(self) -> Path:
        return self.path / "interactions.db"

    @property
    def exports_dir(self) -> Path:
        return self.path / "exports"


class EvaluationConfig(BaseModel):
    auto_eval: bool = True
    min_score_for_memory: float = 0.75


class DatasetConfig(BaseModel):
    min_rating: int = 4
    min_eval_score: float = 0.7


def _load_yaml(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_settings() -> "Settings":
    base_dir = Path(__file__).parent
    data = _load_yaml(base_dir / "default.yaml")
    local_data = _load_yaml(base_dir / "local.yaml")

    # 딥 머지: local이 default를 오버라이드
    def deep_merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k] = deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    merged = deep_merge(data, local_data)
    return Settings(**merged)


class Settings(BaseModel):
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)

    def ensure_storage_dirs(self) -> None:
        for d in [
            self.storage.path,
            self.storage.indices_dir,
            self.storage.exports_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# 싱글톤 설정 인스턴스
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
