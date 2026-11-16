"""Telegram Bot API + Instagram Graph API. Общий код для MCP-сервера и GitHub Actions.

Команды:  python social.py check     — проверить токены (ничего не публикует)
          python social.py refresh   — продлить токен Instagram на 60 дней
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

HERE = Path(__file__).parent
ENV_FILE = HERE / ".env"
STATE_DIR = HERE / "state"
load_dotenv(ENV_FILE)

IG_API = (os.getenv("IG_API_BASE", "").strip() or "https://graph.instagram.com/v24.0").rstrip("/")
IG_USER_ID = os.getenv("IG_USER_ID", "").strip()
IG_USERNAME = (os.getenv("IG_USERNAME", "lab_of_landscape").strip().lstrip("@"))
IG_TOKEN_TYPE = (os.getenv("IG_TOKEN_TYPE", "").strip().lower() or "instagram_login")
http = httpx.Client(timeout=60)


def _resolve_ig_user_id():
    """Resolve the selected Instagram business asset shared through Unified Login."""
    global IG_USER_ID
    if IG_USER_ID:
        return IG_USER_ID
    if not IG_API.startswith("https://graph.facebook.com/"):
        return ""
    response = http.get(
        f"{IG_API}/me/assigned_instagram_accounts",
        params={"access_token": env("IG_TOKEN"), "fields": "id,username"},
    )
    body = response.json()
    if "error" in body:
        error = body["error"]
        if error.get("code") == 190 and error.get("error_subcode") in (459, 464):
            raise RuntimeError(
                "Meta заблокировала API-сессию Facebook-пользователя. "
                "Войдите в facebook.com под тем же профилем, подтвердите аккаунт "
                "или завершите проверку безопасности, затем создайте новый токен Unified Login."
            )
        raise RuntimeError(
            "Не удалось получить Instagram-активы Unified Login: "
            f"{error.get('message')} (код {error.get('code')}, "
            f"subcode {error.get('error_subcode')}). "
            "Проверьте разрешение business_management в конфигурации Meta."
        )
    matches = [item for item in body.get("data", []) if item.get("username", "").lower() == IG_USERNAME.lower()]
    if len(matches) != 1:
        available = ", ".join("@" + str(x.get("username", "?")) for x in body.get("data", []))
        raise RuntimeError(
            f"В выданных Meta активах не найден единственный аккаунт @{IG_USERNAME}. "
            f"Доступные аккаунты: {available or 'список пуст'}. "
            "Проверьте, что Instagram-аккаунт выбран в конфигурации Unified Login."
        )
    IG_USER_ID = str(matches[0]["id"])
    print(f"[OK] Unified Login: найден @{IG_USERNAME}, Instagram ID {IG_USER_ID}")
    return IG_USER_ID


def env(name, required=True):
    value = os.getenv(name, "").strip()
    if required and not value:
        raise RuntimeError(f"В файле .env не заполнено {name}")
    return value


# ---------------- Telegram ----------------

def tg(method, data=None, files=None):
    r = http.post(f"https://api.telegram.org/bot{env('TG_BOT_TOKEN')}/{method}", data=data, files=files)
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method}: {body.get('description')}")
    return body["result"]


def _chat(chat_id):
    return chat_id or env("TG_CHAT_ID")


def _is_local(src):
    return not str(src).startswith(("http://", "https://")) and Path(src).is_file()


def send_message(text, chat_id=None, buttons=None):
    """buttons: [[{"text": "...", "url": "..."}], ...] — ряды кнопок."""
    data = {"chat_id": _chat(chat_id), "text": text, "parse_mode": "HTML"}
    if buttons:
        data["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    return tg("sendMessage", data)


def send_photo(photo, caption="", chat_id=None):
    data = {"chat_id": _chat(chat_id), "caption": caption, "parse_mode": "HTML"}
    if _is_local(photo):
        with open(photo, "rb") as f:
            return tg("sendPhoto", data, {"photo": f})
    return tg("sendPhoto", {**data, "photo": photo})


def send_album(photos, caption="", chat_id=None):
    if not 2 <= len(photos) <= 10:
        raise ValueError("В альбоме должно быть от 2 до 10 фото")
    media, files = [], {}
    for i, p in enumerate(photos):
        item = {"type": "photo"}
        if _is_local(p):
            files[f"f{i}"] = open(p, "rb")
            item["media"] = f"attach://f{i}"
        else:
            item["media"] = p
        if i == 0 and caption:
            item.update(caption=caption, parse_mode="HTML")
        media.append(item)
    try:
        return tg("sendMediaGroup", {"chat_id": _chat(chat_id), "media": json.dumps(media)}, files or None)
    finally:
        for f in files.values():
            f.close()


def get_updates():
    """Новые сообщения боту. offset хранится в state/tg_offset.txt, поэтому ничего не теряется и не повторяется."""
    STATE_DIR.mkdir(exist_ok=True)
    offset_file = STATE_DIR / "tg_offset.txt"
    offset = int(offset_file.read_text()) if offset_file.exists() else 0
    updates = tg("getUpdates", {"offset": offset, "timeout": 0})
    if updates:
        offset_file.write_text(str(updates[-1]["update_id"] + 1))
    result = []
    for u in updates:
        m = u.get("message") or u.get("channel_post") or u.get("edited_message") or {}
        cb = u.get("callback_query")
        result.append({
            "update_id": u["update_id"],
            "chat_id": (m.get("chat") or {}).get("id"),
            "message_id": m.get("message_id"),
            "from": (m.get("from") or {}).get("username"),
            "date": m.get("date"),
            "text": m.get("text") or m.get("caption"),
            "button_pressed": cb and cb.get("data"),
        })
    return result


def edit_message(message_id, text, chat_id=None):
    return tg("editMessageText", {"chat_id": _chat(chat_id), "message_id": message_id, "text": text, "parse_mode": "HTML"})


def delete_message(message_id, chat_id=None):
    return tg("deleteMessage", {"chat_id": _chat(chat_id), "message_id": message_id})


def pin_message(message_id, chat_id=None):
    return tg("pinChatMessage", {"chat_id": _chat(chat_id), "message_id": message_id})


def tg_post_link(msg):
    chat = msg["chat"]
    if chat.get("username"):
        return f"https://t.me/{chat['username']}/{msg['message_id']}"
    return f"https://t.me/c/{str(chat['id']).removeprefix('-100')}/{msg['message_id']}"


# ---------------- Instagram ----------------

def ig(method, path, **params):
    """Instagram API request. Facebook Login mode addresses the IG account by its numeric ID."""
    if path == "me" or path.startswith("me/"):
        if IG_API.startswith("https://graph.facebook.com/"):
            account_id = _resolve_ig_user_id()
            path = account_id + path[2:]
        elif IG_USER_ID:
            path = IG_USER_ID + path[2:]
    params["access_token"] = env("IG_TOKEN")
    r = http.request(method, f"{IG_API}/{path}", params=params)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Instagram: {body['error'].get('message')}")
    return body


def _wait_ready(creation_id):
    for _ in range(40):  # Instagram готовит медиа асинхронно
        status = ig("GET", creation_id, fields="status_code")["status_code"]
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("Instagram не смог обработать картинку (проверьте ссылку, формат JPG, размер)")
        time.sleep(3)
    raise RuntimeError("Instagram слишком долго обрабатывает картинку, попробуйте позже")


def _ig_publish(creation_id):
    _wait_ready(creation_id)
    media_id = ig("POST", "me/media_publish", creation_id=creation_id)["id"]
    return {"id": media_id, "permalink": ig("GET", media_id, fields="permalink").get("permalink")}


def ig_post_photo(image_url, caption=""):
    return _ig_publish(ig("POST", "me/media", image_url=image_url, caption=caption)["id"])


def ig_post_carousel(image_urls, caption=""):
    if not 2 <= len(image_urls) <= 10:
        raise ValueError("В карусели должно быть от 2 до 10 слайдов")
    children = [ig("POST", "me/media", image_url=u, is_carousel_item="true")["id"] for u in image_urls]
    for c in children:
        _wait_ready(c)
    return _ig_publish(ig("POST", "me/media", media_type="CAROUSEL", children=",".join(children), caption=caption)["id"])


def ig_post_story(image_url):
    return _ig_publish(ig("POST", "me/media", media_type="STORIES", image_url=image_url)["id"])


def ig_recent_posts(limit=10):
    return ig("GET", "me/media", fields="id,caption,media_type,permalink,timestamp", limit=limit)["data"]


def ig_refresh_token():
    """Продлевает токен Instagram Login. Facebook/Unified Login uses a different token lifecycle."""
    if IG_TOKEN_TYPE != "instagram_login" or not IG_API.startswith("https://graph.instagram.com/"):
        raise RuntimeError("Автопродление доступно только для Instagram Login. Для текущего типа токена используйте его штатный механизм продления.")
    r = http.get("https://graph.instagram.com/refresh_access_token",
                 params={"grant_type": "ig_refresh_token", "access_token": env("IG_TOKEN")}).json()
    if "access_token" not in r:
        raise RuntimeError(f"Не удалось продлить токен: {r.get('error', r)}")
    if ENV_FILE.exists():
        lines = [f"IG_TOKEN={r['access_token']}" if l.startswith("IG_TOKEN=") else l
                 for l in ENV_FILE.read_text(encoding="utf-8").splitlines()]
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["IG_TOKEN"] = r["access_token"]
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / "ig_refreshed.txt").write_text(datetime.now(timezone.utc).isoformat())
    return r["access_token"], r["expires_in"] // 86400


def ig_refresh_if_old(days=7):
    """Тихо продлевает токен при запуске сервера, если продлевали больше `days` дней назад."""
    stamp = STATE_DIR / "ig_refreshed.txt"
    if not os.getenv("IG_TOKEN"):
        return
    if stamp.exists() and (datetime.now(timezone.utc) - datetime.fromisoformat(stamp.read_text())).days < days:
        return
    try:
        ig_refresh_token()
    except Exception as e:  # токен моложе 24 часов или уже истёк — сервер всё равно запускается
        print(f"Instagram token refresh skipped: {e}", file=sys.stderr)


# ---------------- Проверка ----------------

def check():
    ok = True
    try:
        me = tg("getMe")
        print(f"[OK] Telegram-бот: @{me['username']}")
        chat = tg("getChat", {"chat_id": env("TG_CHAT_ID")})
        print(f"[OK] Чат {chat['id']} доступен ({chat.get('first_name') or chat.get('title')})")
        if os.getenv("TG_CHANNEL_ID"):
            ch = tg("getChat", {"chat_id": env("TG_CHANNEL_ID")})
            print(f"[OK] Канал: {ch.get('title')}")
        else:
            print("[--] Канал ещё не указан (TG_CHANNEL_ID) — это нормально")
    except Exception as e:
        ok = False
        print(f"[ОШИБКА] Telegram: {e}")
    try:
        profile_path = IG_USER_ID if IG_USER_ID else "me"
        me = ig("GET", profile_path, fields="username,account_type")
        print(f"[OK] Instagram: @{me['username']} ({me.get('account_type')})")
    except Exception as e:
        ok = False
        print(f"[ОШИБКА] Instagram: {e}")
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        sys.exit(0 if check() else 1)
    elif cmd == "refresh":
        _, days = ig_refresh_token()
        print(f"[OK] Токен Instagram продлён, действует ещё {days} дней")
    else:
        print(__doc__)
