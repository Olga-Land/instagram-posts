"""Публикует одобренные посты из slides/<папка>/post.yml, когда пришло их время.

Запускается GitHub Actions каждые 15 минут. Токены берутся из GitHub Secrets.
После публикации дописывает ссылки в post.yml (чтобы не опубликовать дважды) и присылает их Ольге в Telegram.
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yaml

import social as s

ROOT = Path(os.getenv("GITHUB_WORKSPACE", "."))
TZ = ZoneInfo(os.getenv("POST_TIMEZONE", "Europe/Moscow"))
REPO = os.getenv("GITHUB_REPOSITORY", "Olga-Land/instagram-posts")
SHA = os.getenv("GITHUB_SHA", "main")
TG_CAPTION_LIMIT = 1024


def raw_url(path):
    return f"https://raw.githubusercontent.com/{REPO}/{SHA}/{quote(path.relative_to(ROOT).as_posix())}"


def due(post, now):
    when = post.get("publish_at")
    if post.get("approved") is not True or not when or post.get("paused"):
        return False
    when = when if isinstance(when, datetime) else datetime.fromisoformat(str(when))
    return when.replace(tzinfo=TZ) <= now


def publish_telegram(images, text, channel):
    long_text = len(text) > TG_CAPTION_LIMIT
    caption = "" if long_text else text
    if not images:
        msg = s.send_message(text, channel)
    elif len(images) == 1:
        msg = s.send_photo(str(images[0]), caption, channel)
    else:
        msg = s.send_album([str(p) for p in images[:10]], caption, channel)[0]
    if long_text and images:
        s.send_message(text, channel)  # подпись к фото в Telegram не длиннее 1024 знаков
    return s.tg_post_link(msg)


def publish_instagram(images, text, story):
    urls = [raw_url(p) for p in images]
    if not urls:
        raise ValueError("для Instagram нужна хотя бы одна картинка .jpg")
    if story:
        return s.ig_post_story(urls[0])["permalink"]
    if len(urls) == 1:
        return s.ig_post_photo(urls[0], text)["permalink"]
    return s.ig_post_carousel(urls[:10], text)["permalink"]


def main():
    now = datetime.now(TZ)
    channel = os.getenv("TG_CHANNEL_ID", "").strip()
    changed = False
    for post_file in sorted(ROOT.glob("slides/*/post.yml")):
        post = yaml.safe_load(post_file.read_text(encoding="utf-8")) or {}
        if not due(post, now):
            continue
        folder = post_file.parent
        images = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
        text = (post.get("text") or "").strip()
        report = [f"📅 Пост <b>{folder.name}</b>:"]

        jobs = []
        if post.get("telegram", True) and not post.get("published_telegram"):
            jobs.append(("published_telegram", "Telegram", lambda: publish_telegram(images, text, channel)))
        if post.get("instagram", True) and not post.get("published_instagram"):
            jobs.append(("published_instagram", "Instagram",
                         lambda: publish_instagram(images, text, post.get("story", False))))
        if not jobs:
            continue

        done = {}
        for key, name, run in jobs:
            if key == "published_telegram" and not channel:
                done[key] = "пропущено — канал не задан"
                report.append("⚠️ Telegram: канал не задан (секрет TG_CHANNEL_ID) — пропущено")
                continue
            try:
                done[key] = run()
                report.append(f"✅ {name}: {done[key]}")
            except Exception as e:  # одна площадка упала — вторая всё равно публикуется
                report.append(f"❌ {name}: {e}")
                done["paused"] = f"ошибка {name}: {e}".replace('"', "'")
                report.append("Пост поставлен на паузу. Исправьте и удалите строку paused в post.yml — он опубликуется снова.")

        if done:  # дописываем в конец, чтобы не трогать текст и комментарии Ольги
            body = post_file.read_text(encoding="utf-8").rstrip("\n")
            post_file.write_text(body + "\n" + "".join(f"{k}: \"{v}\"\n" for k, v in done.items()), encoding="utf-8")
            changed = True
        s.send_message("\n".join(report))

    print("changed" if changed else "nothing to publish")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
