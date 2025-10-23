import asyncio
import os
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import get_expired_transfers, delete_transfer
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


async def cleanup_expired_files():
    """清理过期或已下载的文件"""
    current_time = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')
    print(f"🧹 开始清理过期文件... (东八区时间: {current_time})")

    expired_transfers = await get_expired_transfers()
    cleaned_count = 0

    for transfer in expired_transfers:
        # 删除文件
        if transfer['encrypted_file_path']:
            file_path = Path(transfer['encrypted_file_path'])
            if file_path.exists():
                try:
                    os.remove(file_path)
                    print(f"   ✅ 删除文件: {file_path.name}")
                except Exception as e:
                    print(f"   ❌ 删除失败: {e}")

        # 删除数据库记录
        await delete_transfer(transfer['url_token'])
        cleaned_count += 1

    if cleaned_count > 0:
        print(f"🎉 清理完成，共删除 {cleaned_count} 条记录")
    else:
        print("✅ 无需清理")


def start_cleanup_scheduler():
    """启动定时清理任务(每小时执行一次)"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_expired_files, 'interval', hours=1)
    scheduler.start()
    print("⏰ 定时清理任务已启动(每小时执行)")
    return scheduler