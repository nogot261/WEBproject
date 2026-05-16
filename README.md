# WebServer + API (Python, FastAPI)

Учебный проект по теме **WebServer + API**.

## Что реализовано

- web-приложение на **Python + FastAPI**;
- интерфейс на **Bootstrap 5**;
- **ORM-модели** на SQLAlchemy;
- регистрация, авторизация и выход из аккаунта;
- загрузка файлов с ограничением по размеру и расширению;
- просмотр списка файлов, карточка файла, скачивание и удаление;
- приватный REST API для текущего пользователя и его файлов;
- использование стороннего API;
- хранение данных в **SQLite**;
- подготовка к хостингу через Docker.

## Структура проекта

- `app/main.py` - основной FastAPI-сервер;
- `app/database.py` - подключение к базе данных;
- `app/models.py` - ORM-модели;
- `templates/` - HTML-шаблоны;
- `static/` - стили;
- `uploads/` - загруженные файлы;
- `CHECKLIST.md` - соответствие критериям проекта.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Для Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Настройка

Для локального запуска можно использовать встроенный dev-секрет. Для хостинга обязательно задать переменную окружения:

```bash
export SESSION_SECRET_KEY="replace-with-long-random-secret"
```

Для Windows PowerShell:

```powershell
$env:SESSION_SECRET_KEY="replace-with-long-random-secret"
```

## Запуск

```bash
uvicorn app.main:app --reload
```

После запуска открыть:

- сайт: http://127.0.0.1:8000
- Swagger API: http://127.0.0.1:8000/docs

## REST API

- `GET /api/status` - публичная проверка работы сервера.
- `GET /api/users/me` - данные текущего пользователя, нужна авторизация.
- `GET /api/files` - файлы текущего пользователя, нужна авторизация.
- `GET /api/files/{file_id}` - карточка файла текущего пользователя, нужна авторизация.
- `GET /api/external/fact` - получение данных из стороннего API.

Публичные эндпоинты больше не отдают списки всех пользователей и файлов.

## Ручной тестовый сценарий

1. Открыть `/register`, создать пользователя.
2. Выйти и войти через `/login`.
3. Загрузить корректный файл: `.txt`, `.csv`, `.json`, `.md`, `.log`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.pdf` или `.zip`, размером до 5 МБ.
4. Проверить, что пустой файл, файл больше 5 МБ или файл с другим расширением не загружается.
5. Открыть карточку файла, проверить предпросмотр для текстовых файлов.
6. Скачать файл.
7. Удалить файл и убедиться, что он исчез из личного кабинета.
8. Открыть `/docs` и проверить `/api/status`.
9. Проверить, что `/api/files` без авторизации возвращает `401`.
10. Открыть страницу `/external-fact`.

## Хостинг и Docker

Для развёртывания подготовлен `Dockerfile`.

```bash
docker build -t webserver-api-project .
docker run -p 8000:8000 -e SESSION_SECRET_KEY="replace-with-long-random-secret" webserver-api-project
```

SQLite-база `app.db` и папка `uploads/` находятся внутри контейнера. При обычном запуске контейнера эти данные пропадут после пересоздания контейнера. Для сохранения данных нужно подключить volume:

```bash
docker run -p 8000:8000 \
  -e SESSION_SECRET_KEY="replace-with-long-random-secret" \
  -v "$(pwd)/app.db:/code/app.db" \
  -v "$(pwd)/uploads:/code/uploads" \
  webserver-api-project
```
