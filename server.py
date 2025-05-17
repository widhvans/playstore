from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
import os
import tempfile

app = FastAPI()

UPLOAD_DIR = "/root/playstore/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload/{filename}")
async def upload_file(filename: str, file: UploadFile = File(...)):
    if not filename.endswith('.apk'):
        raise HTTPException(status_code=400, detail="Only APK files allowed")
    temp_path = os.path.join(tempfile.gettempdir(), filename)
    with open(temp_path, "wb") as f:
        f.write(await file.read())
    final_path = os.path.join(UPLOAD_DIR, filename)
    os.rename(temp_path, final_path)
    return {"url": f"{WEB_SERVER_URL}/files/{filename}"}

@app.get("/files/{filename}")
async def get_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
