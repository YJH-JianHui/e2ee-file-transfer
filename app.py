from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

import config
import database
from cleanup import start_cleanup_scheduler


# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    print("🚀 正在启动 E2EE File Transfer 系统...")

    # 初始化目录
    config.init_directories()

    # 初始化数据库
    await database.init_database()

    # 启动定时清理任务
    scheduler = start_cleanup_scheduler()

    print("✅ 系统启动完成!")
    print(f"🌐 访问地址: {config.BASE_URL}")

    yield

    # 关闭时执行
    scheduler.shutdown()
    print("👋 系统已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="E2EE File Transfer",
    description="端到端加密文件传输系统",
    version="1.0.0",
    lifespan=lifespan
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 配置模板引擎
templates = Jinja2Templates(directory="templates")


# ==================== 路由定义 ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 - 生成接收链接"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "base_url": config.BASE_URL
    })


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "version": "1.0.0"
    }


# ==================== API 接口 ====================

from fastapi import HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import os
import shutil
from datetime import datetime


class CreateTransferRequest(BaseModel):
    public_key: str


@app.post("/api/create-transfer")
async def create_transfer(request: CreateTransferRequest):
    """
    创建新的传输记录
    接收公钥，生成 URL Token
    """
    try:
        # 验证公钥格式
        if not request.public_key.startswith("-----BEGIN PUBLIC KEY-----"):
            raise HTTPException(status_code=400, detail="无效的公钥格式")

        # 创建传输记录
        result = await database.create_transfer(request.public_key)

        return {
            "success": True,
            "url_token": result["url_token"],
            "expires_at": result["expires_at"],
            "receive_url": f"{config.BASE_URL}/receive/{result['url_token']}"
        }

    except Exception as e:
        print(f"❌ 创建传输失败: {e}")
        raise HTTPException(status_code=500, detail="服务器错误")


@app.get("/api/get-public-key/{url_token}")
async def get_public_key(url_token: str):
    """
    获取指定传输的公钥
    """
    transfer = await database.get_transfer_by_token(url_token)
    if not transfer:
        raise HTTPException(status_code=404, detail="接收链接不存在或已过期")

    # 检查是否过期
    expires_at = datetime.fromisoformat(transfer['expires_at'])
    if datetime.now() > expires_at:
        raise HTTPException(status_code=410, detail="链接已过期")

    # 检查是否已有文件
    if transfer['encrypted_file_path']:
        raise HTTPException(status_code=409, detail="该链接已接收过文件")

    return {
        "public_key": transfer['public_key'],
        "expires_at": transfer['expires_at']
    }


@app.post("/api/upload/{url_token}")
async def upload_file(
        url_token: str,
        file: UploadFile = File(...),
        encrypted_aes_key: str = Form(...),
        original_filename: str = Form(...)
):
    """
    上传加密文件
    """
    try:
        # 验证传输记录
        transfer = await database.get_transfer_by_token(url_token)
        if not transfer:
            raise HTTPException(status_code=404, detail="接收链接不存在")

        # 检查是否已上传
        if transfer['encrypted_file_path']:
            raise HTTPException(status_code=409, detail="该链接已接收过文件")

        # 检查文件大小
        file_size = 0
        file_path = config.UPLOAD_DIR / f"{url_token}_{file.filename}"

        # 保存文件
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                if file_size > config.MAX_FILE_SIZE:
                    os.remove(file_path)
                    raise HTTPException(status_code=413, detail="文件超过大小限制")
                buffer.write(chunk)

        # 更新数据库
        success = await database.update_transfer_file(
            url_token,
            str(file_path),
            encrypted_aes_key,
            original_filename,
            file_size
        )

        if not success:
            os.remove(file_path)
            raise HTTPException(status_code=500, detail="数据库更新失败")

        print(f"✅ 文件上传成功: {original_filename} ({file_size} bytes)")

        return {
            "success": True,
            "message": "文件上传成功",
            "file_size": file_size
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.get("/receive/{url_token}", response_class=HTMLResponse)
async def receive_page(request: Request, url_token: str):
    """
    接收页面 - 根据状态显示上传或下载界面
    """
    transfer = await database.get_transfer_by_token(url_token)
    if not transfer:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_title": "链接不存在",
            "error_message": "该接收链接不存在或已过期"
        })

    # 检查是否已有文件
    if transfer['encrypted_file_path']:
        # 已有文件，显示下载页面
        return templates.TemplateResponse("download.html", {
            "request": request,
            "url_token": url_token,
            "base_url": config.BASE_URL
        })
    else:
        # 无文件，显示上传页面
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "url_token": url_token,
            "base_url": config.BASE_URL
        })


@app.get("/api/get-file-info/{url_token}")
async def get_file_info(url_token: str):
    """
    获取文件信息（用于下载页面显示）
    """
    transfer = await database.get_transfer_by_token(url_token)
    if not transfer:
        raise HTTPException(status_code=404, detail="传输记录不存在")

    if not transfer['encrypted_file_path']:
        raise HTTPException(status_code=404, detail="文件尚未上传")

    return {
        "original_filename": transfer['original_filename'],
        "file_size": transfer['file_size'],
        "created_at": transfer['created_at']
    }


@app.get("/api/download/{url_token}")
async def download_encrypted_file(url_token: str):
    """
    下载加密文件
    """
    from fastapi.responses import FileResponse

    transfer = await database.get_transfer_by_token(url_token)
    if not transfer or not transfer['encrypted_file_path']:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = transfer['encrypted_file_path']
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件已被删除")

    return FileResponse(
        path=file_path,
        media_type='application/octet-stream',
        filename=os.path.basename(file_path)
    )


@app.get("/api/get-encrypted-key/{url_token}")
async def get_encrypted_key(url_token: str):
    """
    获取加密的 AES 密钥
    """
    transfer = await database.get_transfer_by_token(url_token)
    if not transfer or not transfer['encrypted_aes_key']:
        raise HTTPException(status_code=404, detail="密钥不存在")

    return {
        "encrypted_aes_key": transfer['encrypted_aes_key']
    }


@app.post("/api/confirm-download/{url_token}")
async def confirm_download(url_token: str):
    """
    确认下载完成，删除服务器文件
    """
    try:
        transfer = await database.get_transfer_by_token(url_token)
        if not transfer:
            raise HTTPException(status_code=404, detail="传输记录不存在")

        # 删除文件
        if transfer['encrypted_file_path'] and os.path.exists(transfer['encrypted_file_path']):
            os.remove(transfer['encrypted_file_path'])
            print(f"🗑️ 已删除文件: {transfer['encrypted_file_path']}")

        # 标记为已下载
        await database.mark_as_downloaded(url_token)

        # 可选：直接删除数据库记录
        # await database.delete_transfer(url_token)

        return {
            "success": True,
            "message": "文件已删除"
        }

    except Exception as e:
        print(f"❌ 确认下载失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 启动命令 ====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # 开发模式热重载
    )