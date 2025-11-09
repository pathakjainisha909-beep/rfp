import os
import json
import time
import shutil
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
import fitz
from PyPDF2 import PdfReader, PdfWriter
from pdf2docx import parse
import google.generativeai as genai
from sentence_transformers import SentenceTransformer, util
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Optional


class FormIdentification(BaseModel):
    form_title: str = Field(description="Title of the form")
    start_page: int = Field(description="Starting page number (1-indexed)")
    end_page: int = Field(description="Ending page number (1-indexed)")
    confidence: str = Field(description="Confidence level: high, medium, or low")


class AllFormsDetection(BaseModel):
    total_forms_found: int = Field(description="Total number of forms detected")
    forms: List[FormIdentification] = Field(description="List of all forms found")
    explanation: str = Field(description="Brief explanation of detection process")


class TenderDeadline(BaseModel):
    deadline_found: bool = Field(description="Whether deadline was found")
    deadline_date: Optional[str] = Field(description="Last date of submission (any format)")
    bid_opening_date: Optional[str] = Field(description="Bid opening date if found")
    deadline_text: Optional[str] = Field(description="Exact text mentioning deadline")
    explanation: str = Field(description="Context about deadline")


COMPANY_PROFILE = """

You are analyzing tenders for a specialized technology company with the following capabilities:

CORE EXPERTISE:
- Data Analytics & Big Data Solutions
- AI/ML Systems & Agentic AI
- Fintech & Banking Technology
- Payment Systems (UPI, CBDC, BBPS, IMPS, Merchant Acquiring)
- Fraud Risk Monitoring & Early Warning Systems
- Online Dispute Resolution (ODR) platforms
- Digital Banking Infrastructure
- Hardware Security Modules (HSM) & Cryptographic Solutions
- Key Management Systems (KMS)
- Omnichannel Banking Solutions
- Loan Management Systems
- Load Balancers & Network Infrastructure
- Cybersecurity Solutions & Security Auditing
- IT Risk Assessment & Vendor Risk Management
- Compliance & Due Diligence Auditing (including CERT-In standards)
- Information Security Management
- Penetration Testing & Vulnerability Assessment

RELEVANT TENDERS (accept these):
- Software development for banking/fintech
- IT infrastructure & security solutions
- Cybersecurity auditing & risk assessment services
- CERT-In certified security audits
- Vendor risk management & due diligence
- Payment gateway/processing systems
- Digital transformation projects
- Cloud infrastructure & data centers
- AI/ML implementation projects
- Financial technology platforms

IRRELEVANT TENDERS (reject these):
- Civil construction, interior furnishing, furniture
- Electrical works, HVAC, plumbing
- Building materials, maintenance
- Non-technology services
- Physical infrastructure without IT component
"""


