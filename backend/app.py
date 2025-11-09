from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import json
import zipfile
import tempfile
from datetime import datetime

from websocket_manager import ConnectionManager
from scraper_service import ScraperService
from pipeline_service import PipelineService


manager = ConnectionManager()

scraper_service = None
pipeline_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scraper_service, pipeline_service
    
    scraper_service = ScraperService(manager)
    pipeline_service = PipelineService(manager)
    await manager.send_log("info", "System initialized")
    
    yield
    
    await manager.send_log("info", "System shutting down")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/status")
async def get_status():
    return {
        "timestamp": datetime.now().isoformat(),
        "scraping": {"is_running": False, "status": "idle"},
        "pipeline": {"is_running": False, "status": "idle"}
    }


@app.get("/api/banks")
async def get_banks():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        
        banks = []
        for source in config["scraping"]["sources"]:
            banks.append({
                "id": source["name"],
                "name": source["name"],
                "output_folder": source["output_folder"]
            })
        
        return {"banks": banks}
    except Exception as e:
        return {"error": str(e), "banks": []}


@app.post("/api/start")
async def start_automation():
    try:
        await manager.send_log("info", "")
        await scraper_service.run()
        
        await manager.send_log("info", "Starting Analysis...")
        await pipeline_service.run()
        
        await manager.send_completion()
        
        return {"status": "completed"}
    except Exception as e:
        await manager.send_log("error", f"Automation failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@app.post("/api/scrape/start")
async def start_scraping():
    try:
        await scraper_service.run()
        return {"status": "started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/pipeline/start")
async def start_pipeline():
    try:
        await pipeline_service.run()
        await manager.send_completion()
        return {"status": "started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/results")
async def get_results():
    print("=== API RESULTS CALLED - NEW VERSION ===")  
    metadata_folder = "data/metadata"
    docx_folder = "data/output_docx"
    results = []

    if not os.path.exists(metadata_folder):
        return {"results": []}

    # Loop through each tender in metadata folder
    for tender_name in os.listdir(metadata_folder):
        tender_metadata_path = os.path.join(metadata_folder, tender_name, "tender_metadata.json")
        
        if not os.path.exists(tender_metadata_path):
            continue
        
        # Read the pre-generated metadata
        try:
            with open(tender_metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except:
            continue
        
        # Get description from metadata
        description = metadata.get("summary", "Summary unavailable.")
        
        # Get deadline from metadata
        deadline_info = metadata.get("deadline", {})
        if deadline_info.get("deadline_found", False):
            deadline = deadline_info.get("deadline_date", "Not found")
        else:
            deadline = "Not found"
        
        # Count DOCX files from output_docx folder
        tender_docx_path = os.path.join(docx_folder, tender_name)
        forms_count = 0
        if os.path.exists(tender_docx_path):
            docx_files = [
                f for f in os.listdir(tender_docx_path)
                if f.lower().endswith(".docx")
            ]
            forms_count = len(docx_files)
        
        results.append({
            "tender_name": tender_name,
            "description": description,
            "last_date": deadline,
            "forms_count": forms_count,
            "download_url": f"/api/download/{tender_name}"
        })

    return {"results": results}



@app.get("/api/download/{tender_name:path}")
async def download_tender(tender_name: str):
    try:
        extracted_folder = f"data/extracted_sections/{tender_name}"
        docx_folder = f"data/output_docx/{tender_name}"
        
        if not os.path.exists(extracted_folder):
            return {"error": "Tender not found"}
        
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.exists(extracted_folder):
                for root, dirs, files in os.walk(extracted_folder):
                    for file in files:
                        if file.endswith('.pdf'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, extracted_folder)
                            zipf.write(file_path, arcname)
            
            if os.path.exists(docx_folder):
                for root, dirs, files in os.walk(docx_folder):
                    for file in files:
                        if file.endswith('.docx'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.join('DOCX', os.path.relpath(file_path, docx_folder))
                            zipf.write(file_path, arcname)
        
        safe_name = tender_name.replace("/", "_").replace("\\", "_")[:100]
        
        return FileResponse(
            temp_zip.name,
            media_type="application/zip",
            filename=f"{safe_name}_forms.zip"
        )
    
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)