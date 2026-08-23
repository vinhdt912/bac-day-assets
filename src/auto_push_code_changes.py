"""
Tự động commit và push file trong images/ và videos/ lúc 02:00 mỗi ngày.

Chạy:
  uv run python src/auto_push_code_changes.py
  uv run python src/auto_push_code_changes.py --now   # đẩy ngay, rồi vào vòng 02:00
"""

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PUSH_HOUR = 2
PUSH_MINUTE = 0
REMOTE = "origin"
SYNC_PATHS = ("images", "videos")
REPO_ROOT = Path(__file__).resolve().parent.parent


def run_git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def wait_until_datetime(target: datetime):
    now = datetime.now()
    if now >= target:
        return
    wait_seconds = (target - now).total_seconds()
    print(f"🕒 Bây giờ: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(
        f"⏳ Chờ đến {target.strftime('%Y-%m-%d %H:%M:%S')} "
        f"({wait_seconds / 60:.0f} phút)..."
    )
    time.sleep(wait_seconds)


def next_push_time(now=None):
    now = now or datetime.now()
    target = now.replace(
        hour=PUSH_HOUR, minute=PUSH_MINUTE, second=0, microsecond=0
    )
    if now >= target:
        target += timedelta(days=1)
    return target


def current_branch():
    result = run_git("rev-parse", "--abbrev-ref", "HEAD")
    if result.returncode != 0:
        print(result.stderr.strip() or "Lỗi: không đọc được tên nhánh.")
        return None
    return result.stdout.strip()


def commit_local_changes():
    reset = run_git("reset")
    if reset.returncode != 0:
        print(reset.stderr.strip() or "Lỗi: git reset thất bại.")
        return False

    add = run_git("add", "--", *SYNC_PATHS)
    if add.returncode != 0:
        print(add.stderr.strip() or "Lỗi: git add thất bại.")
        return False

    staged = run_git("diff", "--cached", "--quiet")
    if staged.returncode == 0:
        print("Không có thay đổi mới trong images/ hoặc videos/.")
        return False

    staged_list = run_git("diff", "--cached", "--name-only")
    print("Sẽ commit:")
    print(staged_list.stdout.strip() or "(không có file)")

    message = f"auto: sync media {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    commit = run_git("commit", "-m", message)
    if commit.returncode != 0:
        print(commit.stderr.strip() or "Lỗi: git commit thất bại.")
        return False

    print(f"Đã commit: {message}")
    return True


def has_unpushed_commits():
    result = run_git("rev-list", "--count", "@{u}..HEAD")
    if result.returncode != 0:
        return True
    return int((result.stdout or "0").strip() or "0") > 0


def push_to_remote():
    branch = current_branch()
    if not branch:
        return False

    if not has_unpushed_commits():
        print("Không có commit nào chưa push.")
        return True

    print(f"Đang push nhánh {branch} lên {REMOTE}...")
    push = run_git("push", "-u", REMOTE, branch)
    if push.returncode != 0:
        print(push.stderr.strip() or "Lỗi: git push thất bại.")
        return False

    print(push.stdout.strip() or f"Đã push {branch} lên {REMOTE}.")
    return True


def push_code_changes():
    """Commit thay đổi trong images/ và videos/ rồi push lên remote."""
    print(f"\n📦 Repo: {REPO_ROOT}")
    print(f"Chỉ đồng bộ: {', '.join(SYNC_PATHS)}")
    print(f"Bây giờ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    status = run_git("status", "--porcelain")
    if status.returncode != 0:
        print(status.stderr.strip() or "Lỗi: không phải git repo.")
        return False

    committed = commit_local_changes()
    if not committed and not has_unpushed_commits():
        print("Không có media mới để đẩy.")
        return True
    return push_to_remote()


def run_daily_push_cycle():
    """Chờ đến 02:00 mỗi ngày rồi gọi push_code_changes()."""
    while True:
        target = next_push_time()
        print(
            f"📅 Lịch push tiếp theo: {target.strftime('%d/%m %H:%M')}"
        )
        wait_until_datetime(target)
        ok = push_code_changes()
        if ok:
            print("🎉 Đã đồng bộ code xong.")
        else:
            print("❌ Đồng bộ code thất bại, sẽ thử lại vào 02:00 ngày mai.")


if __name__ == "__main__":
    if "--now" in sys.argv:
        push_code_changes()
    run_daily_push_cycle()
