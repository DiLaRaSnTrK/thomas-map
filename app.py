from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.future import select
from sqlalchemy import delete
from database import SessionLocal, engine, Base, database
from models import Place
from auth import create_session, check_login
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import os
from deep_translator import GoogleTranslator

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
    # Rotanın sırayla çizilmesi için ID'ye göre sıralıyoruz
    query = select(Place).order_by(Place.id)
    async with SessionLocal() as session:
        result = await session.execute(query)
        places = result.scalars().all()

    places_json = [
        {
            "id": p.id,
            "name_historic": p.name_historic,
            "name_modern": p.name_modern,
            "transport_type": p.transport_type, # Ana sayfaya eklendi
            "latitude": p.latitude,
            "longitude": p.longitude,
            "is_in_ottoman": p.is_in_ottoman,
            "description_tr": p.description_tr,
            "description_en": p.description_en,
        }
        for p in places
    ]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "places": places_json,
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
    query = select(Place).order_by(Place.id)
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
    transport_type: str = Form(None), # Formdan gelen veri eklendi
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
            transport_type=transport_type, # Veritabanına kaydediliyor
            latitude=latitude,
            longitude=longitude,
            is_in_ottoman=is_in_ottoman,
            description_tr=description_tr,
            description_en=description_en
        )
        session.add(place)
        await session.commit()
    return RedirectResponse(url="/admin?msg=added", status_code=303)


@app.get("/admin/delete/{place_id}")
async def delete_place(place_id: int, user: str = Depends(check_login)):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
        if place:
            await session.delete(place)
            await session.commit()
    return RedirectResponse(url="/admin?msg=deleted", status_code=303)


@app.get("/admin/edit/{place_id}", response_class=HTMLResponse)
async def edit_page(request: Request, place_id: int, user: str = Depends(check_login)):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
    return templates.TemplateResponse("edit.html", {"request": request, "place": place})


@app.post("/admin/edit/{place_id}")
async def edit_save(
    place_id: int, 
    name_historic: str = Form(...), 
    name_modern: str = Form(...), 
    transport_type: str = Form(None), # Düzenleme formuna eklendi
    latitude: float = Form(...), 
    longitude: float = Form(...), 
    is_in_ottoman: bool = Form(False), 
    description_tr: str = Form(""), 
    description_en: str = Form(""),
    user: str = Depends(check_login)
):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
        if place:
            place.name_historic = name_historic
            place.name_modern = name_modern
            place.transport_type = transport_type # Güncelleniyor
            place.latitude = latitude
            place.longitude = longitude
            place.is_in_ottoman = is_in_ottoman
            place.description_tr = description_tr
            place.description_en = description_en
            await session.commit()
    return RedirectResponse(url="/admin?msg=updated", status_code=303)


# ---------------- Otomatik Çeviri ve Excel ----------------

@app.post("/admin/translate")
async def translate_text(request: Request):
    try:
        data = await request.json()
        text_to_translate = data.get("text")
        if not text_to_translate:
            return {"translated_text": ""}
        
        translated = GoogleTranslator(source='tr', target='en').translate(text_to_translate)
        return {"translated_text": translated}
    except Exception as e:
        print(f"Çeviri hatası: {e}")
        return JSONResponse({"error": "Çeviri yapılamadı", "details": str(e)}, status_code=500)


@app.get("/load_excel")
async def load_excel():
    excel_path = Path("data/123.xlsx")
    if not excel_path.exists():
        return JSONResponse({"error": f"Excel dosyası '{excel_path}' bulunamadı!"}, status_code=404)

    df = pd.read_excel(excel_path)
    # Sütun isimlerini temizle ve küçük harfe çevir
    df.columns = [str(c).strip().lower().replace('ı', 'i').replace('i̇', 'i') for c in df.columns]

    translator = GoogleTranslator(source='tr', target='en')

    async with SessionLocal() as session:
        await session.execute(delete(Place))
        await session.commit()

        added = 0
        for index, row in df.iterrows():
            try:
                # Sütunları anahtar kelimelerle bul
                lat_col = next((c for c in df.columns if 'enlem' in c or 'lat' in c), None)
                lon_col = next((c for c in df.columns if 'boylam' in c or 'lon' in c), None)
                osman_col = next((c for c in df.columns if 'osman' in c), None)
                hist_col = next((c for c in df.columns if 'tarih' in c), None)
                mod_col = next((c for c in df.columns if 'lokasyon' in c or 'modern' in c), None)
                info_col = next((c for c in df.columns if 'bilgi' in c or 'desc' in c), None)
                
                # Sizin Excel'iniz için "araç" veya "kullanılan" kelimelerini kontrol eder
                vehicle_col = next((c for c in df.columns if 'arac' in c or 'transport' in c or 'kullanilan' in c or 'vasita' in c), None)
                
                if not lat_col or not lon_col or pd.isna(row[lat_col]):
                    continue

                # Veri temizleme
                transport_val = ""
                if vehicle_col and not pd.isna(row[vehicle_col]):
                    transport_val = str(row[vehicle_col]).strip()

                is_ottoman_val = False
                if osman_col:
                    val = str(row[osman_col]).strip().lower()
                    is_ottoman_val = val in ["evet", "true", "1", "yes"]

                desc_tr = str(row.get(info_col, "")) if info_col else ""
                desc_en = ""
                
                if desc_tr and desc_tr != "nan" and desc_tr.strip() != "":
                    try:
                        desc_en = translator.translate(desc_tr)
                    except:
                        desc_en = ""

                place = Place(
                    name_historic=str(row.get(hist_col, "")) if hist_col else "",
                    name_modern=str(row.get(mod_col, "")) if mod_col else "",
                    transport_type=transport_val,  # 👈 Excel'den gelen veri buraya yazılıyor
                    latitude=float(row[lat_col]),
                    longitude=float(row[lon_col]),
                    is_in_ottoman=is_ottoman_val,
                    description_tr=desc_tr,
                    description_en=desc_en
                )
                
                session.add(place)
                added += 1

            except Exception as e:
                print(f"Hata (Satır {index}): {e}")
                continue

        await session.commit()

    return JSONResponse({
        "status": "success",
        "message": f"Eski veriler temizlendi. {added} yeni kayıt yüklendi."
    })