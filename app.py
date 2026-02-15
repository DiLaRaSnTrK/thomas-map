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
from deep_translator import GoogleTranslator
from sqlalchemy import delete


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
    query = select(Place).order_by(Place.id)
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

# app.py dosyasına eklenecek yeni rotalar

@app.get("/admin/delete/{place_id}")
async def delete_place(place_id: int, user: str = Depends(check_login)):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
        if place:
            await session.delete(place)
            await session.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/edit/{place_id}", response_class=HTMLResponse)
async def edit_page(request: Request, place_id: int, user: str = Depends(check_login)):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
    return templates.TemplateResponse("edit.html", {"request": request, "place": place})

@app.post("/admin/edit/{place_id}")
async def edit_place(
    place_id: int,
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
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
        if place:
            place.name_historic = name_historic
            place.name_modern = name_modern
            place.latitude = latitude
            place.longitude = longitude
            place.is_in_ottoman = is_in_ottoman
            place.description_tr = description_tr
            place.description_en = description_en
            await session.commit()
    return RedirectResponse(url="/admin", status_code=303)

# ---------------- Excel'den Veri Yükleme ----------------
# --- app.py içindeki load_excel fonksiyonunu bu şekilde güncelleyin ---
# app.py içindeki ilgili kısımları bu şekilde güncelleyin

@app.get("/load_excel")
async def load_excel():
    # 1. Dosya Kontrolü
    # Not: Excel dosyanızın adı tam olarak '123.xlsx' olmalı ve 'data' klasöründe bulunmalıdır.
    excel_path = Path("data/123.xlsx")
    if not excel_path.exists():
        return JSONResponse({"error": f"Excel dosyası '{excel_path}' bulunamadı!"}, status_code=404)

    # 2. Excel'i Oku ve Sütunları Standartlaştır
    df = pd.read_excel(excel_path)
    
    # Türkçe karakter ve boşluk sorunlarını çözmek için sütun isimlerini temizliyoruz
    original_cols = df.columns.tolist()
    df.columns = [str(c).strip().lower().replace('ı', 'i').replace('i̇', 'i') for c in df.columns]

    # 3. Çeviri Motorunu Başlat (Türkçe -> İngilizce)
    translator = GoogleTranslator(source='tr', target='en')

    async with SessionLocal() as session:
        # 4. Önce Mevcut Verileri Temizle (Sıfırdan temiz bir yükleme için)
        await session.execute(delete(Place))
        await session.commit()

        added = 0
        # Excel'deki 'NO' sütunu varsa ona göre, yoksa satır sırasına göre yükleme yapar
        # Bu, haritadaki çizgilerin (polyline) doğru sırayla çizilmesini sağlar.
        for index, row in df.iterrows():
            try:
                # --- Dinamik Sütun Yakalama ---
                # Sütun isimleri değişse bile anahtar kelimelerden doğru veriyi bulur
                lat_col = next((c for c in df.columns if 'enlem' in c or 'lat' in c), None)
                lon_col = next((c for c in df.columns if 'boylam' in c or 'lon' in c), None)
                osman_col = next((c for c in df.columns if 'osman' in c), None)
                hist_col = next((c for c in df.columns if 'tarih' in c), None)
                mod_col = next((c for c in df.columns if 'lokasyon' in c or 'modern' in c), None)
                info_col = next((c for c in df.columns if 'bilgi' in c or 'desc' in c), None)

                # Koordinat yoksa bu satırı atla
                if not lat_col or not lon_col or pd.isna(row[lat_col]):
                    continue

                # --- Osmanlı Toprağı Kontrolü ---
                is_ottoman_val = False
                if osman_col:
                    val = str(row[osman_col]).strip().lower()
                    # 'Evet', 'True', '1' veya 'Yes' değerlerini yakalar
                    is_ottoman_val = val in ["evet", "true", "1", "yes"]

                # --- Otomatik Çeviri İşlemi ---
                desc_tr = str(row.get(info_col, "")) if info_col else ""
                desc_en = ""
                
                if desc_tr and desc_tr != "nan" and desc_tr.strip() != "":
                    try:
                        # Bilgi metnini otomatik olarak İngilizceye çevirir
                        desc_en = translator.translate(desc_tr)
                    except Exception as e:
                        print(f"Çeviri hatası (Satır {index}): {e}")
                        desc_en = "" # Hata olursa boş bırakır

                # 5. Veritabanı Nesnesini Oluştur
                place = Place(
                    name_historic=str(row.get(hist_col, "")) if hist_col else "",
                    name_modern=str(row.get(mod_col, "")) if mod_col else "",
                    latitude=float(row[lat_col]),
                    longitude=float(row[lon_col]),
                    is_in_ottoman=is_ottoman_val,
                    description_tr=desc_tr,
                    description_en=desc_en  # Otomatik doldurulan İngilizce alan
                )
                
                session.add(place)
                added += 1

            except Exception as e:
                print(f"Satır {index} işlenirken hata oluştu: {e}")
                continue

        # 6. Tüm Değişiklikleri Kaydet
        await session.commit()

    return JSONResponse({
        "status": "success",
        "message": f"Eski veriler temizlendi. {added} yeni kayıt otomatik çevirileriyle birlikte eklendi."
    })

# DÜZENLEME VE SİLME ROTALARI (Admin paneli butonları için)
@app.get("/admin/delete/{place_id}")
async def delete_place(place_id: int, user: str = Depends(check_login)):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
        if place:
            await session.delete(place)
            await session.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/edit/{place_id}", response_class=HTMLResponse)
async def edit_page(request: Request, place_id: int, user: str = Depends(check_login)):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
    return templates.TemplateResponse("edit.html", {"request": request, "place": place})

@app.post("/admin/edit/{place_id}")
async def edit_save(place_id: int, name_historic: str = Form(...), name_modern: str = Form(...), 
                    latitude: float = Form(...), longitude: float = Form(...), 
                    is_in_ottoman: bool = Form(False), description_tr: str = Form(""), 
                    user: str = Depends(check_login)):
    async with SessionLocal() as session:
        query = select(Place).where(Place.id == place_id)
        result = await session.execute(query)
        place = result.scalar_one_or_none()
        if place:
            place.name_historic = name_historic
            place.name_modern = name_modern
            place.latitude = latitude
            place.longitude = longitude
            place.is_in_ottoman = is_in_ottoman
            place.description_tr = description_tr
            await session.commit()
    return RedirectResponse(url="/admin", status_code=303)