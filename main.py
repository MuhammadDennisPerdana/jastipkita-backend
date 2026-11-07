from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from typing import List, Optional
import os
from dotenv import load_dotenv

# ⭐ 1. LOAD ENVIRONMENT VARIABLES DARI FILE .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Cek apakah DATABASE_URL ada di .env
if not DATABASE_URL:
    raise ValueError("❌ ERROR: DATABASE_URL tidak ditemukan di file .env! Pastikan file .env ada di folder yang sama dengan main.py.")

# ⭐ 2. INISIALISASI APP & CORS
app = FastAPI(title="JastipKita API", version="1.0.0")

# Izinkan Flutter (HP/Emulator) untuk akses API ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper untuk koneksi database
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail="Gagal koneksi ke database")

# ==========================================
# 3. MODELS (Format Data dari Flutter)
# ==========================================

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str  # 'buyer' atau 'jastiper'

class LoginRequest(BaseModel):
    email: str
    password: str

class OrderRequest(BaseModel):
    buyer_id: int
    jastiper_id: int
    item_name: str
    total_amount: float

class UpdateStatusRequest(BaseModel):
    status: str  # 'waiting_payment', 'paid', 'shopping', 'delivered', 'completed'

# ==========================================
# 4. ENDPOINTS (API Routes)
# ==========================================

@app.get("/")
def read_root():
    return {"message": "JastipKita Backend is Running! 🚀", "status": "active"}

# --- AUTH ---

@app.post("/api/register")
def register(user: RegisterRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Cek email duplikat
        cur.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Email sudah terdaftar!")

        # Insert user baru
        cur.execute(
            "INSERT INTO users (email, password, full_name, role) VALUES (%s, %s, %s, %s) RETURNING id, full_name, role",
            (user.email, user.password, user.full_name, user.role)
        )
        new_user = cur.fetchone()
        conn.commit()
        
        return {
            "message": "Register berhasil!",
            "user_id": new_user[0],
            "full_name": new_user[1],
            "role": new_user[2]
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/api/login")
def login(user: LoginRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, full_name, role FROM users WHERE email = %s AND password = %s", 
            (user.email, user.password)
        )
        found_user = cur.fetchone()
        
        if not found_user:
            raise HTTPException(status_code=401, detail="Email atau password salah!")
            
        return {
            "message": "Login berhasil!",
            "user_id": found_user[0],
            "full_name": found_user[1],
            "role": found_user[2]
        }
    finally:
        cur.close()
        conn.close()

# --- ORDERS ---

@app.post("/api/orders")
def create_order(order: OrderRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO orders (buyer_id, jastiper_id, item_name, total_amount, status) VALUES (%s, %s, %s, %s, 'waiting_payment') RETURNING id",
            (order.buyer_id, order.jastiper_id, order.item_name, order.total_amount)
        )
        new_order = cur.fetchone()
        conn.commit()
        
        return {"message": "Order berhasil dibuat!", "order_id": new_order[0]}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.get("/api/orders/{user_id}")
def get_orders(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT o.id, o.item_name, o.total_amount, o.status, o.created_at,
                      b.full_name as buyer_name, j.full_name as jastiper_name
               FROM orders o
               JOIN users b ON o.buyer_id = b.id
               JOIN users j ON o.jastiper_id = j.id
               WHERE o.buyer_id = %s OR o.jastiper_id = %s
               ORDER BY o.created_at DESC""",
            (user_id, user_id)
        )
        orders = cur.fetchall()
        
        result = []
        for o in orders:
            result.append({
                "id": o[0],
                "item_name": o[1],
                "total_amount": float(o[2]),
                "status": o[3],
                "created_at": o[4].isoformat() if o[4] else None,
                "buyer_name": o[5],
                "jastiper_name": o[6]
            })
            
        return result
    finally:
        cur.close()
        conn.close()

@app.put("/api/orders/{order_id}/status")
def update_order_status(order_id: int, status_update: UpdateStatusRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        valid_statuses = ['waiting_payment', 'paid', 'shopping', 'delivered', 'completed']
        if status_update.status not in valid_statuses:
            raise HTTPException(status_code=400, detail="Status tidak valid!")

        cur.execute(
            "UPDATE orders SET status = %s WHERE id = %s",
            (status_update.status, order_id)
        )
        conn.commit()
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Order tidak ditemukan!")
            
        return {"message": f"Status order berhasil diubah menjadi {status_update.status}"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()