"""
Đăng bài Threads (account Bac Day) kèm ảnh/video.

Excel `bac_day_vocab_data.xlsx` — Sheet1, cột:
  - content      : nội dung bài chính
  - sub_content  : nội dung reply (luồng trả lời bài chính)
  - image_url    : URL công khai của ảnh (JPEG/PNG)
  - video_url    : URL công khai của video
  - upload_time  : tự ghi sau khi đăng thành công (để bỏ qua bài đã đăng)

Ưu tiên media: image_url > video_url > TEXT thuần.
"""

import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

CONST_MAX_POST = 15
CONST_TIME_SLEEP = 60  # phút — mỗi bài cách nhau 1 tiếng
SESSION_START_HOUR = 9
SESSION_END_HOUR = 0
POST_BUFFER_SECONDS = 180

REQUIRED_COLUMNS = ("content", "sub_content", "image_url", "video_url")


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() in ("", "nan", "None")


def _clean_str(value):
    if _is_blank(value):
        return None
    return str(value).strip()


def get_session_bounds(now=None):
    """Phiên đăng: 09:00 hôm nay → 00:00 hôm sau."""
    now = now or datetime.now()
    session_start = now.replace(
        hour=SESSION_START_HOUR, minute=0, second=0, microsecond=0
    )
    session_end = now.replace(
        hour=SESSION_END_HOUR, minute=0, second=0, microsecond=0
    )

    if now.hour >= SESSION_START_HOUR:
        session_end += timedelta(days=1)
        return session_start, session_end
    if now.hour < SESSION_END_HOUR:
        session_start -= timedelta(days=1)
        return session_start, session_end
    return None, None


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


def wait_until_session_start():
    while True:
        session_start, session_end = get_session_bounds()
        if session_start is not None:
            print(
                f"📅 Phiên đăng: {session_start.strftime('%d/%m %H:%M')} "
                f"→ {session_end.strftime('%d/%m %H:%M')}"
            )
            return session_start, session_end

        now = datetime.now()
        target = now.replace(
            hour=SESSION_START_HOUR, minute=0, second=0, microsecond=0
        )
        print("⏸️  Ngoài khung giờ đăng (00:00–09:00). Chờ đến 9:00...")
        wait_until_datetime(target)


def filter_session_posts(df, session_start, session_end):
    return df[
        (df["upload_time"] >= session_start) & (df["upload_time"] < session_end)
    ].copy()


def load_vocab_df(file_path):
    df = pd.read_excel(file_path, sheet_name="Sheet1")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Excel thiếu cột: {missing}")
    if "upload_time" not in df.columns:
        df["upload_time"] = pd.NaT
    df["upload_time"] = pd.to_datetime(df["upload_time"], errors="coerce")
    return df


def save_vocab_df(df, file_path):
    with pd.ExcelWriter(
        file_path, engine="openpyxl", mode="a", if_sheet_exists="overlay"
    ) as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)


def seconds_until_session_end(session_end):
    return (session_end - datetime.now()).total_seconds()


def can_post_more(session_end, posted_count):
    if posted_count >= CONST_MAX_POST:
        return False
    if seconds_until_session_end(session_end) <= POST_BUFFER_SECONDS:
        return False
    return datetime.now() < session_end


def sleep_between_posts(session_end):
    remaining = seconds_until_session_end(session_end) - POST_BUFFER_SECONDS
    if remaining <= 0:
        return
    time_sleep = min(CONST_TIME_SLEEP * 60, remaining)
    print(f"Đang đợi {time_sleep / 60:.0f} phút trước bài tiếp theo...")
    time.sleep(time_sleep)


def resolve_media(image_url=None, video_url=None):
    """Trả về (media_type, media_url). Ưu tiên ảnh > video > text."""
    image_url = _clean_str(image_url)
    video_url = _clean_str(video_url)
    if image_url:
        return "IMAGE", image_url
    if video_url:
        return "VIDEO", video_url
    return "TEXT", None


def post_to_threads(
    text,
    reply_to_id=None,
    user_id=None,
    access_token=None,
    image_url=None,
    video_url=None,
):
    media_type, media_url = resolve_media(image_url, video_url)
    url_create = f"https://graph.threads.net/v1.0/{user_id}/threads"
    payload_create = {
        "media_type": media_type,
        "access_token": access_token,
    }

    text = _clean_str(text)
    if text:
        payload_create["text"] = text
    elif media_type == "TEXT":
        print("Lỗi: bài TEXT cần có nội dung.")
        return None

    if media_type == "IMAGE":
        payload_create["image_url"] = media_url
    elif media_type == "VIDEO":
        payload_create["video_url"] = media_url

    if reply_to_id:
        payload_create["reply_to_id"] = reply_to_id

    print(f"  -> media_type={media_type}" + (f", url={media_url}" if media_url else ""))
    response_create = requests.post(url_create, data=payload_create)
    data_create = response_create.json()

    if "id" not in data_create:
        print(f"Lỗi tạo container: {data_create}")
        return None

    creation_id = data_create["id"]
    print(f"  -> Đã tạo container. Creation ID: {creation_id}")

    # Video cần thời gian xử lý lâu hơn ảnh/text
    wait_seconds = 30 if media_type == "VIDEO" else 5
    time.sleep(wait_seconds)

    url_publish = f"https://graph.threads.net/v1.0/{user_id}/threads_publish"
    payload_publish = {
        "creation_id": creation_id,
        "access_token": access_token,
    }
    response_publish = requests.post(url_publish, data=payload_publish)
    data_publish = response_publish.json()

    if "id" in data_publish:
        published_id = data_publish["id"]
        print(f"  -> Publish THÀNH CÔNG! Post ID: {published_id}")
        return published_id

    print(f"Lỗi publish: {data_publish}")
    return None


