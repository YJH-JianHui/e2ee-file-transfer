import aiosqlite
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from config import DATABASE_PATH, FILE_EXPIRATION_HOURS, URL_TOKEN_LENGTH
from datetime import datetime, timedelta, timezone

# 定义东八区时区
CST = timezone(timedelta(hours=8))

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

        # 日志表
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
    # 使用东八区时间
    now = datetime.now(CST)
    expires_at = now + timedelta(hours=FILE_EXPIRATION_HOURS)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO transfers (url_token, public_key, expires_at, created_at)
            VALUES (?, ?, ?, ?)
        """, (url_token, public_key, expires_at.isoformat(), now.isoformat()))
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


# 更新上传进度
async def update_upload_progress(url_token: str, chunks_uploaded: int, chunks_total: int) -> bool:
    """更新分片上传进度"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            UPDATE transfers
            SET chunks_uploaded = ?,
                chunks_total = ?,
                upload_started_at = COALESCE(upload_started_at, CURRENT_TIMESTAMP)
            WHERE url_token = ?
        """, (chunks_uploaded, chunks_total, url_token))
        await db.commit()
        return cursor.rowcount > 0


# 标记上传完成
async def mark_upload_completed(url_token: str) -> bool:
    """标记上传完成"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            UPDATE transfers
            SET upload_completed_at = CURRENT_TIMESTAMP
            WHERE url_token = ?
        """, (url_token,))
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
    # 获取东八区当前时间的 ISO 格式字符串
    current_time_cst = datetime.now(CST).isoformat()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM transfers
            WHERE expires_at < ?
            OR downloaded = 1
        """, (current_time_cst,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

# ==================== 日志功能 ====================

async def log_action(url_token: str, action: str, details: str = None,
                     ip_address: str = None, user_agent: str = None) -> bool:
    """
    记录操作日志
    :param url_token: 传输 Token
    :param action: 操作类型 (created, uploaded, downloaded, etc.)
    :param details: 详细信息
    :param ip_address: IP 地址
    :param user_agent: 用户代理
    :return: 是否成功
    """
    current_time_cst = datetime.now(CST).isoformat()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO transfer_logs (url_token, action, details, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url_token, action, details, ip_address, user_agent, current_time_cst))
        await db.commit()
        return True


async def get_transfer_logs(url_token: str) -> list:
    """获取特定传输的所有日志"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM transfer_logs
            WHERE url_token = ?
            ORDER BY created_at DESC
        """, (url_token,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ==================== 统计功能 ====================

async def get_statistics() -> Dict:
    """获取系统统计信息"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 总传输数
        async with db.execute("SELECT COUNT(*) FROM transfers") as cursor:
            total_transfers = (await cursor.fetchone())[0]

        # 已完成传输数
        async with db.execute("SELECT COUNT(*) FROM transfers WHERE downloaded = 1") as cursor:
            completed_transfers = (await cursor.fetchone())[0]

        # 待下载传输数
        async with db.execute("""
            SELECT COUNT(*) FROM transfers 
            WHERE encrypted_file_path IS NOT NULL 
            AND downloaded = 0 
            AND expires_at > CURRENT_TIMESTAMP
        """) as cursor:
            pending_transfers = (await cursor.fetchone())[0]

        # 总文件大小
        async with db.execute("SELECT COALESCE(SUM(file_size), 0) FROM transfers") as cursor:
            total_size = (await cursor.fetchone())[0]

        # 今日创建数
        async with db.execute("""
            SELECT COUNT(*) FROM transfers 
            WHERE DATE(created_at) = DATE('now')
        """) as cursor:
            today_created = (await cursor.fetchone())[0]

        # 今日下载数
        async with db.execute("""
            SELECT COUNT(*) FROM transfers 
            WHERE DATE(download_at) = DATE('now')
        """) as cursor:
            today_downloaded = (await cursor.fetchone())[0]

        return {
            "total_transfers": total_transfers,
            "completed_transfers": completed_transfers,
            "pending_transfers": pending_transfers,
            "total_size": total_size,
            "today_created": today_created,
            "today_downloaded": today_downloaded
        }