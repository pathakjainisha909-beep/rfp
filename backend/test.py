import os
import json

metadata_folder = "data/metadata"
docx_folder = "data/output_docx"
results = []

if not os.path.exists(metadata_folder):
    print(f"ERROR: Metadata folder not found: {metadata_folder}")
    exit()

print(f"Reading metadata from: {os.path.abspath(metadata_folder)}")
print(f"Folders found: {os.listdir(metadata_folder)}")

# Loop through each tender in metadata folder
for tender_name in os.listdir(metadata_folder):
    tender_metadata_path = os.path.join(metadata_folder, tender_name, "tender_metadata.json")
    
    print(f"\n=== Processing: {tender_name} ===")
    print(f"Looking for file: {tender_metadata_path}")
    print(f"File exists: {os.path.exists(tender_metadata_path)}")
    
    if not os.path.exists(tender_metadata_path):
        print(f"SKIP: Metadata file not found")
        continue
    
    # Read the pre-generated metadata
    try:
        with open(tender_metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            print(f"✓ Successfully loaded metadata")
            print(f"  Summary: {metadata.get('summary', 'N/A')[:100]}...")
            print(f"  Deadline found: {metadata.get('deadline', {}).get('deadline_found', False)}")
    except Exception as e:
        print(f"ERROR reading JSON: {e}")
        continue
    
    # Get description from metadata
    description = metadata.get("summary", "Summary unavailable.")
    
    # Get deadline from metadata
    deadline_info = metadata.get("deadline", {})
    if deadline_info.get("deadline_found", False):
        deadline = deadline_info.get("deadline_date", "Not found")
    else:
        deadline = "Not found"
    
    print(f"  Final deadline: {deadline}")
    
    # Count DOCX files from output_docx folder
    tender_docx_path = os.path.join(docx_folder, tender_name)
    forms_count = 0
    if os.path.exists(tender_docx_path):
        docx_files = [
            f for f in os.listdir(tender_docx_path)
            if f.lower().endswith(".docx")
        ]
        forms_count = len(docx_files)
    
    print(f"  Forms count: {forms_count}")
    
    results.append({
        "tender_name": tender_name,
        "description": description,
        "last_date": deadline,
        "forms_count": forms_count,
        "download_url": f"/api/download/{tender_name}"
    })

print(f"\n=== FINAL RESULTS ===")
print(json.dumps(results, indent=2))