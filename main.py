#!/usr/bin/env python3
"""
file_care - 다운로드 폴더 자동 분류 도구

사용 흐름:
  1. scan    → 폴더 탐색 및 DB 저장
  2. list    → 파일 목록 조회 / exclude 설정
  3. classify → LLM이 분류 결정
  4. review  → 분류 결과 확인
  5. execute → 실제 파일 이동
"""

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text
from db import (
    init_db, get_all_files, get_files_by_status,
    set_excluded_by_ids, set_pending_by_ids, get_stats
)

console = Console()

STATUS_COLOR = {
    "pending":    "white",
    "excluded":   "dim",
    "classified": "cyan",
    "done":       "green",
    "failed":     "red",
}


@click.group()
def cli():
    """file_care - LLM 기반 파일 자동 분류 도구"""
    pass


@cli.command()
@click.argument("target_dir")
@click.option("--recursive", "-r", is_flag=True, default=False,
              help="하위 폴더도 재귀적으로 스캔")
def scan(target_dir, recursive):
    """디렉토리를 스캔하여 DB에 저장합니다."""
    from scanner import scan as do_scan
    console.print(f"[cyan]스캔 시작: {target_dir}[/cyan]")
    do_scan(target_dir, recursive=recursive)
    _print_stats()


@cli.command("list")
@click.option("--dir", "-d", "parent_dir", default=None, help="특정 폴더만 필터")
@click.option("--status", "-s", default=None,
              type=click.Choice(["pending", "excluded", "classified", "done", "failed"]),
              help="상태 필터")
@click.option("--page", "-p", default=1, help="페이지 번호")
@click.option("--per-page", default=50, help="페이지당 항목 수")
def list_files(parent_dir, status, page, per_page):
    """파일 목록을 조회합니다."""
    if status:
        files = get_files_by_status(status, parent_dir)
    else:
        files = get_all_files(parent_dir)

    if not files:
        console.print("[yellow]파일이 없습니다.[/yellow]")
        return

    total = len(files)
    start = (page - 1) * per_page
    end = start + per_page
    page_files = files[start:end]

    table = Table(title=f"파일 목록 (총 {total}개, 페이지 {page}/{(total-1)//per_page+1})",
                  show_lines=False)
    table.add_column("ID", style="dim", width=6)
    table.add_column("상태", width=10)
    table.add_column("파일명", min_width=30)
    table.add_column("확장자", width=8)
    table.add_column("크기", width=10, justify="right")
    table.add_column("대상폴더", min_width=20)

    for f in page_files:
        color = STATUS_COLOR.get(f["status"], "white")
        table.add_row(
            str(f["id"]),
            Text(f["status"], style=color),
            f["filename"],
            f["extension"] or "-",
            _fmt_size(f["size_bytes"]),
            f["target_folder"] or "-",
        )

    console.print(table)
    console.print(f"\n[dim]페이지 이동: --page 2  |  상태 필터: --status pending[/dim]")


@cli.command()
@click.argument("ids", nargs=-1, type=int)
@click.option("--all-failed", is_flag=True, help="failed 전체 exclude")
def exclude(ids, all_failed):
    """파일을 excluded 상태로 표시합니다. (분류에서 제외)

    예) file_care exclude 1 2 3
        file_care exclude --all-failed
    """
    if all_failed:
        files = get_files_by_status("failed")
        ids = [f["id"] for f in files]

    if not ids:
        console.print("[yellow]ID를 지정하세요. 예: exclude 1 2 3[/yellow]")
        return

    set_excluded_by_ids(list(ids))
    console.print(f"[green]{len(ids)}개 파일을 excluded로 표시했습니다.[/green]")


@cli.command()
@click.argument("ids", nargs=-1, type=int)
def include(ids):
    """excluded 파일을 다시 pending으로 되돌립니다.

    예) file_care include 1 2 3
    """
    if not ids:
        console.print("[yellow]ID를 지정하세요. 예: include 1 2 3[/yellow]")
        return
    set_pending_by_ids(list(ids))
    console.print(f"[green]{len(ids)}개 파일을 pending으로 되돌렸습니다.[/green]")


@cli.command()
@click.option("--dir", "-d", "parent_dir", default=None, help="특정 폴더만 분류")
def classify(parent_dir):
    """LLM으로 파일을 분류합니다. (pending → classified/failed)"""
    from classifier import classify as do_classify
    do_classify(parent_dir)


@cli.command()
@click.option("--dir", "-d", "parent_dir", default=None, help="특정 폴더만")
def review(parent_dir):
    """분류 결과를 미리 확인합니다."""
    files = get_files_by_status("classified", parent_dir)
    if not files:
        console.print("[yellow]classified 상태 파일이 없습니다.[/yellow]")
        return

    table = Table(title=f"분류 결과 미리보기 ({len(files)}개)", show_lines=False)
    table.add_column("ID", style="dim", width=6)
    table.add_column("파일명", min_width=30)
    table.add_column("→ 대상폴더", min_width=20, style="cyan")
    table.add_column("이유", min_width=30, style="dim")

    for f in files:
        table.add_row(
            str(f["id"]),
            f["filename"],
            f["target_folder"] or "-",
            f["llm_reason"] or "-",
        )

    console.print(table)
    console.print(f"\n[dim]'execute' 명령으로 실제 이동하거나, 'exclude ID' 로 제외할 수 있습니다.[/dim]")


@cli.command()
@click.option("--dir", "-d", "parent_dir", default=None, help="특정 폴더만")
@click.option("--dry-run", is_flag=True, help="실제 이동 없이 미리 보기")
def execute(parent_dir, dry_run):
    """분류된 파일을 실제로 이동합니다. (classified → done/failed)"""
    from executor import execute as do_execute
    do_execute(parent_dir, dry_run=dry_run)


@cli.command()
@click.option("--dir", "-d", "parent_dir", default=None)
def retry(parent_dir):
    """failed 파일을 pending으로 되돌려 재시도합니다."""
    from executor import retry_failed
    retry_failed(parent_dir)


@cli.command()
def stats():
    """DB 통계를 출력합니다."""
    _print_stats()


def _print_stats():
    data = get_stats()
    table = Table(title="파일 상태 통계")
    table.add_column("상태", width=12)
    table.add_column("파일 수", justify="right", width=10)
    table.add_column("총 용량", justify="right", width=12)

    order = ["pending", "excluded", "classified", "done", "failed"]
    for status in order:
        if status in data:
            color = STATUS_COLOR.get(status, "white")
            info = data[status]
            table.add_row(
                Text(status, style=color),
                str(info["count"]),
                _fmt_size(info["bytes"]),
            )

    console.print(table)


def _fmt_size(bytes_val):
    if bytes_val is None or bytes_val == 0:
        return "-"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


if __name__ == "__main__":
    cli()
