import uvicorn
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 ĐANG KHỞI ĐỘNG PERSONAL AI KNOWLEDGE PLATFORM...")
    print("📍 URL Giao diện Web: http://localhost:8000")
    print("📍 URL API Swagger Docs: http://localhost:8000/docs")
    print("="*60 + "\n")
    
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
