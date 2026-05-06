from __future__ import annotations

from pathlib import Path


class NamespaceManager:
    """프로젝트별 FAISS 인덱스 파일 경로를 관리합니다."""

    def __init__(self, indices_dir: Path):
        self.indices_dir = indices_dir
        self.indices_dir.mkdir(parents=True, exist_ok=True)

    def index_path(self, namespace: str) -> Path:
        return self.indices_dir / namespace / "index.faiss"

    def meta_path(self, namespace: str) -> Path:
        return self.indices_dir / namespace / "id_map.pkl"

    def namespace_dir(self, namespace: str) -> Path:
        d = self.indices_dir / namespace
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_namespaces(self) -> list[str]:
        return [d.name for d in self.indices_dir.iterdir() if d.is_dir()]

    def exists(self, namespace: str) -> bool:
        return self.index_path(namespace).exists()

    def delete(self, namespace: str) -> None:
        ns_dir = self.indices_dir / namespace
        if ns_dir.exists():
            import shutil
            shutil.rmtree(ns_dir)
