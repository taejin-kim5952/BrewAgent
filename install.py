"""
RAG Platform 설치 보조 스크립트
setup.bat에서 호출되며, Python 수준의 설치 작업을 담당합니다.
"""
import sys
import os
import subprocess
import shutil
from pathlib import Path


def check_python_version():
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        print(f"  [!] Python 3.10 이상이 필요합니다. 현재: {major}.{minor}")
        sys.exit(1)
    print(f"  [OK] Python {major}.{minor} 확인 완료")


def check_pip():
    try:
        import pip  # noqa: F401
        print("  [OK] pip 확인 완료")
    except ImportError:
        print("  [!] pip가 없습니다. python -m ensurepip --upgrade 를 실행하세요.")
        sys.exit(1)


def install_requirements(install_dir: Path):
    req_file = install_dir / "requirements.txt"
    if not req_file.exists():
        print(f"  [!] requirements.txt를 찾을 수 없습니다: {req_file}")
        sys.exit(1)

    venv_pip = install_dir / "venv" / "Scripts" / "pip.exe"
    if not venv_pip.exists():
        venv_pip = install_dir / "venv" / "bin" / "pip"

    print("  패키지 설치 중...")
    result = subprocess.run(
        [str(venv_pip), "install", "-r", str(req_file)],
        capture_output=False,
    )
    if result.returncode != 0:
        print("  [!] 패키지 설치 실패")
        sys.exit(1)
    print("  [OK] 패키지 설치 완료")


def create_storage_dirs(install_dir: Path):
    dirs = [
        install_dir / "storage" / "indices",
        install_dir / "storage" / "exports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print("  [OK] storage 디렉터리 생성 완료")


def check_ollama():
    if shutil.which("ollama"):
        print("  [OK] Ollama 확인 완료")
        return True
    print("  [!] Ollama가 설치되어 있지 않습니다.")
    return False


def check_tesseract():
    if shutil.which("tesseract"):
        print("  [OK] Tesseract OCR 확인 완료")
        return True
    print("  [i] Tesseract OCR 없음 (이미지 파싱 제한)")
    return False


def pull_ollama_model(model: str):
    print(f"  모델 다운로드: {model}")
    result = subprocess.run(["ollama", "pull", model])
    if result.returncode != 0:
        print(f"  [!] {model} 다운로드 실패")
    else:
        print(f"  [OK] {model} 다운로드 완료")


def main():
    if len(sys.argv) < 2:
        install_dir = Path("C:/RAGPlatform")
    else:
        install_dir = Path(sys.argv[1])

    print(f"\n  설치 경로: {install_dir}\n")

    check_python_version()
    check_pip()
    create_storage_dirs(install_dir)
    check_ollama()
    check_tesseract()

    print("\n  [OK] 보조 설치 작업 완료")


if __name__ == "__main__":
    main()
