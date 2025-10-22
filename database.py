import aiosqlite
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from config import DATABASE_PATH, FILE_EXPIRATION_HOURS, URL_TOKEN_LENGTH


# 数据库初始化
async def init_database():
    """创建数据库表结构"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 传输表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_token TEXT UNIQUE NOT NULL,
                public_key TEXT NOT NULL,
                encrypted_file_path TEXT,
                encrypted_aes_key TEXT,
                original_filename TEXT,
                file_size INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                downloaded BOOLEAN DEFAULT 0,
                download_at TIMESTAMP,
                upload_started_at TIMESTAMP,
                upload_completed_at TIMESTAMP,
                chunks_total INTEGER DEFAULT 0,
                chunks_uploaded INTEGER DEFAULT 0
            )
        """)

        # 日志表（新增）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfer_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_token TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()
        print("✅ 数据库表初始化完成")


# 生成唯一的 URL Token
def generate_url_token() -> str:
    """生成加密安全的随机 Token"""
    return secrets.token_urlsafe(URL_TOKEN_LENGTH)


# 创建新的传输记录
async def create_transfer(public_key: str) -> Dict:
    """
    创建新传输记录
    :param public_key: PEM 格式的公钥
    :return: 包含 url_token 的字典
    """
    url_token = generate_url_token()
    expires_at = datetime.now() + timedelta(hours=FILE_EXPIRATION_HOURS)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO transfers (url_token, public_key, expires_at)
            VALUES (?, ?, ?)
        """, (url_token, public_key, expires_at))
        await db.commit()

    return {
        "url_token": url_token,
        "expires_at": expires_at.isoformat()
    }


# 根据 Token 获取传输记录
async def get_transfer_by_token(url_token: str) -> Optional[Dict]:
    """
    通过 URL Token 获取传输信息
    :param url_token: 接收码
    :return: 传输记录字典或 None
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM transfers WHERE url_token = ?
        """, (url_token,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
    return None


# 更新文件上传信息
async def update_transfer_file(
        url_token: str,
        encrypted_file_path: str,
        encrypted_aes_key: str,
        original_filename: str,
        file_size: int
) -> bool:
    """
    更新传输记录的文件信息
    :return: 是否成功
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            UPDATE transfers
            SET encrypted_file_path = ?,
                encrypted_aes_key = ?,
                original_filename = ?,
                file_size = ?
            WHERE url_token = ?
        """, (encrypted_file_path, encrypted_aes_key, original_filename, file_size, url_token))
        await db.commit()
        return cursor.rowcount > 0


# 标记文件已下载
async def mark_as_downloaded(url_token: str) -> bool:
    """
    标记文件已下载
    :return: 是否成功
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            UPDATE transfers
            SET downloaded = 1,
                download_at = CURRENT_TIMESTAMP
            WHERE url_token = ?
        """, (url_token,))
        await db.commit()
        return cursor.rowcount > 0


# 删除传输记录
async def delete_transfer(url_token: str) -> bool:
    """
    删除传输记录
    :return: 是否成功
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM transfers WHERE url_token = ?
        """, (url_token,))
        await db.commit()
        return cursor.rowcount > 0


# 获取过期的传输记录
async def get_expired_transfers() -> list:
    """
    获取所有过期的传输记录
    :return: 过期记录列表
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM transfers
            WHERE expires_at < CURRENT_TIMESTAMP
            OR downloaded = 1
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]