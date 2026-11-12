# instagram-posts

Посты для Telegram-канала и Instagram @lab_of_landscape. GitHub публикует их сам по расписанию, даже когда компьютер выключен.

## Как запланировать пост
1. Положите картинки `.jpg` в папку `slides/<дата>/` (публикуются по алфавиту).
2. Скопируйте туда `slides/ОБРАЗЕЦ-post.yml` под именем `post.yml` и впишите текст и время (по Москве).
3. Когда всё готово, поставьте `approved: true` и отправьте изменения в GitHub.
4. В течение 15–30 минут после указанного времени пост выйдет, и ссылки придут в Telegram.

Публикуются только посты с `approved: true`. После публикации робот дописывает в `post.yml` строки `published_...`. Их нельзя удалять, иначе пост выйдет второй раз.
Если что-то пошло не так, в Telegram придёт ❌, а в `post.yml` появится строка `paused`. Исправьте ошибку, удалите строку `paused`, и пост опубликуется заново.

## Секреты (один раз)
GitHub → этот репозиторий → **Settings → Secrets and variables → Actions → New repository secret**:

| Имя | Что вставить |
|---|---|
| `TG_BOT_TOKEN` | токен бота (тот же, что в `.env` на компьютере) |
| `TG_CHAT_ID` | `350055812` |
| `TG_CHANNEL_ID` | `@имя_канала` (бот должен быть админом канала) |
| `IG_TOKEN` | токен Instagram |
| `GH_PAT` | необязательно: личный токен GitHub для автопродления токена Instagram (см. ниже) |

**GH_PAT:** github.com → аватар → Settings → Developer settings → Fine-grained tokens → Generate. Repository access: только `instagram-posts`. Permissions: **Secrets: Read and write**. Без этого секрета токен Instagram придётся обновлять вручную раз в 60 дней.

Ручной запуск: вкладка **Actions** → «Публикация по расписанию» → **Run workflow**.
