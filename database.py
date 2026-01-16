import aiosqlite
import os
from config import DATABASE_PATH


class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH

    async def init_db(self):
        """Инициализация базы данных"""
        # Создаем директорию для БД, если путь содержит директорию
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            # Убеждаемся, что директория доступна для записи
            if not os.access(db_dir, os.W_OK):
                raise PermissionError(f"Нет прав на запись в директорию: {db_dir}")
        
        # Подключаемся к БД и создаем таблицы
        async with aiosqlite.connect(self.db_path, timeout=10.0) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    rubies INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    amount REAL,
                    rubies INTEGER,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    prompt TEXT,
                    cost INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            await db.commit()

    async def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None):
        """Получить или создать пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            user = await cursor.fetchone()
            
            if not user:
                # Новые пользователи получают 4 рубина при регистрации
                await db.execute(
                    "INSERT INTO users (user_id, username, first_name, rubies) VALUES (?, ?, ?, ?)",
                    (user_id, username, first_name, 4)
                )
                await db.commit()
                return {"user_id": user_id, "username": username, "first_name": first_name, "rubies": 4}
            
            return {
                "user_id": user[0],
                "username": user[1],
                "first_name": user[2],
                "rubies": user[3]
            }

    async def get_user_rubies(self, user_id: int) -> int:
        """Получить количество рубинов пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT rubies FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def add_rubies(self, user_id: int, amount: int):
        """Добавить рубины пользователю"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET rubies = rubies + ? WHERE user_id = ?",
                (amount, user_id)
            )
            await db.commit()

    async def deduct_rubies(self, user_id: int, amount: int) -> bool:
        """Списать рубины у пользователя. Возвращает True если успешно"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT rubies FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = await cursor.fetchone()
            current_rubies = result[0] if result else 0
            
            if current_rubies >= amount:
                await db.execute(
                    "UPDATE users SET rubies = rubies - ? WHERE user_id = ?",
                    (amount, user_id)
                )
                await db.commit()
                return True
            return False

    async def create_payment(self, payment_id: str, user_id: int, amount: float, rubies: int):
        """Создать запись о платеже"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO payments (payment_id, user_id, amount, rubies, status) VALUES (?, ?, ?, ?, ?)",
                (payment_id, user_id, amount, rubies, "pending")
            )
            await db.commit()

    async def update_payment_status(self, payment_id: str, status: str):
        """Обновить статус платежа"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE payments SET status = ? WHERE payment_id = ?",
                (status, payment_id)
            )
            await db.commit()

    async def get_payment(self, payment_id: str):
        """Получить информацию о платеже"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM payments WHERE payment_id = ?",
                (payment_id,)
            )
            result = await cursor.fetchone()
            if result:
                return {
                    "payment_id": result[0],
                    "user_id": result[1],
                    "amount": result[2],
                    "rubies": result[3],
                    "status": result[4],
                    "created_at": result[5]
                }
            return None

    async def log_generation(self, user_id: int, prompt: str, cost: int):
        """Записать генерацию в историю"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO generations (user_id, prompt, cost) VALUES (?, ?, ?)",
                (user_id, prompt, cost)
            )
            await db.commit()
