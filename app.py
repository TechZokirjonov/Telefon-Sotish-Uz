from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Header
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import shutil
import os

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# --- MA'LUMOTLAR VA AUTH ---
import json
import hashlib
import secrets
import uuid
from pathlib import Path

DATA_FILE = "telefon_sotish_data.json"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("admin123".encode("utf-8")).hexdigest()
users_db = {}
listings_db = []
sessions = {}

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def save_data():
    Path(DATA_FILE).write_text(json.dumps({"users": users_db, "listings": listings_db}, ensure_ascii=False, indent=2), encoding="utf-8")

def load_data():
    global users_db, listings_db
    if Path(DATA_FILE).exists():
        try:
            data = json.loads(Path(DATA_FILE).read_text(encoding="utf-8"))
            users_db = data.get("users", {})
            listings_db = data.get("listings", [])
        except Exception:
            users_db, listings_db = {}, []
    if not listings_db:
        listings_db = [
            {"id":1,"username":"admin","brand":"Apple","model":"iPhone 15 Pro Max","storage":"256GB","condition":"Yangi","price":"$1250","phone_number":"+998901234567","description":"Karobka dokument, ochilmagan, garantiya bor.","image":"https://images.unsplash.com/photo-1695048133142-1a20484d2569?auto=format&fit=crop&w=600&q=80"},
            {"id":2,"username":"admin","brand":"Samsung","model":"Galaxy S24 Ultra","storage":"512GB","condition":"Ideal","price":"$1100","phone_number":"+998939876543","description":"Ideal holatda, 1 oydan oshgan, chexol sovg'a.","image":"https://images.unsplash.com/photo-1610945265064-0e34e5519bbf?auto=format&fit=crop&w=600&q=80"}
        ]
        save_data()
load_data()

def current_user(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Avval tizimga kiring!")
    username = sessions.get(authorization.split(" ",1)[1].strip())
    if not username:
        raise HTTPException(status_code=401, detail="Sessiya tugagan. Qayta kiring!")
    return username

@app.post("/api/register")
async def register(username: str = Form(...), password: str = Form(...)):
    username=username.strip()
    if len(username)<3: raise HTTPException(status_code=400,detail="Login kamida 3 ta belgidan iborat bo'lsin!")
    if len(password)<4: raise HTTPException(status_code=400,detail="Parol kamida 4 ta belgidan iborat bo'lsin!")
    if username.lower()=="admin": raise HTTPException(status_code=400,detail="Bu login band!")
    if username in users_db: raise HTTPException(status_code=400,detail="Bu foydalanuvchi nomi band!")
    users_db[username]=hash_password(password); save_data()
    return {"success":True,"message":"Ro'yxatdan o'tdingiz! Endi tizimga kiring."}

@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...)):
    username=username.strip(); ph=hash_password(password)
    if username==ADMIN_USERNAME: valid=secrets.compare_digest(ph,ADMIN_PASSWORD_HASH)
    elif username in users_db: valid=secrets.compare_digest(users_db[username],ph)
    else: valid=False
    if not valid: raise HTTPException(status_code=400,detail="Login yoki parol xato!")
    token=secrets.token_urlsafe(32); sessions[token]=username
    return {"success":True,"message":"Xush kelibsiz!","token":token,"username":username}

@app.post("/api/logout")
async def logout(authorization: str | None = Header(None)):
    if authorization and authorization.startswith("Bearer "): sessions.pop(authorization.split(" ",1)[1].strip(),None)
    return {"success":True}

@app.get("/api/me")
async def me(authorization: str | None = Header(None)):
    return {"success":True,"username":current_user(authorization)}

@app.post("/api/listings")
async def create_listing(brand:str=Form(...),model:str=Form(...),storage:str=Form(...),condition:str=Form(...),price:str=Form(...),phone_number:str=Form(...),description:str=Form(""),image:UploadFile=File(...),authorization:str|None=Header(None)):
    username=current_user(authorization)
    if not image.filename: raise HTTPException(status_code=400,detail="Telefon rasmini tanlang!")
    if image.content_type and not image.content_type.startswith("image/"): raise HTTPException(status_code=400,detail="Faqat rasm yuklash mumkin!")
    ext=Path(image.filename).suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp",".gif"}: ext=".jpg"
    filename=uuid.uuid4().hex+ext
    with open(os.path.join(UPLOAD_DIR,filename),"wb") as buffer: shutil.copyfileobj(image.file,buffer)
    item={"id":max([x["id"] for x in listings_db],default=0)+1,"username":username,"brand":brand.strip(),"model":model.strip(),"storage":storage.strip(),"condition":condition.strip(),"price":price.strip(),"phone_number":phone_number.strip(),"description":description.strip(),"image":f"/uploads/{filename}"}
    listings_db.append(item); save_data()
    return {"success":True,"message":"E'lon muvaffaqiyatli joylandi!","listing":item}

