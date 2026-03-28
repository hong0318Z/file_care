import json
from openai import OpenAI
from config import GITHUB_TOKEN, COPILOT_BASE_URL, MODEL, MAX_TOKENS, BATCH_SIZE
from db import (
    get_files_by_status, get_folders_by_parent, set_status, get_all_files
)
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from collections import defaultdict

console = Console()


def _build_folder_context(parent_dir: str) -> str:
    folders = get_folders_by_parent(parent_dir)
    if not folders:
        return "기존 폴더 없음 (새 폴더 생성 필요)"

    lines = ["[기존 폴더 구조]"]
    for f in folders:
        samples = json.loads(f["sample_files"]) if f["sample_files"] else []
        sample_str = ", ".join(samples[:10]) if samples else "비어있음"
        lines.append(f"  📁 {f['name']}/ ({f['file_count']}개 파일) 예: {sample_str}")
    return "\n".join(lines)


def _build_prompt(folder_context: str, files_batch: list) -> str:
    file_list = "\n".join(
        f"  [{f['id']}] {f['filename']} ({f['extension'] or '확장자없음'}, {_fmt_size(f['size_bytes'])})"
        for f in files_batch
    )

    return f"""당신은 파일 정리 전문가입니다. 아래 기존 폴더 구조를 참고하여 각 파일을 어느 폴더에 넣을지 결정하세요.

{folder_context}

[분류할 파일 목록]
{file_list}

## 분류 규칙
1. 기존 폴더가 있으면 그 폴더 이름과 내용을 참고하여 가장 적합한 폴더를 선택하세요.
2. 기존 폴더가 없거나 맞는 폴더가 없으면, 파일명/확장자로 추측하여 새 폴더명을 제안하세요.
   - 업무 관련: 기획서, 보고서, 계약, 제안, 회의, 업무 등의 단어
   - 이미지: .jpg, .png, .gif, .webp, .heic 등
   - 영상: .mp4, .mov, .avi, .mkv 등
   - 문서: .pdf, .docx, .xlsx, .pptx, .hwp 등
   - 압축: .zip, .rar, .7z, .tar.gz 등
   - 코드: .py, .js, .ts, .java, .cpp 등
   - 기타: 위에 해당 없으면 "기타"
3. 확신이 없어도 최선을 다해 추측하세요. null은 정말 판단 불가능할 때만 사용하세요.

## 응답 형식 (JSON만 출력, 다른 텍스트 없음)
{{
  "results": [
    {{
      "id": 파일ID(정수),
      "target_folder": "폴더명",
      "reason": "한 줄 이유"
    }},
    ...
  ]
}}
"""


def _fmt_size(bytes_val: int) -> str:
    if bytes_val is None:
        return "?"
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.0f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f}TB"


def classify(parent_dir: str = None):
    """pending 상태의 파일들을 LLM으로 분류."""
    if not GITHUB_TOKEN:
        console.print("[red]오류: GITHUB_TOKEN 환경변수가 설정되지 않았습니다.[/red]")
        console.print("  export GITHUB_TOKEN=ghp_xxxx")
        return

    client = OpenAI(
        api_key=GITHUB_TOKEN,
        base_url=COPILOT_BASE_URL,
    )

    pending_files = get_files_by_status("pending", parent_dir)
    if not pending_files:
        console.print("[yellow]분류할 파일이 없습니다. (pending 상태 없음)[/yellow]")
        return

    console.print(f"[cyan]분류 시작: {len(pending_files)}개 파일[/cyan]")

    # parent_dir 별로 그룹핑
    groups = defaultdict(list)
    for f in pending_files:
        groups[f["parent_dir"]].append(f)

    total_done = 0
    total_failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("LLM 분류 중...", total=len(pending_files))

        for pdir, files in groups.items():
            folder_context = _build_folder_context(pdir)

            # 배치 처리
            for i in range(0, len(files), BATCH_SIZE):
                batch = files[i:i + BATCH_SIZE]
                prompt = _build_prompt(folder_context, batch)

                try:
                    response = client.chat.completions.create(
                        model=MODEL,
                        max_tokens=MAX_TOKENS,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    raw = response.choices[0].message.content.strip()

                    # JSON 파싱
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    data = json.loads(raw)

                    id_map = {f["id"]: f for f in batch}
                    classified_ids = set()

                    for item in data.get("results", []):
                        fid = item.get("id")
                        target = item.get("target_folder")
                        reason = item.get("reason", "")

                        if fid in id_map:
                            classified_ids.add(fid)
                            if target:
                                set_status(fid, "classified", target, reason)
                                total_done += 1
                            else:
                                set_status(fid, "failed", reason=f"LLM이 판단 불가: {reason}")
                                total_failed += 1

                    # LLM 응답에 없는 파일은 failed 처리
                    for f in batch:
                        if f["id"] not in classified_ids:
                            set_status(f["id"], "failed", reason="LLM 응답에서 누락")
                            total_failed += 1

                except json.JSONDecodeError as e:
                    console.print(f"\n[red]JSON 파싱 오류: {e}[/red]")
                    for f in batch:
                        set_status(f["id"], "failed", reason=f"JSON 파싱 오류: {e}")
                    total_failed += len(batch)
                except Exception as e:
                    console.print(f"\n[red]API 오류: {e}[/red]")
                    for f in batch:
                        set_status(f["id"], "failed", reason=f"API 오류: {e}")
                    total_failed += len(batch)

                progress.update(task, advance=len(batch),
                                description=f"분류 중... 완료:{total_done} 실패:{total_failed}")

    console.print(f"\n[green]분류 완료: {total_done}개 성공, {total_failed}개 실패[/green]")
    console.print("'classify' 결과 확인 후 'execute' 명령으로 실제 이동하세요.")
