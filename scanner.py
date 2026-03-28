from pathlib import Path
from db import init_db, upsert_file, upsert_folder, get_stats


def scan(target_dir: str, recursive: bool = False, log_callback=None):
    """
    target_dir 내의 쌩 파일과 하위 폴더를 DB에 저장.
    log_callback(str) 이 있으면 진행 메시지를 전달.
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    root = Path(target_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"경로가 존재하지 않습니다: {target_dir}")

    init_db()

    file_count = 0
    folder_count = 0

    def _scan_dir(directory: Path):
        nonlocal file_count, folder_count

        try:
            entries = list(directory.iterdir())
        except PermissionError:
            log(f"  ⚠ 권한 없음 (건너뜀): {directory}")
            return

        loose_files = [e for e in entries if e.is_file()]
        subdirs     = [e for e in entries if e.is_dir()]

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
            if file_count % 100 == 0:
                log(f"  파일 {file_count}개 발견 중...")

        for d in subdirs:
            try:
                inner = list(d.iterdir())
                inner_files = [e.name for e in inner if e.is_file()]
                inner_count = len(inner_files)
                sample = inner_files[:20]
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
    total_gb = pending.get("bytes", 0) / (1024 ** 3)
    log(f"  ✅ 쌩 파일: {file_count}개  |  폴더: {folder_count}개  |  총 용량: {total_gb:.2f} GB")
