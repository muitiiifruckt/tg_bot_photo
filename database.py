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
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER,
                    to_user_id INTEGER,
                    amount INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_user_id) REFERENCES users (user_id),
                    FOREIGN KEY (to_user_id) REFERENCES users (user_id)
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

    async def get_user_by_username(self, username: str):
        """Получить пользователя по username"""
        async with aiosqlite.connect(self.db_path) as db:
            # Убираем @ если есть
            username = username.lstrip('@')
            cursor = await db.execute(
                "SELECT user_id, username, first_name, rubies FROM users WHERE username = ? COLLATE NOCASE",
                (username,)
            )
            result = await cursor.fetchone()
            if result:
                return {
                    "user_id": result[0],
                    "username": result[1],
                    "first_name": result[2],
                    "rubies": result[3]
                }
            return None

    async def transfer_rubies(self, from_user_id: int, to_user_id: int, amount: int) -> bool:
        """Перевести рубины от одного пользователя другому"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем баланс отправителя
            cursor = await db.execute(
                "SELECT rubies FROM users WHERE user_id = ?",
                (from_user_id,)
            )
            result = await cursor.fetchone()
            from_balance = result[0] if result else 0
            
            if from_balance < amount:
                return False
            
            # Списываем у отправителя
            await db.execute(
                "UPDATE users SET rubies = rubies - ? WHERE user_id = ?",
                (amount, from_user_id)
            )
            
            # Начисляем получателю
            await db.execute(
                "UPDATE users SET rubies = rubies + ? WHERE user_id = ?",
                (amount, to_user_id)
            )
            
            # Логируем перевод
            await db.execute(
                "INSERT INTO transfers (from_user_id, to_user_id, amount) VALUES (?, ?, ?)",
                (from_user_id, to_user_id, amount)
            )
            
            await db.commit()
            return True

    async def get_transfer_history(self, user_id: int, limit: int = 10):
        """Получить историю переводов пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT t.id, t.from_user_id, t.to_user_id, t.amount, t.created_at,
                       u1.username as from_username, u1.first_name as from_first_name,
                       u2.username as to_username, u2.first_name as to_first_name
                FROM transfers t
                LEFT JOIN users u1 ON t.from_user_id = u1.user_id
                LEFT JOIN users u2 ON t.to_user_id = u2.user_id
                WHERE t.from_user_id = ? OR t.to_user_id = ?
                ORDER BY t.created_at DESC
                LIMIT ?
            """, (user_id, user_id, limit))
            
            results = await cursor.fetchall()
            transfers = []
            for row in results:
                transfers.append({
                    "id": row[0],
                    "from_user_id": row[1],
                    "to_user_id": row[2],
                    "amount": row[3],
                    "created_at": row[4],
                    "from_username": row[5],
                    "from_first_name": row[6],
                    "to_username": row[7],
                    "to_first_name": row[8]
                })
            return transfers