@app.get("/api/listings")
async def get_listings(search:str=Query(None),brand:str=Query(None)):
    result=listings_db.copy()
    if brand and brand!="Barchasi": result=[x for x in result if x.get("brand","").lower()==brand.lower()]
    if search:
        q=search.strip().lower(); result=[x for x in result if q in x.get("model","").lower() or q in x.get("storage","").lower() or q in x.get("brand","").lower()]
    return result

@app.get("/api/listings/{listing_id}")
async def get_listing_detail(listing_id:int):
    for x in listings_db:
        if x["id"]==listing_id:return x
    raise HTTPException(status_code=404,detail="E'lon topilmadi")

@app.delete("/api/listings/{listing_id}")
async def delete_listing(listing_id:int,authorization:str|None=Header(None)):
    global listings_db
    username=current_user(authorization)
    for x in listings_db:
        if x["id"]==listing_id:
            if x["username"]!=username and username!=ADMIN_USERNAME: raise HTTPException(status_code=403,detail="Bu e'lonni o'chirishga ruxsatingiz yo'q!")
            img=x.get("image","")
            if img.startswith("/uploads/"):
                fp=os.path.join(UPLOAD_DIR,img.replace("/uploads/","",1))
                if os.path.exists(fp):
                    try:os.remove(fp)
                    except OSError:pass
            listings_db=[i for i in listings_db if i["id"]!=listing_id];save_data()
            return {"success":True,"message":"E'lon o'chirildi!"}
    raise HTTPException(status_code=404,detail="E'lon topilmadi")

# --- FRONTEND (HTML / CSS / JS) QISMI ---

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telefon Sotish Uz - Neon Blue & White Marketplace</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .neon-glow {
            box-shadow: 0 0 20px rgba(59, 130, 246, 0.25), inset 0 0 15px rgba(255, 255, 255, 0.05);
        }
        .neon-border {
            border: 1px solid rgba(59, 130, 246, 0.3);
        }
        .neon-border:focus-within, .neon-border:hover {
            border-color: rgba(255, 255, 255, 0.8);
            box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
        }
    </style>
