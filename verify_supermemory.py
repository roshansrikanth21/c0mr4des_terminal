import os
import sys
from dotenv import load_dotenv

# Add the project root to sys.path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv(dotenv_path="backend/.env")

from backend.services.memory_service import memory_service

def verify_memory():
    print("--- Supermemory AI Integration Verification ---")
    
    # 1. Test Storage
    test_content = "V1.5 SYSTEM UPDATE: Lucent Terminal integrated Supermemory AI for long-term intelligence archiving. This is a verification event."
    print(f"Adding memory: {test_content}")
    success = memory_service.add_memory(content=test_content, source="verification_script")
    
    if success:
        print("✓ Storage successful!")
    else:
        print("✗ Storage failed. Check API key and connectivity.")
        return

    # 2. Test Retrieval
    query = "integrated Supermemory AI"
    print(f"Querying memories for: '{query}'")
    results = memory_service.query_memories(query=query)
    
    print(f"Found {len(results)} results:")
    for i, res in enumerate(results):
        print(f"[{i+1}] RAW: {res}")
        print(f"[{i+1}] CONTENT: {res.get('content') or res.get('text') or 'No content found'}")

if __name__ == "__main__":
    verify_memory()
