import sqlite3
import os
from datetime import datetime

class Database:
    def __init__(self):
        # Получаем путь к базе данных из переменной окружения DB_PATH, по умолчанию 'responses.db'
        db_path = os.getenv('DB_PATH', 'responses.db')
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                status TEXT DEFAULT 'pending'
            )
        ''')

        # Проверяем, есть ли столбец username в таблице users, и если нет, добавляем
        self.cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if 'username' not in columns:
            self.cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                name TEXT,
                subscription_duration TEXT,
                favorite_genre TEXT,
                purpose TEXT,
                feedback TEXT,
                confidentiality TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS moderation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                admin_id INTEGER,
                decision TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        self.conn.commit()

    def save_user_response(self, user_id, username, response_data):
        # Вставляем или игнорируем запись в users, обновляем username
        self.cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)
        ''', (user_id, username))

        self.cursor.execute('''
            UPDATE users SET username = ? WHERE user_id = ?
        ''', (username, user_id))

        self.cursor.execute('''
            INSERT INTO responses (
                user_id, username, name, subscription_duration, 
                favorite_genre, purpose, feedback, confidentiality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            username,
            response_data.get('name'),
            response_data.get('subscription_duration'),
            response_data.get('favorite_genre'),
            response_data.get('purpose'),
            response_data.get('feedback'),
            response_data.get('confidentiality')
        ))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_pending_users(self):
        self.cursor.execute('''
            SELECT user_id FROM users WHERE status = 'pending'
        ''')
        return [row[0] for row in self.cursor.fetchall()]

    def get_user_responses(self, user_id):
        self.cursor.execute('''
            SELECT * FROM responses 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT 1
        ''', (user_id,))
        return self.cursor.fetchone()

    def get_user_status(self, user_id):
        self.cursor.execute('''
            SELECT status FROM users WHERE user_id = ?
        ''', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def delete_user_data(self, user_id):
        self.cursor.execute('DELETE FROM responses WHERE user_id = ?', (user_id,))
        self.cursor.execute('DELETE FROM moderation WHERE user_id = ?', (user_id,))
        self.cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        self.conn.commit()

    def update_moderation_status(self, user_id, decision, admin_id):
        self.cursor.execute('''
            UPDATE users 
            SET status = ? 
            WHERE user_id = ?
        ''', (decision, user_id))

        self.cursor.execute('''
            INSERT INTO moderation (user_id, admin_id, decision)
            VALUES (?, ?, ?)
        ''', (user_id, admin_id, decision))

        # Удаляем ответы пользователя из таблицы responses после модерации
        self.cursor.execute('DELETE FROM responses WHERE user_id = ?', (user_id,))

        self.conn.commit()

    def get_approved_users(self, offset=0, limit=10):
        self.cursor.execute('''
            SELECT u.user_id, 
                   u.username as username,
                   (SELECT m.timestamp FROM moderation m WHERE m.user_id = u.user_id AND m.decision = 'approved' ORDER BY m.timestamp DESC LIMIT 1) as timestamp
            FROM users u
            WHERE u.status = 'approved'
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        return self.cursor.fetchall()

    def get_approved_users_count(self):
        self.cursor.execute('''
            SELECT COUNT(*) FROM users WHERE status = 'approved'
        ''')
        return self.cursor.fetchone()[0]

    def get_rejected_users_count(self):
        self.cursor.execute('''
            SELECT COUNT(*) FROM users WHERE status = 'rejected'
        ''')
        return self.cursor.fetchone()[0]

    def has_saved_responses(self, user_id):
        """Check if the user has any saved responses in the responses table."""
        self.cursor.execute('''
            SELECT COUNT(*) FROM responses WHERE user_id = ?
        ''', (user_id,))
        count = self.cursor.fetchone()[0]
        return count > 0

    def close(self):
        self.conn.close()
