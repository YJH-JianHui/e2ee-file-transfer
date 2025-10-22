import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据库配置
DATABASE_DIR = BASE_DIR / "data"
DATABASE_PATH = DATABASE_DIR / "database.db"

# 文件存储配置
UPLOAD_DIR = BASE_DIR / "uploads"
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB (优化后支持大文件)

# 分块上传配置
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB per chunk (用于分块加密和上传)
UPLOAD_BUFFER_SIZE = 1024 * 1024  # 1MB (读取缓冲区)

# 文件有效期(小时)
FILE_EXPIRATION_HOURS = 24

# URL 配置
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
URL_TOKEN_LENGTH = 16  # 接收码长度

# 安全配置
ALLOWED_EXTENSIONS = {
    # 文档类
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md',
    # 图片类
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp',
    # 压缩包
    'zip', 'rar', '7z', 'tar', 'gz',
    # 视频音频
    'mp4', 'avi', 'mkv', 'mov', 'mp3', 'wav', 'flac',
    # 其他
    'json', 'xml', 'csv', 'sql'
}

# 创建必要的目录
def init_directories():
    """初始化项目所需目录"""
    DATABASE_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    (UPLOAD_DIR / "chunks").mkdir(exist_ok=True)  # 分片临时目录
    print(f"✅ 目录初始化完成:")
    print(f"   - 数据库目录: {DATABASE_DIR}")
    print(f"   - 上传目录: {UPLOAD_DIR}")
    print(f"   - 分片目录: {UPLOAD_DIR / 'chunks'}")