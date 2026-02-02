from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.future import select
from database import SessionLocal, engine, Base, database
from models import Place
from auth import create_session, check_login
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import os

# Ortam değişkenlerini yükle
load_dotenv()

# FastAPI uygulaması
app = FastAPI()

# Statik dosyalar ve şablonlar
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Basit kullanıcılar
users = {"admin": "admin123"}


# ---------------- Başlatma / Kapatma ----------------
@app.on_event("startup")
async def startup():
    await database.connect()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


# ---------------- Ana Sayfa ----------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    query = select(Place)
    async with SessionLocal() as session:
        result = await session.execute(query)
        places = result.scalars().all()

    # 🔽🔽🔽 BURASI EKLENECEK
    places_json = [
        {
            "id": p.id,
            "name_historic": p.name_historic,
            "name_modern": p.name_modern,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "is_in_ottoman": p.is_in_ottoman,
            "description_tr": p.description_tr,
            "description_en": p.description_en,
        }
        for p in places
    ]
    # 🔼🔼🔼

    return templates.TemplateResponse("index.html", {
        "request": request,
        "places": places_json,   # 👈 ORM DEĞİL JSON GİDİYOR
        "google_maps_key": os.getenv("GOOGLE_MAPS_API_KEY")
    })



# ---------------- Giriş Sistemi ----------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if users.get(username) == password:
        response = RedirectResponse(url="/admin", status_code=303)
        token = create_session(username)
        response.set_cookie(key="session_token", value=token, httponly=True)
        return response
    return RedirectResponse(url="/login", status_code=303)


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("session_token")
    return response


# ---------------- Admin Panel ----------------
@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request, user: str = Depends(check_login)):
    query = select(Place)
    async with SessionLocal() as session:
        result = await session.execute(query)
        places = result.scalars().all()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "places": places
    })


@app.post("/admin/add")
async def add_place(
    request: Request,
    name_historic: str = Form(...),
    name_modern: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    is_in_ottoman: bool = Form(False),
    description_tr: str = Form(""),
    description_en: str = Form(""),
    user: str = Depends(check_login)
):
    async with SessionLocal() as session:
        place = Place(
            name_historic=name_historic,
            name_modern=name_modern,
            latitude=latitude,
            longitude=longitude,
            is_in_ottoman=is_in_ottoman,
            description_tr=description_tr,
            description_en=description_en
        )
        session.add(place)
        await session.commit()
    return RedirectResponse(url="/admin", status_code=303)


# ---------------- Excel'den Veri Yükleme ----------------
@app.get("/load_excel")
async def load_excel():
    """
    data klasöründeki Excel dosyasını okuyup veritabanına ekler.
    Beklenen sütun adları:
    no | lokasyon | tarih | kullanılan araç | bilgi | latitude | longitude | osmanlı toprağı olan yerler
    """
    excel_path = Path("data/123.xlsx")

    if not excel_path.exists():
        return JSONResponse({"error": f"{excel_path} bulunamadı!"}, status_code=404)

    # Excel oku
    df = pd.read_excel(excel_path)
    df.columns = df.columns.str.strip().str.lower()

    if "enlem" not in df.columns or "boylam" not in df.columns:
        return JSONResponse({"error": "Excel dosyasında 'latitude' veya 'longitude' sütunu bulunamadı."}, status_code=400)

    added = 0
    async with SessionLocal() as session:
        for _, row in df.iterrows():
            try:
                if pd.isna(row["enlem"]) or pd.isna(row["boylam"]):
                    continue

                place = Place(
                    name_historic=str(row.get("tarih", "")),
                    name_modern=str(row.get("lokasyon", "")),
                    latitude=float(row["enlem"]),
                    longitude=float(row["boylam"]),
                    is_in_ottoman=str(row.get("osmanlı toprağı olan yerler", "")).strip().lower() in ["evet", "true", "1"],
                    description_tr=str(row.get("bilgi", ""))
                )
                session.add(place)
                added += 1
            except Exception:
                continue

        await session.commit()

    return JSONResponse({"message": f"{added} kayıt başarıyla eklendi."})