</head>
<body class="bg-[#050b14] text-zinc-100 font-sans antialiased min-h-screen flex flex-col justify-between selection:bg-blue-500 selection:text-white">

    <!-- TOP HEADER NAVBAR -->
    <header class="bg-[#081222] border-b border-blue-900/40 sticky top-0 z-40 backdrop-blur-md bg-opacity-90">
        <div class="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3 cursor-pointer" onclick="filterBrand('Barchasi')">
                <div class="bg-blue-600 text-white p-2 rounded-xl font-black text-lg shadow-[0_0_15px_rgba(59,130,246,0.6)]">
                    <i class="fa-solid fa-mobile-screen-button"></i>
                </div>
                <div>
                    <h1 class="font-black tracking-wider text-lg leading-none text-white drop-shadow-[0_0_10px_rgba(255,255,255,0.7)]">TELEFON SOTISH</h1>
                    <span class="text-[10px] text-blue-400 font-semibold tracking-widest uppercase">Neon Blue & White</span>
                </div>
            </div>

            <!-- SEARCH BAR IN NAVBAR -->
            <div class="hidden md:flex flex-1 max-w-md mx-8">
                <div class="relative w-full">
                    <input type="text" id="searchInput" placeholder="Model, brend yoki xotira bo'yicha qidirish..." oninput="loadListings()" class="w-full bg-[#0d1b30] text-sm text-white placeholder-zinc-400 px-4 py-2.5 pl-10 rounded-xl focus:outline-none focus:ring-2 focus:ring-white border border-blue-900/50 transition">
                    <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-3.5 text-blue-400 text-sm"></i>
                </div>
            </div>

            <!-- ACTIONS / PROFILE -->
            <div class="flex items-center gap-3">
                <button onclick="openCartModal()" class="relative bg-[#0d1b30] hover:bg-blue-900/50 p-2.5 rounded-xl text-zinc-300 border border-blue-900/40 transition">
                    <i class="fa-solid fa-cart-shopping"></i>
                    <span id="cartCount" class="absolute -top-1 -right-1 bg-white text-blue-950 text-[10px] font-black w-5 h-5 rounded-full flex items-center justify-center shadow-[0_0_10px_rgba(255,255,255,0.8)]">0</span>
                </button>
                <div id="userProfileArea">
                    <button onclick="openAuthModal()" class="bg-white hover:bg-blue-100 text-blue-950 px-4 py-2 rounded-xl text-sm font-black transition shadow-[0_0_15px_rgba(255,255,255,0.4)]">
                        Kirish
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- MOBILE SEARCH BAR -->
    <div class="md:hidden bg-[#081222] px-4 pb-3 border-b border-blue-900/40">
        <div class="relative w-full">
            <input type="text" id="mobileSearchInput" placeholder="Model bo'yicha qidirish..." oninput="syncAndLoad(this.value)" class="w-full bg-[#0d1b30] text-sm text-white placeholder-zinc-400 px-4 py-2.5 pl-10 rounded-xl border border-blue-900/50 focus:outline-none focus:ring-1 focus:ring-white">
            <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-3 text-blue-400 text-sm"></i>
        </div>
    </div>

    <!-- MAIN CONTENT CONTAINER -->
    <main class="max-w-7xl mx-auto px-4 py-6 space-y-8 flex-grow w-full">
        
        <!-- HERO SECTION -->
        <section class="bg-gradient-to-r from-[#0a1628] via-[#0d1f38] to-[#060f1e] rounded-3xl p-6 md:p-10 text-white border border-blue-900/40 shadow-[0_0_35px_rgba(59,130,246,0.15)] flex flex-col md:flex-row items-center justify-between gap-6 relative overflow-hidden">
            <div class="absolute right-0 bottom-0 opacity-10 translate-x-10 translate-y-10 text-9xl text-blue-400">
                <i class="fa-solid fa-mobile"></i>
            </div>
            <div class="space-y-4 max-w-xl z-10">
                <span class="bg-blue-950/80 backdrop-blur-md text-blue-300 text-xs font-bold px-3.5 py-1.5 rounded-full uppercase tracking-wider border border-blue-800 shadow-[0_0_12px_rgba(59,130,246,0.3)]">Neon Blue & White Edition</span>
                <h2 class="text-3xl md:text-5xl font-black tracking-tight leading-tight text-white drop-shadow-[0_0_10px_rgba(255,255,255,0.4)]">Orzuingizdagi smartfonni toping yoki soting</h2>
                <p class="text-blue-200/80 text-sm md:text-base">Yangi va ishlatilgan telefonlar savdosi uchun zamonaviy xavfsiz platforma.</p>
            </div>
            <div class="z-10 w-full md:w-auto">
                <button onclick="checkAuthAndOpenAdd()" class="w-full md:w-auto bg-white text-blue-950 px-6 py-3.5 rounded-2xl font-black shadow-[0_0_20px_rgba(255,255,255,0.4)] hover:bg-blue-100 transition text-center">
                    <i class="fa-solid fa-plus mr-2"></i> E'lon Joylash
                </button>
            </div>
        </section>

        <!-- CATEGORIES / BRANDS FILTER SECTION -->
        <section>
            <h3 class="text-lg font-bold text-white mb-3 drop-shadow-[0_0_5px_rgba(255,255,255,0.3)]">Brendlar bo'yicha</h3>
            <div class="flex items-center gap-3 overflow-x-auto pb-2 scrollbar-none">
                <button onclick="filterBrand('Barchasi')" class="brand-btn bg-white text-blue-950 px-5 py-2.5 rounded-2xl text-sm font-black shadow-[0_0_15px_rgba(255,255,255,0.4)] whitespace-nowrap transition">Barchasi</button>
                <button onclick="filterBrand('Apple')" class="brand-btn bg-[#0d1b30] text-blue-200 hover:text-white px-5 py-2.5 rounded-2xl text-sm font-bold shadow-sm whitespace-nowrap border border-blue-900/50 transition">Apple iPhone</button>
                <button onclick="filterBrand('Samsung')" class="brand-btn bg-[#0d1b30] text-blue-200 hover:text-white px-5 py-2.5 rounded-2xl text-sm font-bold shadow-sm whitespace-nowrap border border-blue-900/50 transition">Samsung</button>
                <button onclick="filterBrand('Xiaomi')" class="brand-btn bg-[#0d1b30] text-blue-200 hover:text-white px-5 py-2.5 rounded-2xl text-sm font-bold shadow-sm whitespace-nowrap border border-blue-900/50 transition">Xiaomi / Redmi</button>
                <button onclick="filterBrand('Artel')" class="brand-btn bg-[#0d1b30] text-blue-200 hover:text-white px-5 py-2.5 rounded-2xl text-sm font-bold shadow-sm whitespace-nowrap border border-blue-900/50 transition">Artel</button>
                <button onclick="filterBrand('Other')" class="brand-btn bg-[#0d1b30] text-blue-200 hover:text-white px-5 py-2.5 rounded-2xl text-sm font-bold shadow-sm whitespace-nowrap border border-blue-900/50 transition">Boshqalar</button>
            </div>
        </section>

        <!-- PRODUCT CATALOG SECTION -->
        <section class="space-y-4">
            <div class="flex items-center justify-between">
                <h3 class="text-xl font-black text-white drop-shadow-[0_0_6px_rgba(255,255,255,0.4)]">Mavjud E'lonlar</h3>
                <span id="resultCount" class="text-xs font-bold text-blue-300 bg-[#0d1b30] border border-blue-900/50 px-3 py-1 rounded-full shadow-[0_0_8px_rgba(59,130,246,0.2)]">0 ta e'lon</span>
            </div>

            <!-- CARDS GRID CONTAINER -->
            <div id="listingsContainer" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                <div class="col-span-full py-16 text-center text-blue-400">
                    <i class="fa-solid fa-spinner fa-spin text-2xl mb-2 text-white"></i>
                    <p class="text-sm">Yuklanmoqda...</p>
                </div>
            </div>
        </section>
    </main>

    <!-- FOOTER -->
    <footer class="bg-[#081222] text-blue-200/70 mt-20 border-t border-blue-900/40">
        <div class="max-w-7xl mx-auto px-4 py-12 grid grid-cols-1 md:grid-cols-4 gap-8">
            <div class="space-y-4 md:col-span-1">
                <div class="flex items-center gap-2 text-white">
                    <i class="fa-solid fa-mobile-screen-button text-white text-xl drop-shadow-[0_0_10px_rgba(255,255,255,0.8)]"></i>
                    <span class="font-black text-lg">Telefon Sotish Uz</span>
                </div>
                <p class="text-xs leading-relaxed text-blue-300/70">O'zbekistondagi eng tezkor, qulay va xavfsiz mobil qurilmalar savdo platformasi.</p>
            </div>
            <div>
                <h4 class="font-bold text-xs uppercase tracking-wider text-white mb-3">Kategoriyalar</h4>
                <ul class="space-y-2 text-xs">
                    <li><a href="#" onclick="filterBrand('Apple')" class="hover:text-white transition">iPhone modellari</a></li>
                    <li><a href="#" onclick="filterBrand('Samsung')" class="hover:text-white transition">Samsung Galaxy</a></li>
                    <li><a href="#" onclick="filterBrand('Xiaomi')" class="hover:text-white transition">Xiaomi smartfonlari</a></li>
                </ul>
            </div>
            <div>
                <h4 class="font-bold text-xs uppercase tracking-wider text-white mb-3">Ma'lumot</h4>
                <ul class="space-y-2 text-xs">
                    <li><a href="#" class="hover:text-white transition">Foydalanish shartlari</a></li>
                    <li><a href="#" class="hover:text-white transition">Xavfsizlik qoidalari</a></li>
                    <li><a href="#" class="hover:text-white transition">Reklama berish</a></li>
                </ul>
            </div>
            <div>
                <h4 class="font-bold text-xs uppercase tracking-wider text-white mb-3">Bog'lanish</h4>
                <p class="text-xs mb-1 text-blue-300/70">Telegram qo'llab-quvvatlash:</p>
                <span class="text-sm font-bold text-white drop-shadow-[0_0_6px_rgba(255,255,255,0.5)]">@telefonsotish_support</span>
            </div>
        </div>
        <div class="border-t border-blue-900/40 text-center py-4 text-xs text-blue-400/60">
            © 2026 Telefon Sotish Uz. Barcha huquqlar himoyalangan.
        </div>
    </footer>

    <!-- AUTH MODAL -->
    <div id="authModal" class="fixed inset-0 bg-[#03070e]/85 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
        <div class="bg-[#091424] border border-blue-900/60 w-full max-w-md p-8 rounded-3xl shadow-[0_0_35px_rgba(59,130,246,0.2)] space-y-6 relative">
            <div class="flex justify-between items-center">
                <h3 id="authTitle" class="text-xl font-black text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.5)]">Tizimga kirish</h3>
                <button onclick="closeAuthModal()" class="text-blue-400 hover:text-white font-bold text-xl"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <form id="authForm" class="space-y-4">
                <input type="text" id="authUsername" placeholder="Foydalanuvchi nomi" required class="w-full px-4 py-3.5 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white placeholder-blue-300/50">
                <input type="password" id="authPassword" placeholder="Parol" required class="w-full px-4 py-3.5 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white placeholder-blue-300/50">
                <button type="submit" id="authSubmitBtn" class="w-full bg-white hover:bg-blue-100 text-blue-950 py-3.5 rounded-2xl font-black transition shadow-[0_0_20px_rgba(255,255,255,0.4)]">Kirish</button>
            </form>
            <div class="text-center">
                <button type="button" onclick="toggleAuthMode()" id="toggleAuthText" class="text-xs text-blue-300 font-semibold hover:text-white transition">Akkauntingiz yo'qmi? Ro'yxatdan o'ting</button>
            </div>
            <p id="authMsg" class="text-center text-xs font-semibold"></p>
        </div>
    </div>

    <!-- ADD LISTING MODAL -->
    <div id="addModal" class="fixed inset-0 bg-[#03070e]/85 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
        <div class="bg-[#091424] border border-blue-900/60 w-full max-w-lg p-8 rounded-3xl shadow-[0_0_35px_rgba(59,130,246,0.2)] space-y-6 relative max-h-[90vh] overflow-y-auto">
            <div class="flex justify-between items-center">
                <h3 class="text-xl font-black text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.5)]">Yangi e'lon joylash</h3>
                <button onclick="closeAddModal()" class="text-blue-400 hover:text-white font-bold text-xl"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <form id="phoneForm" class="space-y-4">
                <div>
                    <label class="block text-xs font-bold text-blue-300 mb-1">Telefon rasmi</label>
                    <input type="file" id="imageInput" accept="image/*" capture="environment" required class="w-full text-xs text-blue-200 file:mr-3 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:bg-blue-900/60 file:text-white font-bold cursor-pointer">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <select id="brandInput" required class="w-full px-4 py-3 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white font-medium">
                        <option value="" class="bg-[#0d1d35]">Brendni tanlang</option>
                        <option value="Apple" class="bg-[#0d1d35]">Apple iPhone</option>
                        <option value="Samsung" class="bg-[#0d1d35]">Samsung</option>
                        <option value="Xiaomi" class="bg-[#0d1d35]">Xiaomi</option>
                        <option value="Artel" class="bg-[#0d1d35]">Artel</option>
                        <option value="Other" class="bg-[#0d1d35]">Boshqa</option>
                    </select>
                    <input type="text" id="modelInput" placeholder="Model (Masalan: 14 Pro)" required class="w-full px-4 py-3 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white placeholder-blue-300/50">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <input type="text" id="storageInput" placeholder="Xotira (Masalan: 256GB)" required class="w-full px-4 py-3 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white placeholder-blue-300/50">
                    <select id="conditionInput" required class="w-full px-4 py-3 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white font-medium">
                        <option value="Yangi" class="bg-[#0d1d35]">Yangi (Qutida)</option>
                        <option value="Ideal" class="bg-[#0d1d35]">Ideal holatda</option>
                        <option value="Yaxshi" class="bg-[#0d1d35]">Yaxshi holatda</option>
                        <option value="Ishlatilgan" class="bg-[#0d1d35]">Ishlatilgan</option>
                    </select>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <input type="text" id="priceInput" placeholder="Narxi (Masalan: $850)" required class="w-full px-4 py-3 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white placeholder-blue-300/50">
                    <input type="tel" id="phoneInput" placeholder="Telefon (+998...)" required class="w-full px-4 py-3 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white placeholder-blue-300/50">
                </div>
                <textarea id="descInput" placeholder="Qo'shimcha ma'lumot (karobka, holati, aksiya...)" rows="3" class="w-full px-4 py-3 border border-blue-900/50 rounded-2xl text-sm focus:outline-none focus:ring-1 focus:ring-white bg-[#0d1d35] text-white placeholder-blue-300/50"></textarea>
                <button type="submit" class="w-full bg-white hover:bg-blue-100 text-blue-950 py-3.5 rounded-2xl font-black transition shadow-[0_0_20px_rgba(255,255,255,0.4)]">E'lonni e'lon qilish</button>
            </form>
        </div>
    </div>

    <!-- DETAIL PRODUCT MODAL -->
    <div id="detailModal" class="fixed inset-0 bg-[#03070e]/85 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
        <div class="bg-[#091424] border border-blue-900/60 w-full max-w-2xl p-6 md:p-8 rounded-3xl shadow-[0_0_35px_rgba(59,130,246,0.2)] relative max-h-[90vh] overflow-y-auto" id="detailContent">
            <!-- Dynamic loaded detail info -->
        </div>
    </div>

    <!-- CART MODAL -->
    <div id="cartModal" class="fixed inset-0 bg-[#03070e]/85 backdrop-blur-sm hidden items-center justify-center p-4 z-50">
        <div class="bg-[#091424] border border-blue-900/60 w-full max-w-md p-6 rounded-3xl shadow-[0_0_35px_rgba(59,130,246,0.2)] space-y-4 relative">
            <div class="flex justify-between items-center border-b border-blue-900/40 pb-3">
                <h3 class="text-lg font-black text-white drop-shadow-[0_0_6px_rgba(255,255,255,0.4)]"><i class="fa-solid fa-cart-shopping mr-2 text-white"></i> Tanlanganlar (Savatcha)</h3>
                <button onclick="closeCartModal()" class="text-blue-400 hover:text-white font-bold text-lg"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div id="cartItemsContainer" class="space-y-3 max-h-60 overflow-y-auto">
                <p class="text-blue-300/60 text-center text-sm py-6">Savatchangiz bo'sh</p>
            </div>
            <div class="border-t border-blue-900/40 pt-3 flex justify-between items-center font-bold text-white">
                <span>Jami mahsulotlar:</span>
                <span id="cartTotalCount" class="drop-shadow-[0_0_6px_rgba(255,255,255,0.5)]">0 ta</span>
            </div>
            <button onclick="alert('Buyurtmangiz qabul qilindi! Sotuvchi tez orada aloqa qiladi.')" class="w-full bg-white hover:bg-blue-100 text-blue-950 py-3 rounded-xl font-black transition shadow-[0_0_20px_rgba(255,255,255,0.4)]">Buyurtmani rasmiylashtirish</button>
        </div>
    </div>

    <script>
