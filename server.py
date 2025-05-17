from fastapi import FastAPI, File, UploadFile
import os
import tempfile
import uvicorn

app = FastAPI()

UPLOAD_DIR = "/root/playstore/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    temp_path = os.path.join(tempfile.gettempdir(), file.filename)
    with open(temp_path, "wb") as f:
        f.write(await file.read())
    final_path = os.path.join(UPLOAD_DIR, file.filename)
    os.rename(temp_path, final_path)
    return {"url": f"{WEB_SERVER_URL}/files/{file.filename}"}

@app.get("/files/{filename}")
async def get_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        return {"error": "File not found"}
    return FileResponse(file_path)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
