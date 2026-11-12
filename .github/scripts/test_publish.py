"""Самопроверка логики без настоящих публикаций: python .github/scripts/test_publish.py"""
import os
import sys
import tempfile
from pathlib import Path

import yaml

tmp = Path(tempfile.mkdtemp())
os.environ.update(GITHUB_WORKSPACE=str(tmp), TG_CHANNEL_ID="@test", TG_BOT_TOKEN="x", IG_TOKEN="x")
sys.path.insert(0, str(Path(__file__).parent))
import publish  # noqa: E402

sent = []
publish.s.send_message = lambda text, chat=None: sent.append(text) or {"chat": {"username": "t"}, "message_id": 1}
publish.s.send_album = lambda photos, cap, chat: [{"chat": {"username": "test"}, "message_id": 7}]
publish.s.ig_post_carousel = lambda urls, text: {"permalink": "https://instagram.com/p/OK"}


def make(name, approved, when):
    d = tmp / "slides" / name
    d.mkdir(parents=True)
    for i in (1, 2):
        (d / f"slide_0{i}.jpg").write_bytes(b"x")
    (d / "post.yml").write_text(f"approved: {approved}\npublish_at: {when}\ntext: |\n  Привет\n", encoding="utf-8")
    return d / "post.yml"


ready = make("ready", "true", "2020-01-01 10:00")
draft = make("draft", "false", "2020-01-01 10:00")
future = make("future", "true", "2099-01-01 10:00")

publish.main()
data = yaml.safe_load(ready.read_text(encoding="utf-8"))
assert data["published_telegram"] == "https://t.me/test/7", data
assert data["published_instagram"] == "https://instagram.com/p/OK", data
assert data["text"].strip() == "Привет"
assert "published_telegram" not in draft.read_text(encoding="utf-8")
assert "published_telegram" not in future.read_text(encoding="utf-8")
assert len(sent) == 1  # отчёт только про один пост

publish.main()  # второй запуск ничего не публикует повторно
assert len(sent) == 1

publish.s.ig_post_carousel = lambda urls, text: (_ for _ in ()).throw(RuntimeError("плохая картинка"))
broken = make("broken", "true", "2020-01-01 10:00")
publish.main()
assert "paused" in yaml.safe_load(broken.read_text(encoding="utf-8"))
publish.main()  # на паузе — без повторных ошибок
assert len(sent) == 2
print("OK: все проверки прошли")