let isRegisterMode=false;
let loggedUser=localStorage.getItem('username')||null;
let selectedBrand='Barchasi';
let cart=JSON.parse(localStorage.getItem('cart')||'[]');

function updateUIState(){
 const a=document.getElementById('userProfileArea');
 if(a)a.innerHTML=loggedUser?`<div class="flex items-center gap-2"><span class="text-xs font-bold bg-[#0d1b30] border border-blue-900/50 px-3 py-2 rounded-xl text-white hidden sm:inline">@${loggedUser}</span><button onclick="logout()" class="bg-blue-950 hover:bg-red-500/20 text-blue-300 hover:text-red-400 px-3 py-2 rounded-xl text-xs font-bold transition border border-blue-900/50"><i class="fa-solid fa-right-from-bracket"></i></button></div>`:`<button onclick="openAuthModal()" class="bg-white hover:bg-blue-100 text-blue-950 px-4 py-2 rounded-xl text-sm font-black transition">Kirish</button>`;
 updateCartCount();
}
function filterBrand(brand){selectedBrand=brand;document.querySelectorAll('.brand-btn').forEach(b=>b.classList.toggle('bg-white',b.textContent.trim()===brand));loadListings();}
function syncAndLoad(v){const i=document.getElementById('searchInput');if(i)i.value=v;loadListings();}
async function loadListings(){
 try{
  const q=document.getElementById('searchInput')?.value||'';
  let url='/api/listings?search='+encodeURIComponent(q);
  if(selectedBrand&&selectedBrand!=='Barchasi')url+='&brand='+encodeURIComponent(selectedBrand);
  const r=await fetch(url);const phones=await r.json();
  const c=document.getElementById('listingsContainer');if(!c)return;
  const rc=document.getElementById('resultCount');if(rc)rc.textContent=`${phones.length} ta e'lon`;
  if(!phones.length){c.innerHTML=`<div class="col-span-full py-16 text-center text-blue-300/60"><i class="fa-solid fa-box-open text-3xl"></i><p class="text-sm mt-2">Hech qanday e'lon topilmadi</p></div>`;return;}
  c.innerHTML=phones.map(p=>`<div class="bg-[#091424] border border-blue-900/50 rounded-3xl shadow-sm hover:shadow-[0_0_25px_rgba(59,130,246,0.3)] transition overflow-hidden flex flex-col justify-between group"><div><div class="w-full h-52 bg-[#060f1e] relative overflow-hidden cursor-pointer" onclick="openDetail(${p.id})"><span class="absolute top-3 left-3 bg-white text-blue-950 text-[10px] font-black px-2.5 py-1 rounded-full z-10">${p.condition||'-'}</span><img src="${p.image}" alt="${p.model}" class="w-full h-full object-cover group-hover:scale-105 transition duration-500 opacity-90"></div><div class="p-4 space-y-1.5"><div class="flex justify-between items-start"><span class="text-[10px] font-bold uppercase tracking-wider text-blue-400">${p.brand||'-'}</span><span class="text-xs font-semibold text-blue-200/70"><i class="fa-solid fa-hard-drive mr-1"></i>${p.storage||'-'}</span></div><h4 onclick="openDetail(${p.id})" class="font-black text-white text-base truncate cursor-pointer hover:text-blue-200">${p.model||'-'}</h4><div class="text-white font-black text-lg pt-1">${p.price||'-'}</div></div></div><div class="p-4 pt-0 border-t border-blue-900/40 mt-2 flex items-center justify-between"><span class="text-xs font-semibold text-blue-200/70"><i class="fa-solid fa-phone text-white mr-1"></i>${p.phone_number||'-'}</span><button onclick="addToCart(${p.id})" class="bg-blue-950 hover:bg-white text-blue-200 hover:text-blue-950 p-2.5 rounded-xl text-xs font-bold transition border border-blue-900/50"><i class="fa-solid fa-cart-plus"></i></button></div></div>`).join('');
 }catch(e){console.error(e);}
}
async function openDetail(id){
 const r=await fetch(`/api/listings/${id}`);if(!r.ok)return;const p=await r.json();
 const owner=loggedUser&&(loggedUser===p.username||loggedUser==='admin');
 document.getElementById('detailContent').innerHTML=`<div class="flex justify-between items-center border-b border-blue-900/40 pb-3 mb-4"><h3 class="text-xl font-black text-white">${p.model}</h3><button onclick="closeDetailModal()" class="text-blue-400 hover:text-white font-bold text-xl"><i class="fa-solid fa-xmark"></i></button></div><div class="grid grid-cols-1 md:grid-cols-2 gap-6"><div class="h-64 bg-[#060f1e] rounded-2xl overflow-hidden border border-blue-900/50"><img src="${p.image}" class="w-full h-full object-cover"></div><div class="space-y-3"><div class="text-2xl font-black text-white">${p.price}</div><p class="text-xs text-blue-200/70">Brend: <b class="text-white">${p.brand}</b> | Xotira: <b class="text-white">${p.storage}</b></p><p class="text-xs text-blue-200/70">Holati: <b class="text-white">${p.condition}</b></p><p class="text-xs text-blue-200/70">Aloqa: <b class="text-white">${p.phone_number}</b></p><div class="bg-[#0d1d35] p-3 rounded-xl border border-blue-900/50 text-xs text-blue-200">${p.description||"Qo'shimcha ma'lumot yo'q."}</div>${owner?`<button onclick="deleteListing(${p.id})" class="w-full bg-red-500/20 border border-red-500/50 hover:bg-red-500 text-red-300 hover:text-white py-2.5 rounded-xl font-bold text-xs transition"><i class="fa-solid fa-trash mr-1"></i>E'lonni o'chirish</button>`:''}</div></div>`;
 const m=document.getElementById('detailModal');m.classList.remove('hidden');m.classList.add('flex');
}
function closeDetailModal(){const m=document.getElementById('detailModal');m.classList.add('hidden');m.classList.remove('flex');}
async function deleteListing(id){if(!confirm("Rostdan ham bu e'lonni o'chirmoqchimisiz?"))return;const t=localStorage.getItem('token');if(!t)return openAuthModal();const r=await fetch(`/api/listings/${id}`,{method:'DELETE',headers:{Authorization:`Bearer ${t}`}});const d=await r.json();if(r.ok){closeDetailModal();loadListings();alert("E'lon o'chirildi!");}else alert(d.detail||'Xatolik!');}
async function addToCart(id){const r=await fetch(`/api/listings/${id}`);if(!r.ok)return;const p=await r.json();if(cart.some(x=>x.id===p.id))return alert('Bu mahsulot savatchada bor!');cart.push({id:p.id,model:p.model,price:p.price,image:p.image});localStorage.setItem('cart',JSON.stringify(cart));updateCartCount();alert("Mahsulot savatchaga qo'shildi!");}
function updateCartCount(){const c=document.getElementById('cartCount');if(c)c.textContent=cart.length;}
function openCartModal(){const c=document.getElementById('cartItemsContainer');if(!c)return;document.getElementById('cartTotalCount').textContent=`${cart.length} ta`;c.innerHTML=cart.length?cart.map((x,i)=>`<div class="flex items-center justify-between border-b border-blue-900/40 pb-2"><div class="flex items-center gap-3"><img src="${x.image}" class="w-12 h-12 object-cover rounded-xl"><div><h5 class="font-bold text-white text-sm">${x.model}</h5><span class="text-white font-black text-xs">${x.price}</span></div></div><button onclick="removeFromCart(${i})" class="text-blue-400 hover:text-red-400"><i class="fa-solid fa-trash"></i></button></div>`).join(''):`<p class="text-blue-300/60 text-center text-sm py-6">Savatchangiz bo'sh</p>`;const m=document.getElementById('cartModal');m.classList.remove('hidden');m.classList.add('flex');}
function closeCartModal(){const m=document.getElementById('cartModal');m.classList.add('hidden');m.classList.remove('flex');}
function removeFromCart(i){cart.splice(i,1);localStorage.setItem('cart',JSON.stringify(cart));updateCartCount();openCartModal();}
function openAuthModal(){const m=document.getElementById('authModal');m.classList.remove('hidden');m.classList.add('flex');}
function closeAuthModal(){const m=document.getElementById('authModal');m.classList.add('hidden');m.classList.remove('flex');}
function toggleAuthMode(){isRegisterMode=!isRegisterMode;document.getElementById('authTitle').textContent=isRegisterMode?"Ro'yxatdan o'tish":"Tizimga kirish";document.getElementById('authSubmitBtn').textContent=isRegisterMode?"Ro'yxatdan o'tish":"Kirish";document.getElementById('toggleAuthText').textContent=isRegisterMode?"Akkauntingiz bormi? Tizimga kiring":"Akkauntingiz yo'qmi? Ro'yxatdan o'ting";}
async function getStoredSession(){const t=localStorage.getItem('token');if(!t){loggedUser=null;return false;}try{const r=await fetch('/api/me',{headers:{Authorization:`Bearer ${t}`}});if(!r.ok){localStorage.removeItem('token');localStorage.removeItem('username');loggedUser=null;return false;}const d=await r.json();loggedUser=d.username;localStorage.setItem('username',loggedUser);return true;}catch(e){return false;}}

