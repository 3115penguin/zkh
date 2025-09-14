from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import logging
import re
import sqlite3
import os
import requests
import json
import uuid
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import Dict

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка .env
load_dotenv()
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v2/chat/completions"
OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("API запущен успешно!")
    yield
    logger.info("API остановлен")

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class Complaint(BaseModel):
    text: str

def connect_db():
    return sqlite3.connect('complaints.db', check_same_thread=False)

def init_db():
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                address TEXT,
                category VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_processed BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("База данных SQLite инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

def get_gigachat_token() -> str:
    if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
        logger.error("Отсутствуют GIGACHAT_CLIENT_ID или GIGACHAT_CLIENT_SECRET в .env")
        raise ValueError("GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET должны быть указаны")

    payload = {
        "scope": "GIGACHAT_API",
        "grant_type": "client_credentials",
        "client_id": GIGACHAT_CLIENT_ID,
        "client_secret": GIGACHAT_CLIENT_SECRET
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "RqUID": str(uuid.uuid4())
    }
    try:
        logger.info(f"Отправка запроса на OAuth: URL={OAUTH_URL}, payload={payload}, headers={headers}")
        response = requests.post(OAUTH_URL, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            logger.error(f"Токен не получен: {token_data}")
            raise ValueError("Токен не возвращён в ответе")
        logger.info("Токен GigaChat успешно получен")
        return access_token
    except Exception as e:
        logger.error(f"Ошибка получения токена GigaChat: {str(e)}, ответ сервера: {response.text if 'response' in locals() else 'нет ответа'}")
        raise

def classify_complaint(text: str) -> Dict[str, str]:
    text_lower = text.lower()
    if any(word in text_lower for word in ["вода", "водопровод", "труба", "протечка"]):
        category = "водоснабжение"
    elif any(word in text_lower for word in ["свет", "электричество", "розетка", "провод"]):
        category = "электричество"
    elif any(word in text_lower for word in ["отопление", "батарея", "тепло", "радиатор"]):
        category = "отопление"
    else:
        category = "другое"
    address_match = re.search(r'Адрес[^:\n]*:\s*([^\n]+)', text, re.IGNORECASE)
    address = address_match.group(1).strip() if address_match else "не указан"
    return {"category": category, "address": address}

def classify_with_gigachat_api(text: str) -> Dict[str, str]:
    try:
        access_token = get_gigachat_token()
        prompt = (
            f"Классифицируй жалобу по категориям (водоснабжение, электричество, отопление, другое) "
            f"и извлеки адрес. Верни ответ в формате JSON: "
            f'{{"category": "<категория>", "address": "<адрес>"}}\n'
            f"Текст жалобы: {text}"
        )
        logger.info(f"Отправка запроса в GigaChat API: URL={GIGACHAT_API_URL}, prompt={prompt}")
        response = requests.post(
            GIGACHAT_API_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json={
                "model": "GigaChat-Pro",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 200
            },
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        logger.info(f"Ответ GigaChat: {content}")
        try:
            parsed_result = json.loads(content)
            category = parsed_result.get("category", "другое")
            address = parsed_result.get("address", "не указан")
            valid_categories = ["водоснабжение", "электричество", "отопление", "другое"]
            if category not in valid_categories:
                category = "другое"
            return {"category": category, "address": address}
        except json.JSONDecodeError:
            logger.error(f"Ошибка парсинга JSON из GigaChat: {content}")
            return classify_complaint(text)
    except Exception as e:
        logger.error(f"Не удалось получить ответ от GigaChat API: {str(e)}, ответ сервера: {response.text if 'response' in locals() else 'нет ответа'}")
        return classify_complaint(text)

@app.get("/")
async def root():
    return {"message": "API работает!", "status": "ok"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/complaint")
async def process_complaint(complaint: Complaint):
    try:
        result = classify_with_gigachat_api(complaint.text)
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO complaints (text, address, category) VALUES (?, ?, ?)",
            (complaint.text, result["address"], result["category"])
        )
        complaint_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Жалоба #{complaint_id} сохранена в SQLite")
        return {
            "status": "success",
            "id": complaint_id,
            "category": result["category"],
            "address": result["address"]
        }
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка обработки жалобы")

@app.get("/complaints")
async def get_complaints():
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, text, address, category, created_at FROM complaints WHERE is_processed = 0 ORDER BY created_at DESC")
        rows = cursor.fetchall()
        complaints = {
            "водоснабжение": [],
            "электричество": [],
            "отопление": [],
            "другое": []
        }
        for row in rows:
            complaints[row[3]].append({
                "id": row[0],
                "text": row[1],
                "address": row[2],
                "category": row[3],
                "created_at": str(row[4])
            })
        cursor.close()
        conn.close()
        return complaints
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка получения жалоб")

@app.post("/complaint/{id}/processed")
async def mark_processed(id: int):
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE complaints SET is_processed = 1 WHERE id = ?", (id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Жалоба не найдена")
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Жалоба #{id} помечена как обработанная")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка обработки жалобы")

if __name__ == "__main__":
    import uvicorn
    logger.info("Запуск API сервера на SQLite...")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)