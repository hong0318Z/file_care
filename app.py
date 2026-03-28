#!/usr/bin/env python3
"""
file_care GUI - LLM 기반 파일 자동 분류 도구
실행: python app.py
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import json
import os
import sys
from pathlib import Path

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── 설정 파일 경로 ──────────────────────────────────────────
def _settings_path() -> Path:
    """항상 실행 파일(또는 스크립트)과 같은 폴더의 settings.json"""
    if getattr(sys, "frozen", False):
        # PyInstaller exe
        base = Path(sys.executable).resolve().parent
    else:
        # python app.py
        base = Path(os.path.abspath(__file__)).parent
    return base / "settings.json"


def load_settings() -> dict:
    p = _settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"github_token": "", "db_path": "file_care.db",
            "batch_size": 300, "model": "claude-sonnet-4-5"}


def save_settings(data: dict):
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 공통 스타일 ────────────────────────────────────────────
FONT_TITLE  = ("Malgun Gothic", 18, "bold")
FONT_LABEL  = ("Malgun Gothic", 12)
FONT_SMALL  = ("Malgun Gothic", 10)
FONT_MONO   = ("Consolas", 10)

COLOR_PENDING    = "#4A90D9"
COLOR_EXCLUDED   = "#888888"
COLOR_CLASSIFIED = "#F0A500"
COLOR_DONE       = "#4CAF50"
COLOR_FAILED     = "#E53935"

STATUS_KO = {
    "pending":    "대기",
    "excluded":   "제외",
    "classified": "분류완료",
    "done":       "이동완료",
    "failed":     "실패",
}

# ══════════════════════════════════════════════════════════
#  메인 앱 창
# ══════════════════════════════════════════════════════════
class FileCareApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("file_care  |  LLM 파일 자동 분류")
        self.geometry("1280x780")
        self.minsize(1000, 640)

        self._msg_q: queue.Queue = queue.Queue()
        self._current_frame = None

        self._build_layout()
        self._build_sidebar()
        self._show("dashboard")
        self.after(100, self._poll_queue)

    # ── 레이아웃 ──────────────────────────────────────────
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=190, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(20, weight=1)

        ctk.CTkLabel(sb, text="📁  file_care",
                     font=("Malgun Gothic", 16, "bold")).grid(
            row=0, column=0, padx=16, pady=(22, 18), sticky="w")

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        nav = [
            ("dashboard", "📊  대시보드"),
            ("scan",      "🔍  스캔"),
            ("files",     "📋  파일 목록"),
            ("classify",  "🤖  LLM 분류"),
            ("execute",   "✅  검토 & 이동"),
            ("settings",  "⚙️   설정"),
        ]
        for i, (key, label) in enumerate(nav):
            btn = ctk.CTkButton(
                sb, text=label, anchor="w", height=38,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                font=FONT_LABEL,
                command=lambda k=key: self._show(k),
            )
            btn.grid(row=i + 1, column=0, padx=8, pady=2, sticky="ew")
            self._nav_btns[key] = btn

    def _show(self, name: str):
        for w in self.grid_slaves(row=0, column=1):
            w.grid_forget()
        for k, b in self._nav_btns.items():
            b.configure(fg_color=("gray75", "gray25") if k == name else "transparent")

        FrameCls = {
            "dashboard": DashboardFrame,
            "scan":      ScanFrame,
            "files":     FilesFrame,
            "classify":  ClassifyFrame,
            "execute":   ExecuteFrame,
            "settings":  SettingsFrame,
        }[name]
        frame = FrameCls(self)
        frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self._current_frame = frame

    def _poll_queue(self):
        try:
            while True:
                msg = self._msg_q.get_nowait()
                if self._current_frame and hasattr(self._current_frame, "on_message"):
                    self._current_frame.on_message(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)


# ══════════════════════════════════════════════════════════
#  대시보드
# ══════════════════════════════════════════════════════════
class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkLabel(self, text="📊  대시보드", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 16))

        self._stat_cards: dict[str, ctk.CTkLabel] = {}
        cards = [
            ("pending",    "대기",    COLOR_PENDING),
            ("excluded",   "제외",    COLOR_EXCLUDED),
            ("classified", "분류완료", COLOR_CLASSIFIED),
            ("done",       "이동완료", COLOR_DONE),
            ("failed",     "실패",    COLOR_FAILED),
        ]
        for col, (status, label, color) in enumerate(cards):
            card = ctk.CTkFrame(self, corner_radius=12)
            card.grid(row=1, column=col, padx=6, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=label, font=FONT_SMALL,
                         text_color=color).grid(row=0, column=0, pady=(12, 2))
            cnt_lbl = ctk.CTkLabel(card, text="—", font=("Malgun Gothic", 28, "bold"),
                                   text_color=color)
            cnt_lbl.grid(row=1, column=0)
            size_lbl = ctk.CTkLabel(card, text="", font=FONT_SMALL,
                                    text_color="gray60")
            size_lbl.grid(row=2, column=0, pady=(0, 12))
            self._stat_cards[status] = (cnt_lbl, size_lbl)

        # 새로고침 버튼
        ctk.CTkButton(self, text="🔄  새로고침", width=120,
                      command=self._refresh).grid(
            row=2, column=0, columnspan=5, pady=16, sticky="w")

        # 최근 완료 파일 목록
        ctk.CTkLabel(self, text="최근 이동 완료 파일", font=FONT_LABEL).grid(
            row=3, column=0, columnspan=5, sticky="w", pady=(8, 4))

        self._log = ctk.CTkTextbox(self, height=300, font=FONT_MONO, state="disabled")
        self._log.grid(row=4, column=0, columnspan=5, sticky="nsew")
        self.grid_rowconfigure(4, weight=1)

        self._refresh()

    def _refresh(self):
        from db import get_stats, get_files_by_status
        stats = get_stats()
        for status, (cnt_lbl, size_lbl) in self._stat_cards.items():
            info = stats.get(status, {"count": 0, "bytes": 0})
            cnt_lbl.configure(text=str(info["count"]))
            size_lbl.configure(text=_fmt_size(info["bytes"]))

        done_files = get_files_by_status("done")[-50:]
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        if done_files:
            for f in reversed(done_files):
                self._log.insert("end",
                    f"✅  {f['filename']}  →  {f['target_folder'] or '?'}\n")
        else:
            self._log.insert("end", "아직 이동 완료된 파일이 없습니다.\n")
        self._log.configure(state="disabled")


# ══════════════════════════════════════════════════════════
#  스캔
# ══════════════════════════════════════════════════════════
class ScanFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="🔍  디렉토리 스캔", font=FONT_TITLE).grid(
            row=0, sticky="w", pady=(0, 16))

        # 경로 입력
        path_row = ctk.CTkFrame(self, fg_color="transparent")
        path_row.grid(row=1, sticky="ew", pady=4)
        path_row.grid_columnconfigure(0, weight=1)

        self._path_var = tk.StringVar()
        ctk.CTkEntry(path_row, textvariable=self._path_var,
                     placeholder_text="정리할 폴더 경로를 선택하세요",
                     font=FONT_LABEL, height=40).grid(
            row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(path_row, text="폴더 선택", width=110, height=40,
                      command=self._pick_folder).grid(row=0, column=1)

        # 옵션
        opt_row = ctk.CTkFrame(self, fg_color="transparent")
        opt_row.grid(row=2, sticky="w", pady=8)
        self._recursive = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(opt_row, text="하위 폴더도 재귀 스캔",
                        variable=self._recursive,
                        font=FONT_LABEL).grid(row=0, column=0, padx=(0, 20))

        # 스캔 버튼
        self._scan_btn = ctk.CTkButton(self, text="🔍  스캔 시작", height=44,
                                       font=("Malgun Gothic", 13, "bold"),
                                       command=self._run_scan)
        self._scan_btn.grid(row=3, sticky="ew", pady=8)

        # 로그
        ctk.CTkLabel(self, text="스캔 로그", font=FONT_LABEL).grid(
            row=4, sticky="w", pady=(12, 4))
        self._log = ctk.CTkTextbox(self, font=FONT_MONO, state="disabled")
        self._log.grid(row=5, sticky="nsew")
        self.grid_rowconfigure(5, weight=1)

    def _pick_folder(self):
        path = filedialog.askdirectory(title="정리할 폴더 선택")
        if path:
            self._path_var.set(path)

    def _log_write(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _run_scan(self):
        path = self._path_var.get().strip()
        if not path:
            messagebox.showwarning("경로 없음", "폴더를 선택해주세요.")
            return
        if not Path(path).exists():
            messagebox.showerror("오류", f"경로가 존재하지 않습니다:\n{path}")
            return

        self._scan_btn.configure(state="disabled", text="스캔 중...")
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

        def worker():
            import io, contextlib
            from scanner import scan as do_scan
            buf = io.StringIO()
            try:
                # stdout 캡처 없이 직접 콜백 방식으로 진행
                self.after(0, self._log_write, f"▶ 스캔 시작: {path}")
                do_scan(path, recursive=self._recursive.get(),
                        log_callback=lambda msg: self.after(0, self._log_write, msg))
                self.after(0, self._log_write, "✅ 스캔 완료!")
            except Exception as e:
                self.after(0, self._log_write, f"❌ 오류: {e}")
            finally:
                self.after(0, lambda: self._scan_btn.configure(
                    state="normal", text="🔍  스캔 시작"))

        threading.Thread(target=worker, daemon=True).start()


# ══════════════════════════════════════════════════════════
#  파일 목록
# ══════════════════════════════════════════════════════════
class FilesFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="📋  파일 목록", font=FONT_TITLE).grid(
            row=0, sticky="w", pady=(0, 10))

        # 필터 바
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=1, sticky="ew", pady=4)

        self._filter_var = tk.StringVar(value="all")
        statuses = [("전체", "all"), ("대기", "pending"), ("제외", "excluded"),
                    ("분류완료", "classified"), ("이동완료", "done"), ("실패", "failed")]
        for i, (label, val) in enumerate(statuses):
            ctk.CTkRadioButton(filter_row, text=label, variable=self._filter_var,
                               value=val, font=FONT_SMALL,
                               command=self._load).grid(
                row=0, column=i, padx=8)

        # 검색
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._load())
        ctk.CTkEntry(filter_row, textvariable=self._search_var,
                     placeholder_text="파일명 검색...",
                     width=200, height=32, font=FONT_SMALL).grid(
            row=0, column=len(statuses) + 1, padx=(20, 0))

        # 액션 버튼
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, sticky="ew", pady=4)
        ctk.CTkButton(btn_row, text="✖  선택 제외", width=120, height=34,
                      fg_color="#555", hover_color="#444",
                      command=self._exclude_selected).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(btn_row, text="↩  선택 복원", width=120, height=34,
                      fg_color="#2a5e8a", hover_color="#1e4d73",
                      command=self._include_selected).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(btn_row, text="🗑  DB 초기화", width=120, height=34,
                      fg_color="#7b1f1f", hover_color="#5c1515",
                      command=self._reset_db).grid(row=0, column=2, padx=(0, 8))
        self._sel_label = ctk.CTkLabel(btn_row, text="", font=FONT_SMALL,
                                       text_color="gray60")
        self._sel_label.grid(row=0, column=3, padx=12)

        # 트리뷰 (파일 테이블)
        tree_frame = ctk.CTkFrame(self)
        tree_frame.grid(row=3, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview",
                         background="#2b2b2b", foreground="white",
                         fieldbackground="#2b2b2b", rowheight=26,
                         font=("Malgun Gothic", 10))
        style.configure("Dark.Treeview.Heading",
                         background="#1a1a2e", foreground="white",
                         font=("Malgun Gothic", 10, "bold"))
        style.map("Dark.Treeview",
                  background=[("selected", "#3a7ebf")])

        cols = ("id", "filename", "ext", "size", "status", "target")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   style="Dark.Treeview", selectmode="extended")
        heads = [("id","ID",50), ("filename","파일명",320), ("ext","확장자",70),
                 ("size","크기",90), ("status","상태",80), ("target","대상 폴더",200)]
        for col, label, width in heads:
            self._tree.heading(col, text=label,
                               command=lambda c=col: self._sort(c))
            self._tree.column(col, width=width, minwidth=40)

        sb_y = ttk.Scrollbar(tree_frame, orient="vertical",
                              command=self._tree.yview)
        sb_x = ttk.Scrollbar(tree_frame, orient="horizontal",
                              command=self._tree.xview)
        self._tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # 태그 색상
        self._tree.tag_configure("pending",    foreground=COLOR_PENDING)
        self._tree.tag_configure("excluded",   foreground=COLOR_EXCLUDED)
        self._tree.tag_configure("classified", foreground=COLOR_CLASSIFIED)
        self._tree.tag_configure("done",       foreground=COLOR_DONE)
        self._tree.tag_configure("failed",     foreground=COLOR_FAILED)

        self._sort_col = "id"
        self._sort_asc = True
        self._load()

    def _load(self):
        from db import get_all_files, get_files_by_status
        status = self._filter_var.get()
        search = self._search_var.get().strip().lower()

        if status == "all":
            files = get_all_files()
        else:
            files = get_files_by_status(status)

        if search:
            files = [f for f in files if search in f["filename"].lower()]

        self._tree.delete(*self._tree.get_children())
        for f in files:
            self._tree.insert("", "end",
                iid=str(f["id"]),
                values=(f["id"], f["filename"], f["extension"] or "-",
                        _fmt_size(f["size_bytes"]),
                        STATUS_KO.get(f["status"], f["status"]),
                        f["target_folder"] or "-"),
                tags=(f["status"],))

        self._sel_label.configure(text=f"총 {len(files)}개")

    def _on_select(self, _=None):
        n = len(self._tree.selection())
        self._sel_label.configure(text=f"{n}개 선택" if n else
                                  f"총 {len(self._tree.get_children())}개")

    def _exclude_selected(self):
        sel = [int(i) for i in self._tree.selection()]
        if not sel:
            messagebox.showinfo("선택 없음", "제외할 파일을 선택하세요.")
            return
        from db import set_excluded_by_ids
        set_excluded_by_ids(sel)
        self._load()

    def _include_selected(self):
        sel = [int(i) for i in self._tree.selection()]
        if not sel:
            messagebox.showinfo("선택 없음", "복원할 파일을 선택하세요.")
            return
        from db import set_pending_by_ids
        set_pending_by_ids(sel)
        self._load()

    def _sort(self, col):
        col_map = {"id": "id", "filename": "filename", "ext": "extension",
                   "size": "size_bytes", "status": "status", "target": "target_folder"}
        key = col_map.get(col, col)
        items = [(self._tree.set(iid, col), iid) for iid in self._tree.get_children()]
        items.sort(reverse=not self._sort_asc)
        for i, (_, iid) in enumerate(items):
            self._tree.move(iid, "", i)
        self._sort_asc = not self._sort_asc

    def _reset_db(self):
        if not messagebox.askyesno("DB 초기화",
                "DB의 모든 파일 목록을 삭제합니다.\n실제 파일은 이동/삭제되지 않습니다.\n\n계속하시겠습니까?"):
            return
        try:
            from db import reset_db
            reset_db()
            self._load()
            messagebox.showinfo("완료", "DB가 초기화되었습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"초기화 실패: {e}")


# ══════════════════════════════════════════════════════════
#  LLM 분류
# ══════════════════════════════════════════════════════════
class ClassifyFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text="🤖  LLM 분류", font=FONT_TITLE).grid(
            row=0, sticky="w", pady=(0, 10))

        # ── 토큰 상태 ──
        settings = load_settings()
        token = settings.get("github_token", "")
        info_text = "✅ GitHub 토큰 설정됨" if token else "⚠️ 토큰 미설정 — [설정] 탭에서 입력하세요"
        ctk.CTkLabel(self, text=info_text, font=FONT_SMALL,
                     text_color=COLOR_DONE if token else COLOR_FAILED).grid(
            row=1, sticky="w", pady=(0, 8))

        # ── 스캔된 디렉토리 목록 ──
        top = ctk.CTkFrame(self)
        top.grid(row=2, sticky="ew", pady=(0, 8))
        top.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(top, fg_color="transparent")
        hdr.grid(row=0, sticky="ew", padx=10, pady=(8, 4))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="스캔된 폴더 목록  (분류할 폴더를 선택하세요)",
                     font=FONT_LABEL).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="🔄", width=32, height=28,
                      command=self._reload_dirs).grid(row=0, column=1)

        dir_frame = ctk.CTkFrame(top, height=160)
        dir_frame.grid(row=1, sticky="ew", padx=10, pady=(0, 8))
        dir_frame.grid_columnconfigure(0, weight=1)
        dir_frame.grid_rowconfigure(0, weight=1)
        dir_frame.grid_propagate(False)

        self._dir_tree = ttk.Treeview(dir_frame,
                                       columns=("path", "pending", "total"),
                                       show="headings", style="Dark.Treeview",
                                       selectmode="extended", height=5)
        self._dir_tree.heading("path",    text="폴더 경로")
        self._dir_tree.heading("pending", text="대기")
        self._dir_tree.heading("total",   text="전체")
        self._dir_tree.column("path",    width=520, minwidth=200)
        self._dir_tree.column("pending", width=60,  anchor="center")
        self._dir_tree.column("total",   width=60,  anchor="center")
        dsb = ttk.Scrollbar(dir_frame, orient="vertical", command=self._dir_tree.yview)
        self._dir_tree.configure(yscrollcommand=dsb.set)
        self._dir_tree.grid(row=0, column=0, sticky="nsew")
        dsb.grid(row=0, column=1, sticky="ns")

        # 전체 선택 / 선택 해제
        sel_row = ctk.CTkFrame(top, fg_color="transparent")
        sel_row.grid(row=2, sticky="w", padx=10, pady=(0, 8))
        ctk.CTkButton(sel_row, text="전체 선택", width=90, height=28,
                      command=lambda: self._dir_tree.selection_set(
                          self._dir_tree.get_children())).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(sel_row, text="선택 해제", width=90, height=28,
                      fg_color="#555", hover_color="#444",
                      command=lambda: self._dir_tree.selection_remove(
                          self._dir_tree.get_children())).grid(row=0, column=1)

        # ── 분류 버튼 + 진행바 ──
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=3, sticky="ew")
        ctrl.grid_columnconfigure(0, weight=1)

        self._cls_btn = ctk.CTkButton(
            ctrl, text="🤖  선택한 폴더 LLM 분류 시작", height=44,
            font=("Malgun Gothic", 13, "bold"), command=self._run)
        self._cls_btn.grid(row=0, sticky="ew", pady=(0, 6))

        self._progress = ctk.CTkProgressBar(ctrl)
        self._progress.set(0)
        self._progress.grid(row=1, sticky="ew", pady=(0, 4))

        self._status_lbl = ctk.CTkLabel(ctrl, text="", font=FONT_SMALL,
                                         text_color="gray60")
        self._status_lbl.grid(row=2, sticky="w")

        # ── 실시간 로그 ──
        ctk.CTkLabel(self, text="실시간 로그  (API 요청/응답 포함)", font=FONT_LABEL).grid(
            row=4, sticky="w", pady=(10, 4))
        self._log = ctk.CTkTextbox(self, font=FONT_MONO, state="disabled")
        self._log.grid(row=5, sticky="nsew")
        self.grid_rowconfigure(5, weight=1)

        self._reload_dirs()

    def _reload_dirs(self):
        from db import get_scanned_dirs
        self._dir_tree.delete(*self._dir_tree.get_children())
        dirs = get_scanned_dirs()
        for d in dirs:
            pending = d["pending"]
            total   = d["total"]
            tag = "pending" if pending > 0 else "done"
            self._dir_tree.insert("", "end",
                values=(d["parent_dir"], pending, total), tags=(tag,))
        self._dir_tree.tag_configure("pending", foreground=COLOR_PENDING)
        self._dir_tree.tag_configure("done",    foreground=COLOR_EXCLUDED)

    def _log_write(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _run(self):
        import config
        token = config.GITHUB_TOKEN
        if not token:
            messagebox.showerror("토큰 없음",
                "GitHub 토큰이 설정되지 않았습니다.\n[설정] 탭에서 토큰을 입력하고 저장하세요.")
            return

        selected = self._dir_tree.selection()
        if not selected:
            messagebox.showwarning("선택 없음", "분류할 폴더를 목록에서 선택하세요.\n(Ctrl+클릭으로 다중 선택 가능)")
            return

        selected_dirs = [self._dir_tree.item(s)["values"][0] for s in selected]

        from db import get_files_by_status
        all_pending = []
        for d in selected_dirs:
            all_pending += get_files_by_status("pending", d)

        if not all_pending:
            messagebox.showinfo("없음", "선택한 폴더에 분류할 파일이 없습니다.\n(pending 상태 파일 없음)")
            return

        self._progress.set(0)
        self._cls_btn.configure(state="disabled", text="분류 중...")
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._log_write(f"▶ 분류 시작: {len(selected_dirs)}개 폴더, {len(all_pending)}개 파일")
        self._log_write(f"▶ 모델: {config.MODEL}")
        self._log_write(f"▶ API: {config.COPILOT_BASE_URL}/chat/completions")
        self._log_write("─" * 60)

        def worker():
            from classifier import classify as do_classify
            for d in selected_dirs:
                self.after(0, self._log_write, f"\n📁 처리 중: {d}")
                do_classify(d,
                            progress_callback=self._on_progress,
                            log_callback=lambda msg: self.after(0, self._log_write, msg))
            self.after(0, self._on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, done: int, total: int, msg: str):
        pct = done / total if total else 0
        self.after(0, lambda p=pct: self._progress.set(p))
        self.after(0, lambda m=f"{done}/{total}  {msg}": self._status_lbl.configure(text=m))

    def _on_done(self):
        self._cls_btn.configure(state="normal", text="🤖  선택한 폴더 LLM 분류 시작")
        self._progress.set(1)
        self._reload_dirs()
        self._log_write("\n" + "─" * 60)
        self._log_write("✅ 완료!  [검토 & 이동] 탭에서 결과를 확인하세요.")


# ══════════════════════════════════════════════════════════
#  검토 & 실행
# ══════════════════════════════════════════════════════════
class ExecuteFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="✅  검토 & 파일 이동", font=FONT_TITLE).grid(
            row=0, sticky="w", pady=(0, 10))

        # 버튼 행
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, sticky="ew", pady=6)
        ctk.CTkButton(btn_row, text="🔄 목록 새로고침", width=140, height=38,
                      command=self._load).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(btn_row, text="👁  미리보기 (Dry-run)", width=160, height=38,
                      fg_color="#555", hover_color="#444",
                      command=self._dry_run).grid(row=0, column=1, padx=(0, 8))
        self._exec_btn = ctk.CTkButton(
            btn_row, text="🚀  파일 이동 실행", width=150, height=38,
            fg_color="#2e7d32", hover_color="#1b5e20",
            command=self._execute)
        self._exec_btn.grid(row=0, column=2, padx=(0, 8))
        ctk.CTkButton(btn_row, text="✖ 선택 제외", width=110, height=38,
                      fg_color="#555", hover_color="#444",
                      command=self._exclude_selected).grid(row=0, column=3)

        self._count_lbl = ctk.CTkLabel(btn_row, text="", font=FONT_SMALL,
                                       text_color="gray60")
        self._count_lbl.grid(row=0, column=4, padx=16)

        # 트리뷰
        tree_frame = ctk.CTkFrame(self)
        tree_frame.grid(row=2, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        cols = ("id", "filename", "target", "reason")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   style="Dark.Treeview", selectmode="extended")
        for col, label, w in [("id","ID",50),("filename","파일명",280),
                               ("target","→ 대상 폴더",200),("reason","LLM 이유",320)]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=w, minwidth=40)

        sb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        # 로그
        self._log = ctk.CTkTextbox(self, height=140, font=FONT_MONO, state="disabled")
        self._log.grid(row=3, sticky="ew", pady=(8, 0))

        self._load()

    def _load(self):
        from db import get_files_by_status
        files = get_files_by_status("classified")
        self._tree.delete(*self._tree.get_children())
        for f in files:
            self._tree.insert("", "end", iid=str(f["id"]),
                values=(f["id"], f["filename"],
                        f["target_folder"] or "-",
                        f["llm_reason"] or "-"))
        self._count_lbl.configure(text=f"분류완료 {len(files)}개")

    def _log_write(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _exclude_selected(self):
        sel = [int(i) for i in self._tree.selection()]
        if not sel:
            messagebox.showinfo("선택 없음", "제외할 항목을 선택하세요.")
            return
        from db import set_excluded_by_ids
        set_excluded_by_ids(sel)
        self._load()

    def _dry_run(self):
        from db import get_files_by_status
        files = get_files_by_status("classified")
        if not files:
            messagebox.showinfo("없음", "이동할 파일이 없습니다.")
            return
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._log_write(f"[ DRY-RUN ] 실제 이동 없이 미리보기 ({len(files)}개)")
        for f in files:
            self._log_write(
                f"  {f['filename']}  →  {f['target_folder']}/   ({f['llm_reason']})")

    def _execute(self):
        from db import get_files_by_status
        files = get_files_by_status("classified")
        if not files:
            messagebox.showinfo("없음", "이동할 파일이 없습니다.")
            return
        if not messagebox.askyesno("확인",
                f"{len(files)}개 파일을 실제로 이동하시겠습니까?\n"
                "이 작업은 되돌리기 어렵습니다."):
            return

        self._exec_btn.configure(state="disabled", text="이동 중...")
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

        def worker():
            from executor import execute as do_execute
            do_execute(log_callback=lambda msg: self.after(0, self._log_write, msg))
            self.after(0, self._load)
            self.after(0, lambda: self._exec_btn.configure(
                state="normal", text="🚀  파일 이동 실행"))

        threading.Thread(target=worker, daemon=True).start()


# ══════════════════════════════════════════════════════════
#  설정
# ══════════════════════════════════════════════════════════
class SettingsFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="⚙️  설정", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 20))

        settings = load_settings()

        # ── GitHub Token ──
        ctk.CTkLabel(self, text="GitHub Token", font=FONT_LABEL).grid(
            row=1, column=0, sticky="w", pady=8, padx=(0, 16))
        self._token_var = tk.StringVar(value=settings.get("github_token", ""))
        self._token_entry = ctk.CTkEntry(self, textvariable=self._token_var,
                                         show="*", height=40, font=FONT_LABEL)
        self._token_entry.grid(row=1, column=1, sticky="ew", pady=8, padx=(0, 8))

        # 연결 테스트 버튼
        self._test_btn = ctk.CTkButton(self, text="🔌 연결 테스트", width=130, height=40,
                                       fg_color="#1a4a6e", hover_color="#163d5a",
                                       command=self._test_connection)
        self._test_btn.grid(row=1, column=2, pady=8)

        ctk.CTkLabel(self,
            text="GitHub Personal Access Token (repo + copilot 권한 필요)",
            font=FONT_SMALL, text_color="gray60").grid(
            row=2, column=1, columnspan=2, sticky="w")

        self._show_token = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="토큰 표시", variable=self._show_token,
                        font=FONT_SMALL,
                        command=lambda: self._token_entry.configure(
                            show="" if self._show_token.get() else "*"
                        )).grid(row=3, column=1, sticky="w", pady=2)

        # ── 연결 테스트 결과 ──
        self._test_lbl = ctk.CTkLabel(self, text="", font=FONT_LABEL, wraplength=600)
        self._test_lbl.grid(row=4, column=0, columnspan=3, sticky="w", pady=4)

        # ── 모델명 ──
        ctk.CTkLabel(self, text="모델명", font=FONT_LABEL).grid(
            row=5, column=0, sticky="w", pady=8, padx=(0, 16))
        self._model_var = tk.StringVar(value=settings.get("model", "claude-sonnet-4.5"))
        ctk.CTkEntry(self, textvariable=self._model_var,
                     height=40, font=FONT_LABEL).grid(
            row=5, column=1, sticky="ew", pady=8, padx=(0, 8))
        self._list_btn = ctk.CTkButton(self, text="📋 지원 모델 조회", width=140, height=40,
                                       fg_color="#2d4a22", hover_color="#1f3318",
                                       command=self._list_models)
        self._list_btn.grid(row=5, column=2, pady=8)
        ctk.CTkLabel(self,
            text="모델명을 모르면 [지원 모델 조회] 버튼으로 확인하세요",
            font=FONT_SMALL, text_color="gray60").grid(
            row=6, column=1, columnspan=2, sticky="w")

        # 모델 목록 표시
        self._models_lbl = ctk.CTkLabel(self, text="", font=FONT_SMALL,
                                        text_color="#aaaaaa", wraplength=620,
                                        justify="left")
        self._models_lbl.grid(row=7, column=0, columnspan=3, sticky="w", pady=2)

        # ── DB 경로 ──
        ctk.CTkLabel(self, text="DB 파일 경로", font=FONT_LABEL).grid(
            row=8, column=0, sticky="w", pady=8, padx=(0, 16))
        self._db_var = tk.StringVar(value=settings.get("db_path", "file_care.db"))
        ctk.CTkEntry(self, textvariable=self._db_var,
                     height=40, font=FONT_LABEL).grid(
            row=8, column=1, sticky="ew", pady=8, padx=(0, 8))

        # ── 배치 크기 ──
        ctk.CTkLabel(self, text="배치 크기 (파일 수/요청)", font=FONT_LABEL).grid(
            row=9, column=0, sticky="w", pady=8, padx=(0, 16))
        self._batch_var = tk.StringVar(value=str(settings.get("batch_size", 300)))
        ctk.CTkEntry(self, textvariable=self._batch_var,
                     width=100, height=40, font=FONT_LABEL).grid(
            row=9, column=1, sticky="w", pady=8)

        # ── 저장 버튼 ──
        ctk.CTkButton(self, text="💾  설정 저장", height=44,
                      font=("Malgun Gothic", 13, "bold"),
                      command=self._save).grid(
            row=10, column=0, columnspan=3, sticky="w", pady=20)

        self._result_lbl = ctk.CTkLabel(self, text="", font=FONT_LABEL)
        self._result_lbl.grid(row=11, column=0, columnspan=3, sticky="w")

    def _save(self):
        token = self._token_var.get().strip()
        model = self._model_var.get().strip() or "claude-sonnet-4-5"
        db_path = self._db_var.get().strip() or "file_care.db"
        try:
            batch = int(self._batch_var.get().strip())
        except ValueError:
            batch = 300

        save_settings({
            "github_token": token,
            "model": model,
            "db_path": db_path,
            "batch_size": batch,
        })

        # 런타임 config 즉시 반영
        import config
        config.GITHUB_TOKEN = token
        config.MODEL = model
        config.DB_PATH = db_path
        config.BATCH_SIZE = batch
        os.environ["GITHUB_TOKEN"] = token

        self._result_lbl.configure(text="✅ 저장 완료!", text_color=COLOR_DONE)
        self.after(3000, lambda: self._result_lbl.configure(text=""))

    def _test_connection(self):
        token = self._token_var.get().strip()
        model = self._model_var.get().strip() or "claude-sonnet-4.5"
        if not token:
            self._test_lbl.configure(
                text="⚠ 토큰을 먼저 입력하세요.", text_color=COLOR_FAILED)
            return

        self._test_btn.configure(state="disabled", text="테스트 중...")
        self._test_lbl.configure(text="연결 확인 중...", text_color="gray60")

        def worker():
            # finally 가 항상 실행되도록 worker 전체를 try-finally 로 감쌈
            try:
                import httpx
                import config
                url = f"{config.COPILOT_BASE_URL}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Copilot-Integration-Id": "vscode-chat",
                }
                payload = {
                    "model": model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "hi"}],
                }
                self.after(0, lambda: self._test_lbl.configure(
                    text=f"요청 전송 중...  {url}", text_color="gray60"))
                r = httpx.post(url, headers=headers, json=payload, timeout=15.0)
                if r.status_code == 200:
                    data = r.json()
                    reply = data["choices"][0]["message"]["content"]
                    self.after(0, lambda rp=reply: self._test_lbl.configure(
                        text=f"✅ 연결 성공!  모델: {model}  응답: {rp[:80]}",
                        text_color=COLOR_DONE))
                else:
                    body = r.text[:300]
                    hint = ""
                    if "model_not_supported" in body or r.status_code == 400:
                        hint = "\n→ [지원 모델 조회] 버튼으로 정확한 모델명을 확인하세요."
                    elif r.status_code == 401:
                        hint = "\n→ 토큰이 올바르지 않거나 Copilot 권한이 없습니다."
                    sc = r.status_code
                    self.after(0, lambda b=body, h=hint, s=sc: self._test_lbl.configure(
                        text=f"❌ HTTP {s}: {b}{h}", text_color=COLOR_FAILED))
            except Exception as e:
                msg = str(e)
                if "timed out" in msg.lower() or "timeout" in msg.lower():
                    msg = "타임아웃 (15초 초과) — 네트워크를 확인하세요."
                self.after(0, lambda m=msg: self._test_lbl.configure(
                    text=f"❌ {m[:250]}", text_color=COLOR_FAILED))
            finally:
                self.after(0, lambda: self._test_btn.configure(
                    state="normal", text="🔌 연결 테스트"))

        threading.Thread(target=worker, daemon=True).start()

    def _list_models(self):
        token = self._token_var.get().strip()
        if not token:
            self._models_lbl.configure(
                text="⚠ 토큰을 먼저 입력하세요.", text_color=COLOR_FAILED)
            return

        self._list_btn.configure(state="disabled", text="조회 중...")
        self._models_lbl.configure(text="모델 목록 가져오는 중...", text_color="gray60")

        def worker():
            try:
                import httpx
                import config
                r = httpx.get(
                    f"{config.COPILOT_BASE_URL}/models",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Copilot-Integration-Id": "vscode-chat",
                    },
                    timeout=15.0,
                )
                if r.status_code == 200:
                    data = r.json()
                    models = data.get("data", data) if isinstance(data, dict) else data
                    ids = [m.get("id", str(m)) for m in models]
                    claude_ids = [m for m in ids if "claude" in m.lower()]
                    other_ids  = [m for m in ids if "claude" not in m.lower()]
                    lines = []
                    if claude_ids:
                        lines.append("🟣 Claude: " + "  |  ".join(claude_ids))
                    if other_ids:
                        lines.append("⚪ 기타: " + "  |  ".join(other_ids[:10]))
                    msg = "\n".join(lines) if lines else f"원본 응답: {r.text[:400]}"
                    self.after(0, lambda m=msg: self._models_lbl.configure(
                        text=m, text_color="#cccccc"))
                else:
                    t = r.text[:300]
                    s = r.status_code
                    self.after(0, lambda tt=t, ss=s: self._models_lbl.configure(
                        text=f"HTTP {ss}: {tt}", text_color=COLOR_FAILED))
            except Exception as e:
                err = str(e)
                self.after(0, lambda m=err: self._models_lbl.configure(
                    text=f"오류: {m[:200]}", text_color=COLOR_FAILED))
            finally:
                self.after(0, lambda: self._list_btn.configure(
                    state="normal", text="📋 지원 모델 조회"))

        threading.Thread(target=worker, daemon=True).start()


# ══════════════════════════════════════════════════════════
#  유틸
# ══════════════════════════════════════════════════════════
def _fmt_size(b):
    if not b:
        return "-"
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


# ══════════════════════════════════════════════════════════
#  진입점
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import config
    from db import init_db

    # settings.json → config 런타임 반영
    s = load_settings()
    if s.get("github_token"):
        config.GITHUB_TOKEN = s["github_token"]
        os.environ["GITHUB_TOKEN"] = s["github_token"]
    if s.get("model"):
        config.MODEL = s["model"]
    if s.get("db_path"):
        config.DB_PATH = s["db_path"]
    if s.get("batch_size"):
        config.BATCH_SIZE = s["batch_size"]

    init_db()
    app = FileCareApp()
    app.mainloop()
