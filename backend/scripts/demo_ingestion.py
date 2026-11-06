"""
scripts/demo_ingestion.py
ApexCloud Technologies Phase 4 Content Ingestion Demo Scenario.
Demonstrates:
1. File upload
2. Validation
3. Real text extraction
4. Structured content & sentence segment generation
5. Content preview
6. Database persistence
7. Retrieval & listing
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def run_demo():
    print("=================================================================")
    print(" BrandGuard Phase 4 Demo: ApexCloud Technologies Content Ingestion")
    print("=================================================================")

    # 1. Bootstrap demo organization
    slug = f"apexcloud-demo-{uuid.uuid4().hex[:6]}"
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "ApexCloud Technologies Inc.",
        "org_slug": slug,
        "admin_email": f"growth_{slug}@apexcloud.io",
        "admin_password": "ApexSecurePass123!",
        "admin_full_name": "Sarah Connor (Head of Growth)"
    })
    token = boot.json()["access_token"]
    org_id = boot.json()["user"]["organization_id"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[OK] Organization bootstrapped: ApexCloud Technologies Inc. (slug={slug})")

    # 2. Campaign Document
    campaign_doc = (
        "ApexCloud Enterprise Cloud Modernization\n\n"
        "Transform your infrastructure with ApexCloud next-generation serverless architecture.\n\n"
        "Product Overview\n"
        "ApexCloud is an enterprise-grade cloud computing platform delivering instant auto-scaling, "
        "automated multi-region replication, and zero-maintenance operations. Engineered specifically "
        "for mission-critical microservices and high-throughput distributed applications.\n\n"
        "Key Performance Guarantees\n"
        "Our platform delivers guaranteed sub-15ms global latency and an industry-leading 99.99% availability SLA. "
        "With proactive failover protection across 42 global edge locations, your workloads never experience unexpected downtime.\n\n"
        "Transparent Enterprise Pricing\n"
        "Starting at just $49 per month for growth teams, scaling up to dedicated enterprise clusters at $499 per month "
        "with bespoke security compliance and 24/7 dedicated site reliability engineers.\n\n"
        "Call to Action\n"
        "Migrate to ApexCloud today and claim $1,000 in promotional cloud computing credits. "
        "Visit apexcloud.io/modernize to deploy your first container in under 60 seconds."
    )

    filename = "ApexCloud_Q4_Modernization_Campaign.txt"
    print(f"\n[STEP 1 & 2] Uploading and validating '{filename}'...")
    upload_res = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": (filename, campaign_doc.encode("utf-8"), "text/plain")},
        data={"title": "ApexCloud Q4 Modernization Campaign"}
    )
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    upload_data = upload_res.json()
    doc = upload_data["document"]
    ver = upload_data["version"]

    print(f"  -> Upload HTTP Status: {upload_res.status_code} Created")
    print(f"  -> Stored Document ID: {doc['id']}")
    print(f"  -> Document Title:     {doc['title']}")
    print(f"  -> Content Type:       {doc['content_type']}")
    print(f"  -> Version Number:     v{ver['version_number']}")

    # 3. Extraction & Structuring
    print(f"\n[STEP 3 & 4] Content Extraction & Structuring:")
    print(f"  -> Extraction Status:  {ver['extraction_status']}")
    print(f"  -> Word Count:         {ver['word_count']} words")
    print(f"  -> Character Count:    {ver['character_count']} characters")
    structured = ver["structured_content"]
    print(f"  -> Total Pages:        {structured['total_pages']}")
    print(f"  -> Total Paragraphs:   {structured['total_paragraphs']}")
    print(f"  -> Total Segments:     {structured['total_segments']}")

    # 4. Preview Segments
    print(f"\n[STEP 5] Extracted Structured Segments Preview:")
    for seg in structured["segments"][:5]:
        print(f"   [{seg['segment_id']}] (page {seg['page_number']}, para {seg['paragraph_index']}, char [{seg['char_start']}..{seg['char_end']}]):")
        print(f"      \"{seg['text']}\"")

    # 5. Persistence & Retrieval
    print(f"\n[STEP 6 & 7] Database Persistence & Document Retrieval:")
    doc_res = client.get(f"/api/v1/documents/{doc['id']}", headers=headers)
    assert doc_res.status_code == 200
    retrieved_doc = doc_res.json()
    print(f"  -> Retrieved Document ID: {retrieved_doc['id']}")
    print(f"  -> Confirmed Title:       {retrieved_doc['title']}")
    print(f"  -> Creator User ID:       {retrieved_doc['creator_id']}")
    print(f"  -> Stored Original File:  {retrieved_doc['latest_version']['original_filename']}")

    list_res = client.get("/api/v1/documents", headers=headers)
    assert list_res.status_code == 200
    print(f"  -> Organization Documents Count: {len(list_res.json())}")

    print("\n=================================================================")
    print(" [SUCCESS] Phase 4 Demo Scenario Completed Successfully!")
    print("=================================================================")

if __name__ == "__main__":
    run_demo()
