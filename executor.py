import shutil
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from db import get_files_by_status, set_status, get_stats

console = Console()


def execute(parent_dir: str = None, dry_run: bool = False):
    """classified 상태 파일들을 실제로 이동."""
    files = get_files_by_status("classified", parent_dir)
    if not files:
        console.print("[yellow]이동할 파일이 없습니다. (classified 상태 없음)[/yellow]")
        console.print("먼저 'classify' 명령을 실행하세요.")
        return

    console.print(f"[cyan]이동 대상: {len(files)}개 파일[/cyan]")

    if dry_run:
        console.print("[yellow][DRY RUN 모드] 실제 이동하지 않습니다.[/yellow]\n")
        for f in files:
            src = Path(f["path"])
            dst_dir = Path(f["parent_dir"]) / f["target_folder"]
            dst = dst_dir / f["filename"]
            console.print(f"  [dim]{src}[/dim]")
            console.print(f"    → [green]{dst}[/green]  ({f['llm_reason']})")
        return

    if not Confirm.ask(f"\n{len(files)}개 파일을 이동하시겠습니까?"):
        console.print("취소됨.")
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
                stem = src.stem
                suffix = src.suffix
                counter = 1
                while dst.exists():
                    dst = dst_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

            shutil.move(str(src), str(dst))
            set_status(f["id"], "done", str(dst_dir))
            done += 1

        except Exception as e:
            set_status(f["id"], "failed", reason=f"이동 실패: {e}")
            console.print(f"[red]실패: {f['filename']} → {e}[/red]")
            failed += 1

    console.print(f"\n[green]완료: {done}개 이동 성공, {failed}개 실패[/green]")


def retry_failed(parent_dir: str = None):
    """failed 상태 파일들을 다시 pending으로 되돌림."""
    files = get_files_by_status("failed", parent_dir)
    if not files:
        console.print("[yellow]재시도할 파일이 없습니다.[/yellow]")
        return

    from db import set_pending_by_ids
    ids = [f["id"] for f in files]
    set_pending_by_ids(ids)
    console.print(f"[green]{len(ids)}개 파일을 pending으로 되돌렸습니다.[/green]")
