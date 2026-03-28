import shutil
from pathlib import Path
from db import get_files_by_status, set_status


def execute(parent_dir: str = None, log_callback=None):
    """classified 상태 파일들을 실제로 이동."""
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    files = get_files_by_status("classified", parent_dir)
    if not files:
        log("⚠ 이동할 파일이 없습니다. (classified 상태 없음)")
        return

    done = 0
    failed = 0

    for f in files:
        src = Path(f["path"])
        dst_dir = Path(f["parent_dir"]) / f["target_folder"]

        try:
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f["filename"]

            # 이름 충돌 처리
            if dst.exists():
                stem, suffix = src.stem, src.suffix
                counter = 1
                while dst.exists():
                    dst = dst_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

            shutil.move(str(src), str(dst))
            set_status(f["id"], "done", str(dst_dir))
            log(f"  ✅ {f['filename']}  →  {dst_dir.name}/")
            done += 1

        except Exception as e:
            set_status(f["id"], "failed", reason=f"이동 실패: {e}")
            log(f"  ❌ {f['filename']}  실패: {e}")
            failed += 1

    log(f"\n완료: {done}개 이동  |  실패: {failed}개")


def retry_failed(parent_dir: str = None, log_callback=None):
    """failed 상태 파일들을 pending으로 복구."""
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    files = get_files_by_status("failed", parent_dir)
    if not files:
        log("⚠ 재시도할 파일이 없습니다.")
        return

    from db import set_pending_by_ids
    ids = [f["id"] for f in files]
    set_pending_by_ids(ids)
    log(f"✅ {len(ids)}개 파일을 pending으로 복구했습니다.")
