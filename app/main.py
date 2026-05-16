from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .database import Base, SessionLocal, engine
from .models import UploadedFile as UploadedFileModel
from .models import User

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "dev-session-secret-change-before-hosting")
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {
    ".txt",
    ".csv",
    ".json",
    ".md",
    ".log",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
}

Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="WebServer + API Project", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user


def text_preview(path: str) -> str | None:
    preview_exts = {".txt", ".csv", ".json", ".md", ".py", ".log"}
    file_path = Path(path)
    if file_path.suffix.lower() not in preview_exts:
        return None
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")[:4000]
    except Exception:
        return None


def render_message(request: Request, title: str, message: str, kind: str = "info", user: User | None = None):
    return templates.TemplateResponse(
        "message.html",
        {"request": request, "title": title, "message": message, "kind": kind, "user": user},
    )


@app.head("/")
def home_head():
    return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    stats = {
        "users": db.query(User).count(),
        "files": db.query(UploadedFileModel).count(),
    }
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user, "stats": stats},
    )


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse("register.html", {"request": request, "user": user})


@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip()
    if len(username) < 3:
        return render_message(request, "Ошибка", "Логин должен содержать минимум 3 символа.", "danger")
    if len(password) < 4:
        return render_message(request, "Ошибка", "Пароль должен содержать минимум 4 символа.", "danger")

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return render_message(request, "Ошибка", "Пользователь с таким логином уже существует.", "danger")

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse("login.html", {"request": request, "user": user})


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return render_message(request, "Ошибка", "Неверный логин или пароль.", "danger")

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    files = (
        db.query(UploadedFileModel)
        .filter(UploadedFileModel.owner_id == user.id)
        .order_by(UploadedFileModel.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "files": files},
    )


@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)

    safe_name = Path(file.filename).name if file.filename else "file.bin"
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        return render_message(
            request,
            "Ошибка загрузки",
            f"Файлы с расширением {extension or 'без расширения'} не поддерживаются. Разрешены: {allowed}.",
            "danger",
            user,
        )

    content = await file.read()
    if not content:
        return render_message(request, "Ошибка загрузки", "Нельзя загрузить пустой файл.", "danger", user)
    if len(content) > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
        return render_message(
            request,
            "Ошибка загрузки",
            f"Файл слишком большой. Максимальный размер: {max_mb} МБ.",
            "danger",
            user,
        )

    stored_name = f"{uuid4().hex}_{safe_name}"
    destination = UPLOAD_DIR / stored_name

    destination.write_bytes(content)

    db_file = UploadedFileModel(
        original_name=safe_name,
        stored_name=stored_name,
        file_path=str(destination),
        content_type=file.content_type,
        description=description.strip() or None,
        owner_id=user.id,
    )
    db.add(db_file)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/files/{file_id}", response_class=HTMLResponse)
def file_detail(file_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    item = db.query(UploadedFileModel).filter(UploadedFileModel.id == file_id).first()
    if not item or item.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Файл не найден")

    preview = text_preview(item.file_path)
    return templates.TemplateResponse(
        "file_detail.html",
        {"request": request, "user": user, "item": item, "preview": preview},
    )


@app.get("/download/{file_id}")
def download_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    item = db.query(UploadedFileModel).filter(UploadedFileModel.id == file_id).first()
    if not item or item.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(item.file_path, filename=item.original_name)


@app.post("/files/{file_id}/delete")
def delete_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    item = db.query(UploadedFileModel).filter(UploadedFileModel.id == file_id).first()
    if not item or item.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Файл не найден")

    file_path = Path(item.file_path)
    if file_path.exists() and file_path.is_file():
        file_path.unlink()

    db.delete(item)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/external-fact", response_class=HTMLResponse)
async def external_fact_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    fact = None
    error = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://catfact.ninja/fact")
            response.raise_for_status()
            fact = response.json().get("fact")
    except Exception as exc:
        error = f"Не удалось получить данные из внешнего API: {exc}"

    return templates.TemplateResponse(
        "external_fact.html",
        {"request": request, "user": user, "fact": fact, "error": error},
    )


@app.get("/api/status")
def api_status():
    return {"status": "ok", "project": "WebServer + API", "version": "1.0.0"}


@app.get("/api/users/me")
def api_current_user(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return {
        "id": user.id,
        "username": user.username,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@app.get("/api/files")
def api_files(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    files = (
        db.query(UploadedFileModel)
        .filter(UploadedFileModel.owner_id == user.id)
        .order_by(UploadedFileModel.id.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "original_name": item.original_name,
            "content_type": item.content_type,
            "description": item.description,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in files
    ]


@app.get("/api/files/{file_id}")
def api_file_detail(file_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    item = db.query(UploadedFileModel).filter(UploadedFileModel.id == file_id).first()
    if not item or item.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return {
        "id": item.id,
        "original_name": item.original_name,
        "content_type": item.content_type,
        "description": item.description,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@app.get("/api/external/fact")
async def api_external_fact():
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get("https://catfact.ninja/fact")
        response.raise_for_status()
        return response.json()
