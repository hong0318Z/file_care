import json
from openai import OpenAI
from config import GITHUB_TOKEN, COPILOT_BASE_URL, MODEL, MAX_TOKENS, BATCH_SIZE
from db import get_files_by_status, get_folders_by_parent, set_status
from collections import defaultdict


def _build_folder_context(parent_dir: str) -> str:
    folders = get_folders_by_parent(parent_dir)
    if not folders:
        return "기존 폴더 없음 (새 폴더 생성 필요)"
    lines = ["[기존 폴더 구조]"]
    for f in folders:
        samples = json.loads(f["sample_files"]) if f["sample_files"] else []
        sample_str = ", ".join(samples[:10]) if samples else "비어있음"
        lines.append(f"  {f['name']}/ ({f['file_count']}개 파일) 예: {sample_str}")
    return "\n".join(lines)


def _build_prompt(folder_context: str, files_batch: list) -> str:
    file_list = "\n".join(
        f"  [{f['id']}] {f['filename']} ({f['extension'] or '확장자없음'}, {_fmt_size(f['size_bytes'])})"
        for f in files_batch
    )
    return f"""당신은 파일 정리 전문가입니다. 기존 폴더 구조를 참고하여 각 파일을 어느 폴더에 넣을지 결정하세요.

{folder_context}

[분류할 파일 목록]
{file_list}

## 분류 규칙
1. 기존 폴더가 있으면 이름과 내용을 참고해 가장 적합한 폴더를 선택하세요.
2. 맞는 폴더가 없으면 파일명/확장자로 추측하여 새 폴더명을 제안하세요.
   - 업무 관련 (기획서, 보고서, 계약, 제안, 회의 등 단어 포함): 업무
   - 이미지 (.jpg, .png, .gif, .webp, .heic 등): 이미지
   - 영상 (.mp4, .mov, .avi, .mkv 등): 영상
   - 문서 (.pdf, .docx, .xlsx, .pptx, .hwp 등): 문서
   - 압축 (.zip, .rar, .7z 등): 압축파일
   - 코드 (.py, .js, .ts, .java, .cpp 등): 코드
   - 기타: 기타
3. 확신이 없어도 최선을 다해 추측하세요. null은 정말 판단 불가한 경우만 사용하세요.

## 응답 형식 (JSON만 출력, 다른 텍스트 없음)
{{"results": [{{"id": 파일ID, "target_folder": "폴더명", "reason": "한 줄 이유"}}, ...]}}
"""


def _fmt_size(b):
    if b is None:
        return "?"
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.0f}{u}"
        b /= 1024
    return f"{b:.1f}TB"


def classify(parent_dir: str = None, progress_callback=None, log_callback=None):
    """
    pending 상태의 파일들을 LLM으로 분류.
    progress_callback(done, total, msg)
    log_callback(str)
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    import config
    token = config.GITHUB_TOKEN
    if not token:
        log("❌ 오류: GITHUB_TOKEN이 설정되지 않았습니다.")
        log("  [설정] 탭에서 GitHub 토큰을 입력해주세요.")
        return

    client = OpenAI(api_key=token, base_url=config.COPILOT_BASE_URL)

    pending_files = get_files_by_status("pending", parent_dir)
    if not pending_files:
        log("⚠ 분류할 파일이 없습니다. (pending 상태 없음)")
        return

    total = len(pending_files)
    log(f"▶ 분류 시작: {total}개 파일")

    groups = defaultdict(list)
    for f in pending_files:
        groups[f["parent_dir"]].append(f)

    done = 0
    failed = 0

    for pdir, files in groups.items():
        folder_context = _build_folder_context(pdir)
        batch_size = config.BATCH_SIZE

        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            prompt = _build_prompt(folder_context, batch)

            try:
                response = client.chat.completions.create(
                    model=config.MODEL,
                    max_tokens=config.MAX_TOKENS,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw = response.choices[0].message.content.strip()

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
                            log(f"  ✅ [{fid}] {id_map[fid]['filename']}  →  {target}")
                            done += 1
                        else:
                            set_status(fid, "failed", reason=f"판단 불가: {reason}")
                            log(f"  ⚠ [{fid}] {id_map[fid]['filename']}  판단 불가")
                            failed += 1

                for f in batch:
                    if f["id"] not in classified_ids:
                        set_status(f["id"], "failed", reason="LLM 응답 누락")
                        failed += 1

            except json.JSONDecodeError as e:
                log(f"  ❌ JSON 파싱 오류: {e}")
                for f in batch:
                    set_status(f["id"], "failed", reason=f"JSON 오류: {e}")
                failed += len(batch)
            except Exception as e:
                log(f"  ❌ API 오류: {e}")
                for f in batch:
                    set_status(f["id"], "failed", reason=f"API 오류: {e}")
                failed += len(batch)

            processed = done + failed
            if progress_callback:
                progress_callback(processed, total,
                                  f"완료:{done}  실패:{failed}")

    log(f"\n✅ 분류 완료  |  성공: {done}개  실패: {failed}개")
