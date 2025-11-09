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


# WebSocket manager
manager = ConnectionManager()

# Services
scraper_service = None
pipeline_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events"""
    global scraper_service, pipeline_service
    
    # Startup
    scraper_service = ScraperService(manager)
    pipeline_service = PipelineService(manager)
    await manager.send_log("info", "System initialized")
    
    yield
    
    # Shutdown
    await manager.send_log("info", "System shutting down")


app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# WEBSOCKET
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/api/status")
async def get_status():
    """Get current status"""
    return {
        "timestamp": datetime.now().isoformat(),
        "scraping": {
            "is_running": scraper_service.executor._threads if scraper_service else False,
            "status": "idle"
        },
        "pipeline": {
            "is_running": pipeline_service.executor._threads if pipeline_service else False,
            "status": "idle"
        }
    }


@app.get("/api/banks")
async def get_banks():
    """Get list of available banks from config"""
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
    """Start complete automation (scraping + pipeline)"""
    try:
        # Start scraping
        await manager.send_log("info", "Starting automation...")
        await scraper_service.run()
        
        # After scraping completes, start pipeline
        await manager.send_log("info", "Scraping complete. Starting pipeline...")
        await pipeline_service.run()
        
        # Send completion event
        await manager.send_completion()
        
        return {"status": "completed"}
    except Exception as e:
        await manager.send_log("error", f"Automation failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@app.post("/api/scrape/start")
async def start_scraping():
    """Start scraping only"""
    try:
        await scraper_service.run()
        return {"status": "started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/pipeline/start")
async def start_pipeline():
    """Start pipeline only"""
    try:
        await pipeline_service.run()
        await manager.send_completion()
        return {"status": "started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/results")
async def get_results():
    """Get processed tender results"""
    try:
        metadata_folder = "data/metadata"
        
        if not os.path.exists(metadata_folder):
            return {"results": []}
        
        results = []
        
        for filename in os.listdir(metadata_folder):
            if filename.endswith("_metadata.json"):
                filepath = os.path.join(metadata_folder, filename)
                
                with open(filepath, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                tender_id = filename.replace("_metadata.json", "")
                
                results.append({
                    "tender_id": tender_id,
                    "tender_name": metadata.get("pdf_name", "Unknown"),
                    "description": metadata.get("forms", [{}])[0].get("form_title", "No description") if metadata.get("forms") else "No forms found",
                    "last_date": metadata.get("deadline_info", {}).get("deadline_date", "Not specified"),
                    "forms_count": metadata.get("total_forms", 0),
                    "download_url": f"/api/download/{tender_id}"
                })
        
        return {"results": results}
    
    except Exception as e:
        return {"error": str(e), "results": []}


@app.get("/api/download/{tender_id}")
async def download_tender(tender_id: str):
    """Download all forms for a tender as ZIP"""
    try:
        # Paths
        extracted_folder = f"data/extracted_sections/{tender_id}"
        docx_folder = f"data/output_docx/{tender_id}"
        
        if not os.path.exists(extracted_folder):
            return {"error": "Tender not found"}
        
        # Create temporary ZIP
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add PDFs
            if os.path.exists(extracted_folder):
                for root, dirs, files in os.walk(extracted_folder):
                    for file in files:
                        if file.endswith('.pdf'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.join('PDFs', file)
                            zipf.write(file_path, arcname)
            
            # Add DOCX files
            if os.path.exists(docx_folder):
                for root, dirs, files in os.walk(docx_folder):
                    for file in files:
                        if file.endswith('.docx'):
                            file_path = os.path.join(root, file)
                            arcname = os.path.join('DOCX', file)
                            zipf.write(file_path, arcname)
        
        return FileResponse(
            temp_zip.name,
            media_type="application/zip",
            filename=f"{tender_id}_forms.zip"
        )
    
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)