class PipelineService:
    
    def __init__(self, websocket_manager):
        self.manager = websocket_manager
        self.config = self._load_config()
        self.should_stop = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.loop = None
        
        self._setup_directories()
        self._configure_gemini()
        self._load_semantic_model()
        self._load_cache()
        
    def _load_config(self):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _setup_directories(self):
        self.proc_config = self.config["processing"]
        self.output_folders = self.proc_config["output_folders"]
        
        for folder in self.output_folders.values():
            os.makedirs(folder, exist_ok=True)
    
    def _configure_gemini(self):
        load_dotenv()
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_gemini = genai.GenerativeModel("gemini-2.5-flash")
    
    def _load_semantic_model(self):
        self.filter_settings = self.proc_config["filter_settings"]
        print("[Pipeline] Loading semantic model...")
        self.semantic_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        
        company_capabilities = [
            "data analytics and artificial intelligence",
            "machine learning and AI systems",
            "fintech and digital payments",
            "banking technology and core banking",
            "fraud detection and risk monitoring",
            "payment gateway and UPI systems",
            "blockchain and digital currency",
            "cybersecurity and encryption",
            "loan management systems",
            "merchant acquiring platforms"
        ]
        self.company_embedding = self.semantic_model.encode(company_capabilities, convert_to_tensor=True)
    
    def _load_cache(self):
        cache_file = self.filter_settings["cache_file"]
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                self.cache = json.load(f)
        else:
            self.cache = {}
    
    def _save_cache(self):
        cache_file = self.filter_settings["cache_file"]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, indent=2)
    
    def _send_log_sync(self, level, message, data=None):
        prefix = f"[{level.upper()}]"
        if data:
            print(f"{prefix} {message} | {data}")
        else:
            print(f"{prefix} {message}")

        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.manager.send_log(level, message),
                    self.loop
                )
            except:
                pass
    
    def _send_progress_sync(self, stage, current, total, message):
        print(f"[PROGRESS] {stage}: {current}/{total} - {message}")
        
        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.manager.send_progress(stage, current, total, message),
                    self.loop
                )
            except:
                pass
    
    def _send_pdf_status_sync(self, pdf_name, status, reason, details=None):
        print(f"[PDF] {pdf_name} -> {status.upper()}: {reason}")
        if details:
            print(f"      Details: {details}")
        
        if self.loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.manager.send_pdf_status(pdf_name, status, reason, details),
                    self.loop
                )
            except:
                pass
    
    async def stop(self):
        self.should_stop = True
        await self.manager.send_log("warning", "Stop requested")
    
    async def run(self):
        self.should_stop = False
        self.loop = asyncio.get_event_loop()
        
        await self.manager.send_log("info", "TENDER PROCESSING PIPELINE STARTED")
        
        start_time = time.time()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._run_pipeline_sync)
        
        elapsed = time.time() - start_time
        
        await self.manager.send_log("success", f"PIPELINE COMPLETED IN {elapsed:.2f}s")
    
    def _run_pipeline_sync(self):
        start_time = time.time()
        
        self._send_log_sync("info", "STAGE 1: FILTERING TENDERS", {})
        filtered = self._filter_pdfs_sync()
        
        if self.should_stop:
            self._send_log_sync("warning", "Pipeline stopped by user after filtering", {})
            return
        
        if filtered == 0:
            self._send_log_sync("warning", "No relevant tenders found. Pipeline terminated.", {})
            return
        
        self._send_log_sync("info", "STAGE 2: EXTRACTING FORMS FROM FILTERED TENDERS", {})
        extracted = self._extract_all_forms_sync()
        
        if self.should_stop:
            self._send_log_sync("warning", "Pipeline stopped by user after extraction", {})
            return
        
        if extracted == 0:
            self._send_log_sync("warning", "No forms extracted. Skipping DOCX conversion.", {})
            return
        
        self._send_log_sync("info", "STAGE 3: CONVERTING TO DOCX", {})
        converted = self._convert_to_docx_sync()
        
        elapsed = time.time() - start_time
        
        self._send_log_sync("success", "PIPELINE SUMMARY", {})
        self._send_log_sync("success", f"Filtered Tenders: {filtered}", {})
        self._send_log_sync("success", f"Extracted Forms: {extracted}", {})
        self._send_log_sync("success", f"Converted DOCX: {converted}", {})
        self._send_log_sync("success", f"Total Time: {elapsed:.2f}s", {})
    
    def _group_pdfs_by_tender(self, input_folders):
        tenders = []
        
        for folder in input_folders:
            if not os.path.exists(folder):
                continue
            
            for tender_folder in os.listdir(folder):
                tender_path = os.path.join(folder, tender_folder)
                
                if not os.path.isdir(tender_path):
                    continue
                
                pdf_files = [
                    os.path.join(tender_path, f) 
                    for f in os.listdir(tender_path) 
                    if f.lower().endswith('.pdf')
                ]
                
                if pdf_files:
                    tenders.append((tender_folder, pdf_files))
        
        return tenders
    
    def _filter_pdfs_sync(self):
        input_folders = self.proc_config["input_folders"]
        output_folder = self.output_folders["filtered"]

        tenders = self._group_pdfs_by_tender(input_folders)
        self._send_log_sync("info", f"Found {len(tenders)} tenders to analyze")

        filtered_tender_count = 0

        for tender_folder, pdf_list in tenders:
            self._send_log_sync("info", f"Analyzing Tender: {tender_folder}")

            tender_output_dir = os.path.join(output_folder, tender_folder)
            os.makedirs(tender_output_dir, exist_ok=True)

            tender_has_relevant = False
            last_call_time = 0

            for i, pdf_path in enumerate(pdf_list, 1):
                if self.should_stop:
                    break

                pdf_name = os.path.basename(pdf_path)

                self._send_progress_sync("filtering", i, len(pdf_list), f"{tender_folder}: {pdf_name}")
                self._send_log_sync("info", f"[{i}/{len(pdf_list)}] Analyzing: {pdf_name}")

                if pdf_name in self.cache:
                    result = self.cache[pdf_name]
                    if result.get("passes_filter"):
                        shutil.copy2(pdf_path, os.path.join(tender_output_dir, pdf_name))
                        tender_has_relevant = True
                        self._send_pdf_status_sync(pdf_name, "filtered", "CACHED PASS", {})
                    else:
                        self._send_pdf_status_sync(pdf_name, "skipped", "CACHED SKIP", {})
                    continue

                text, text_error = self._extract_pdf_text(pdf_path)
                if text_error:
                    self.cache[pdf_name] = {"passes_filter": False, "reason": text_error}
                    self._save_cache()
                    self._send_pdf_status_sync(pdf_name, "skipped", text_error, {})
                    continue

                semantic_score = self._calculate_semantic_relevance(text)
                
                last_call_time = self._rate_limit_control(last_call_time)
                is_relevant, reasoning = self._ask_gemini_relevance(text)

                if is_relevant and semantic_score >= 0.3:
                    self.cache[pdf_name] = {
                        "passes_filter": True,
                        "semantic_score": semantic_score,
                        "reasoning": reasoning,
                        "method": "Gemini + Semantic"
                    }
                    self._save_cache()
                    shutil.copy2(pdf_path, os.path.join(tender_output_dir, pdf_name))
                    tender_has_relevant = True
                    self._send_pdf_status_sync(pdf_name, "filtered", f"Relevant (score: {semantic_score:.2f})", {"reasoning": reasoning})
                else:
                    self.cache[pdf_name] = {
                        "passes_filter": False,
                        "reason": reasoning or "Not relevant to company capabilities",
                        "semantic_score": semantic_score
                    }
                    self._save_cache()
                    self._send_pdf_status_sync(pdf_name, "skipped", reasoning[:120] if reasoning else "Not relevant", {})

            if not tender_has_relevant:
                shutil.rmtree(tender_output_dir, ignore_errors=True)
                self._send_log_sync("info", f"Tender Rejected: {tender_folder}")
            else:
                filtered_tender_count += 1
                self._send_log_sync("info", f"Tender Accepted: {tender_folder}")

        self._send_log_sync("success", f"Filtering complete: {filtered_tender_count}/{len(tenders)} tenders passed")
        return filtered_tender_count
    
    def _extract_pdf_text(self, pdf_path):
        max_pages = self.filter_settings["max_pages_to_scan"]
        text = ""
        
        try:
            with fitz.open(pdf_path) as doc:
                for i, page in enumerate(doc):
                    if i >= max_pages:
                        break
                    text += page.get_text("text") + "\n"
        except Exception as e:
            return "", f"error reading PDF: {e}"
        
        if not text.strip():
            return "", "empty text"
        
        return text.strip(), None
    
    def _calculate_semantic_relevance(self, text):
        text_sample = text[:3000]
        text_embedding = self.semantic_model.encode(text_sample, convert_to_tensor=True)
        
        similarities = util.cos_sim(text_embedding, self.company_embedding)
        max_similarity = float(similarities.max())
        
        return max_similarity
    
    def _ask_gemini_relevance(self, text):
        prompt = f"""{COMPANY_PROFILE}

TENDER DOCUMENT TEXT:
{text[:6000]}

TASK:
Analyze if this tender is relevant for the company based on the profile above.

Return ONLY a JSON object:
{{
    "is_relevant": true/false,
    "reasoning": "Brief explanation why this is relevant or not relevant",
    "confidence": "high/medium/low"
}}
"""
        
        try:
            response = self.model_gemini.generate_content(prompt)
            text_response = response.text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text_response)
            return result.get("is_relevant", False), result.get("reasoning", "")
        except Exception as e:
            print(f"[ERROR] Gemini error: {e}")
            return False, f"Gemini error: {e}"
    
    def _rate_limit_control(self, last_call_time, min_interval=6.0):
        now = time.time()
        elapsed = now - last_call_time
        if elapsed < min_interval:
            wait_time = min_interval - elapsed
            print(f"[INFO] Rate limiting: waiting {wait_time:.1f}s before next Gemini call...")
            time.sleep(wait_time)
        return time.time()
    
    def _extract_all_forms_sync(self):
        filtered_folder = self.output_folders["filtered"]
        extracted_folder = self.output_folders["extracted"]
        metadata_folder = self.output_folders["metadata"]
        
        tender_folders = [d for d in os.listdir(filtered_folder) 
                         if os.path.isdir(os.path.join(filtered_folder, d))]
        
        if not tender_folders:
            self._send_log_sync("warning", "No filtered tender folders found", {})
            return 0
        
        self._send_log_sync("info", f"Processing {len(tender_folders)} filtered tender(s)", {})
        
        total_forms_extracted = 0
        
        for tender_name in tender_folders:
            if self.should_stop:
                break
            
            tender_path = os.path.join(filtered_folder, tender_name)
            tender_extracted_folder = os.path.join(extracted_folder, tender_name)
            os.makedirs(tender_extracted_folder, exist_ok=True)
            
            pdfs = [f for f in os.listdir(tender_path) if f.lower().endswith(".pdf")]
            
            if not pdfs:
                continue
            
            self._send_log_sync("info", f"Extracting from tender: {tender_name}", {})
            
            for idx, pdf_name in enumerate(pdfs, 1):
                if self.should_stop:
                    break
                    
                pdf_path = os.path.join(tender_path, pdf_name)
                base_name = os.path.splitext(pdf_name)[0]
                
                self._send_progress_sync("extracting", idx, len(pdfs), f"Extracting forms from: {pdf_name}")
                self._send_log_sync("info", f"[{idx}/{len(pdfs)}] Processing: {pdf_name}", {})
                
                sample_file = self._upload_to_gemini(pdf_path, pdf_name)
                
                if sample_file is None:
                    self._send_log_sync("error", f"Failed to upload {pdf_name} to Gemini", {})
                    continue
                
                total_forms, forms_list = self._detect_forms(pdf_path, sample_file)
                
                if total_forms == 0:
                    self._send_log_sync("warning", f"No forms detected, extracting entire document as single form", {})
                    reader = PdfReader(pdf_path)
                    total_pages = len(reader.pages)
                    forms_list = [{
                        "form_title": f"Complete Bid Document - {base_name}",
                        "start_page": 1,
                        "end_page": total_pages,
                        "confidence": "medium"
                    }]
                    total_forms = 1
                
                self._send_log_sync("info", f"Found {total_forms} form(s) in {pdf_name}", {})
                
                deadline_info = self._extract_deadline(pdf_path, sample_file)
                
                if deadline_info.get("deadline_found"):
                    deadline_date = deadline_info.get("deadline_date", "Not specified")
                    self._send_log_sync("info", f"Deadline: {deadline_date}", {})
                
                metadata = {
                    "pdf_name": pdf_name,
                    "total_forms": total_forms,
                    "forms": forms_list,
                    "deadline_info": deadline_info
                }
                
                metadata_path = os.path.join(metadata_folder, f"{base_name}_metadata.json")
                with open(metadata_path, "w", encoding="utf-8") as mf:
                    json.dump(metadata, mf, indent=2, ensure_ascii=False)
                
                if forms_list:
                    for form_idx, form in enumerate(forms_list, 1):
                        if self.should_stop:
                            break
                        
                        form_title = form.get("form_title", f"Form_{form_idx}")
                        start_page = form.get("start_page", 1)
                        end_page = form.get("end_page", 1)
                        
                        self._send_log_sync("info", f"Form {form_idx}/{total_forms}: {form_title} (Pages {start_page}-{end_page})", {})
                        
                        safe_title = re.sub(r'[^\w\s-]', '', form_title).strip().replace(' ', '_')[:50]
                        output_pdf = os.path.join(tender_extracted_folder, f"FORM{form_idx}_{safe_title}.pdf")
                        
                        self._extract_pages(pdf_path, start_page, end_page, output_pdf)
                        
                        total_forms_extracted += 1
                
                self._delete_gemini_file(sample_file)
        
        self._send_log_sync("success", f"Extraction complete: {total_forms_extracted} forms extracted", {})
        return total_forms_extracted
    
    def _upload_to_gemini(self, pdf_path, pdf_name):
        try:
            self._send_log_sync("info", f"Uploading to Gemini...", {})
            sample_file = genai.upload_file(path=pdf_path, display_name=pdf_name)
            while sample_file.state.name == "PROCESSING":
                time.sleep(2)
                sample_file = genai.get_file(sample_file.name)
            
            if sample_file.state.name == "FAILED":
                return None
            
            return sample_file
        except Exception as e:
            print(f"[ERROR] Gemini upload error: {e}")
            return None
    
    def _detect_forms(self, pdf_path, sample_file):
        detection_prompt = """You are analyzing a tender/procurement PDF document. Your task is to find ALL sections that bidders need to fill, respond to, or submit.

TYPES OF FORMS TO DETECT:

1. TRADITIONAL FORMS:
   - Has titles like "ANNEXURE-I", "ANNEXURE-II", "TECHNICAL BID", "FINANCIAL BID"
   - Contains blank fields, tables, checkboxes to fill
   - Ends with signature/seal/date blocks

2. GeM/GOVERNMENT TENDER DOCUMENTS:
   - "Additional Qualification/Data Required" sections
   - "Technical Specifications" sections that need bidder response
   - "Buyer Added Bid Specific Terms" requiring acceptance/compliance
   - "Document required from seller" sections
   - Any section requiring bidder to submit documents or information

3. COMPLIANCE SECTIONS:
   - Eligibility criteria requiring documentation
   - Experience criteria sections
   - Financial standing requirements
   - Technical qualification parameters
   - Pre-bid requirements

4. SUBMISSION REQUIREMENTS:
   - EMD (Earnest Money Deposit) details
   - ePBG (e-Performance Bank Guarantee) details
   - Certificate requirements
   - Undertaking requirements

FOR EACH FORM/SECTION FOUND:
1. Identify the exact title or heading
2. Determine start and end page numbers
3. Assess confidence level (high/medium/low)

IMPORTANT:
- If document is a GeM tender, extract key sections as separate "forms"
- Even if there are no traditional blank forms, extract sections requiring bidder action
- Look for any section with headings indicating bidder requirements

Return JSON with ALL forms/sections found using the AllFormsDetection schema."""
        
        try:
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": AllFormsDetection
                }
            )
            
            response = model.generate_content([sample_file, detection_prompt])
            result = json.loads(response.text)
            
            total_forms = result.get("total_forms_found", 0)
            forms_list = result.get("forms", [])
            
            return total_forms, forms_list
            
        except Exception as e:
            print(f"[ERROR] Gemini form detection error: {e}")
            return 0, []
    
    def _extract_deadline(self, pdf_path, sample_file):
        deadline_prompt = """You are analyzing a tender/procurement document. Find the tender submission deadline.

Look for phrases like:
- "Last date of submission"
- "Bid closing date"
- "Tender closing date"
- "Deadline for submission"
- "Submit by"
- "Due date"
- "Bid opening date"

Extract the exact date mentioned.

Return JSON using the TenderDeadline schema."""
        
        try:
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": TenderDeadline
                }
            )
            
            response = model.generate_content([sample_file, deadline_prompt])
            result = json.loads(response.text)
            
            return result
            
        except Exception as e:
            return {"deadline_found": False, "deadline_date": None}
    
    def _extract_pages(self, pdf_path, start_page, end_page, output_path):
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        total_pages = len(reader.pages)
        
        if start_page < 1:
            start_page = 1
        if end_page > total_pages:
            end_page = total_pages
        
        for page_num in range(start_page - 1, end_page):
            writer.add_page(reader.pages[page_num])
        
        with open(output_path, "wb") as out:
            writer.write(out)
    
    def _delete_gemini_file(self, sample_file):
        if sample_file:
            try:
                genai.delete_file(sample_file.name)
            except:
                pass
    
    def _convert_to_docx_sync(self):
        extracted_folder = self.output_folders["extracted"]
        docx_folder = self.output_folders["docx"]
        
        all_pdfs = []
        for root, dirs, files in os.walk(extracted_folder):
            for file in files:
                if file.lower().endswith(".pdf"):
                    all_pdfs.append(os.path.join(root, file))
        
        if not all_pdfs:
            self._send_log_sync("warning", "No extracted PDFs found to convert", {})
            return 0
        
        self._send_log_sync("info", f"Converting {len(all_pdfs)} PDF(s) to DOCX", {})
        
        conversion_count = 0
        
        for idx, pdf_path in enumerate(all_pdfs, 1):
            if self.should_stop:
                break
                
            pdf_name = os.path.basename(pdf_path)
            
            rel_path = os.path.relpath(pdf_path, extracted_folder)
            docx_name = rel_path.replace(".pdf", ".docx")
            docx_path = os.path.join(docx_folder, docx_name)
            
            os.makedirs(os.path.dirname(docx_path), exist_ok=True)
            
            self._send_progress_sync("converting", idx, len(all_pdfs), f"Converting: {pdf_name}")
            
            try:
                parse(pdf_path, docx_path, start=0, end=None)
                self._send_log_sync("success", f"Converted ({idx}/{len(all_pdfs)}): {pdf_name}", {})
                conversion_count += 1
            except Exception as e:
                self._send_log_sync("error", f"Conversion failed for {pdf_name}: {str(e)}", {})
        
        self._send_log_sync("success", f"Conversion complete: {conversion_count} DOCX files created", {})
        return conversion_count