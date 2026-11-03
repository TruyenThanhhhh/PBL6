import logging
import uvicorn

# Cấu hình logging toàn cục cho ứng dụng
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 ĐANG KHỞI ĐỘNG PERSONAL AI KNOWLEDGE PLATFORM...")
    print("📍 URL Giao diện Web: http://localhost:8000")
    print("📍 URL API Swagger Docs: http://localhost:8000/docs")
    print("="*60 + "\n")

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