document.getElementById('authForm').addEventListener('submit',async e=>{e.preventDefault();const u=document.getElementById('authUsername').value.trim(),p=document.getElementById('authPassword').value,msg=document.getElementById('authMsg'),btn=document.getElementById('authSubmitBtn');const fd=new FormData();fd.append('username',u);fd.append('password',p);btn.disabled=true;try{const r=await fetch(isRegisterMode?'/api/register':'/api/login',{method:'POST',body:fd});const d=await r.json();if(!r.ok){msg.textContent=d.detail||'Xatolik!';msg.className='text-center text-xs font-semibold text-red-400';return;}msg.textContent=d.message||'Muvaffaqiyatli!';if(!isRegisterMode){loggedUser=d.username;localStorage.setItem('username',d.username);localStorage.setItem('token',d.token);setTimeout(()=>{closeAuthModal();updateUIState();document.getElementById('authForm').reset();},400);}else{toggleAuthMode();document.getElementById('authPassword').value='';}}catch(e){msg.textContent="Server bilan bog'lanib bo'lmadi!";msg.className='text-center text-xs font-semibold text-red-400';}finally{btn.disabled=false;btn.textContent=isRegisterMode?"Ro'yxatdan o'tish":"Kirish";}});
async function logout(){const t=localStorage.getItem('token');if(t)try{await fetch('/api/logout',{method:'POST',headers:{Authorization:`Bearer ${t}`}})}catch(e){}localStorage.removeItem('token');localStorage.removeItem('username');loggedUser=null;updateUIState();}
async function checkAuthAndOpenAdd(){if(!(await getStoredSession())){alert("E'lon berish uchun oldin tizimga kiring!");openAuthModal();return;}const m=document.getElementById('addModal');m.classList.remove('hidden');m.classList.add('flex');}
function closeAddModal(){const m=document.getElementById('addModal');m.classList.add('hidden');m.classList.remove('flex');}
document.getElementById('phoneForm').addEventListener('submit',async e=>{e.preventDefault();const t=localStorage.getItem('token');if(!t){alert('Avval tizimga kiring!');openAuthModal();return;}const file=document.getElementById('imageInput').files[0];if(!file)return alert('Telefon rasmini tanlang!');const fd=new FormData();fd.append('image',file);['brandInput','modelInput','storageInput','conditionInput','priceInput','phoneInput','descInput'].forEach((id,i)=>fd.append(['brand','model','storage','condition','price','phone_number','description'][i],document.getElementById(id).value));try{const r=await fetch('/api/listings',{method:'POST',headers:{Authorization:`Bearer ${t}`},body:fd});const d=await r.json();if(r.ok){alert("E'lon muvaffaqiyatli joylandi! 🎉");document.getElementById('phoneForm').reset();closeAddModal();loadListings();}else alert(d.detail||'Xatolik!');}catch(e){alert("Server bilan bog'lanib bo'lmadi!");}});
(async()=>{await getStoredSession();updateUIState();loadListings();})();
</script>

</body>
</html>
    """
