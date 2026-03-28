from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from db import init_db, upsert_file, upsert_folder, get_stats


def scan(target_dir: str, recursive: bool = False):
    """
    target_dir 내의 쌩 파일과 하위 폴더를 DB에 저장.

    - 쌩 파일: target_dir 바로 아래에 있는 파일
    - 폴더: target_dir 바로 아래에 있는 디렉토리 (그 안의 파일은 sample로만 수집)
    - recursive=True 이면 하위 폴더 안의 쌩 파일도 재귀 처리
    """
    root = Path(target_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"경로가 존재하지 않습니다: {target_dir}")

    init_db()

    file_count = 0
    folder_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("스캔 중...", total=None)

        def _scan_dir(directory: Path):
            nonlocal file_count, folder_count

            try:
                entries = list(directory.iterdir())
            except PermissionError:
                return

            loose_files = [e for e in entries if e.is_file()]
            subdirs = [e for e in entries if e.is_dir()]

            # 쌩 파일 저장
            for f in loose_files:
                try:
                    size = f.stat().st_size
                except OSError:
                    size = 0
                upsert_file(
                    path=str(f),
                    filename=f.name,
                    parent_dir=str(directory),
                    extension=f.suffix.lower(),
                    size_bytes=size,
                )
                file_count += 1
                progress.update(task, description=f"스캔 중... 파일 {file_count}개")

            # 하위 폴더 저장 (내부 파일은 sample용으로만)
            for d in subdirs:
                try:
                    inner = list(d.iterdir())
                    inner_files = [e.name for e in inner if e.is_file()]
                    inner_count = len(inner_files)
                    sample = inner_files[:20]  # 최대 20개만 샘플로
                except PermissionError:
                    sample = []
                    inner_count = 0

                upsert_folder(
                    path=str(d),
                    parent_dir=str(directory),
                    name=d.name,
                    sample_files=sample,
                    file_count=inner_count,
                )
                folder_count += 1

                if recursive:
                    _scan_dir(d)

        _scan_dir(root)

    stats = get_stats()
    pending = stats.get("pending", {})
    print(f"\n스캔 완료:")
    print(f"  쌩 파일: {file_count}개")
    print(f"  폴더:    {folder_count}개")
    if pending:
        total_gb = pending.get("bytes", 0) / (1024 ** 3)
        print(f"  총 용량: {total_gb:.2f} GB")