def post_content_chain(df_origin, row_idx, user_id, access_token):
    """Đăng bài chính (+ media) rồi reply bằng sub_content. Trả về True nếu thành công."""
    content = _clean_str(df_origin.loc[row_idx, "content"])
    sub_content = _clean_str(df_origin.loc[row_idx, "sub_content"])
    image_url = df_origin.loc[row_idx, "image_url"]
    video_url = df_origin.loc[row_idx, "video_url"]

    print("content:", content)
    print("sub_content:", sub_content)
    print("Bây giờ là:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    print("=== ĐANG ĐĂNG BÀI CHÍNH ===")
    post_1_id = post_to_threads(
        content,
        user_id=user_id,
        access_token=access_token,
        image_url=image_url,
        video_url=video_url,
    )
    if not post_1_id:
        print("\n❌ Thất bại ở bài chính, đã dừng chuỗi bài.")
        return False

    if not sub_content:
        print("\n🎉 Hoàn tất! Không có sub_content nên bỏ qua reply.")
        return True

    time.sleep(2)
    print("\n=== ĐANG ĐĂNG REPLY (sub_content) ===")
    post_2_id = post_to_threads(
        sub_content,
        reply_to_id=post_1_id,
        user_id=user_id,
        access_token=access_token,
    )
    if not post_2_id:
        print("\n❌ Bài chính đã lên nhưng reply thất bại.")
        return False

    print("\n🎉 Hoàn tất chuỗi bài (chính + reply).")
    return True


def run_posting_session(file_path, user_id, access_token, session_start, session_end):
    while True:
        df_origin = load_vocab_df(file_path)
        df_filtered = filter_session_posts(df_origin, session_start, session_end)
        posted_count = len(df_filtered)
        print(f"Đã đăng trong phiên: {posted_count}/{CONST_MAX_POST}")

        if not can_post_more(session_end, posted_count):
            break

        pending = df_origin[df_origin["upload_time"].isna()]
        if pending.empty:
            print("⚠️  Hết bài chưa đăng trong file Excel.")
            break

        row_idx = pending.index[0]
        print(f"\n--- Đăng bài #{posted_count + 1} (dòng {row_idx}) ---")
        if post_content_chain(df_origin, row_idx, user_id, access_token):
            df_origin = load_vocab_df(file_path)
            df_origin.loc[row_idx, "upload_time"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            save_vocab_df(df_origin, file_path)
            df_filtered = filter_session_posts(df_origin, session_start, session_end)
            print(f"Đã đăng trong phiên: {len(df_filtered)}/{CONST_MAX_POST}")

        if not can_post_more(session_end, len(df_filtered)):
            break

        sleep_between_posts(session_end)


def run_daily_cycle(file_path, user_id, access_token):
    while True:
        session_start, session_end = wait_until_session_start()
        run_posting_session(
            file_path, user_id, access_token, session_start, session_end
        )

        print(f"\n⏰ Kết thúc phiên lúc {session_end.strftime('%H:%M')}.")
        wait_until_datetime(session_end)

        next_session_start = session_end.replace(
            hour=SESSION_START_HOUR, minute=0, second=0, microsecond=0
        )
        print(
            f"\n🌙 Chờ đến {next_session_start.strftime('%d/%m %H:%M')} "
            "để bắt đầu phiên mới..."
        )
        wait_until_datetime(next_session_start)


if __name__ == "__main__":
    load_dotenv(
        r"C:\Users\vinhdt912\Documents\Projects\add_anki_with_gemini_draft"
        r"\add_anki_with_gemini\.env"
    )

    user_id = os.getenv("USER_ID", "me")
    access_token = os.getenv("LONG_LIVED_TOKEN")
    if not access_token or access_token.startswith("YOUR_"):
        raise SystemExit(
            "Thiếu LONG_LIVED_TOKEN trong .env — hãy thay bằng token thật."
        )

    file_path = r"C:\Users\vinhdt912\Documents\thuy_onedrive\OneDrive\Giáo Ngọng Businesss\Tools\Threads\bac_day\vocab_data.xlsx"

    print(load_vocab_df(file_path).head())
    run_daily_cycle(file_path, user_id, access_token)
