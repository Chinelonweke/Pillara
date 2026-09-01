from dotenv import load_dotenv
load_dotenv()
from core.secrets_loader import load_secrets_from_infisical
load_secrets_from_infisical()
import chromadb
from chromadb.config import Settings as ChromaSettings

client = chromadb.HttpClient(host='localhost', port=8001, settings=ChromaSettings(anonymized_telemetry=False))
col = client.get_collection('drug_knowledge')

print("Total chunks:", col.count())

results = col.query(
    query_texts=['drug interactions between warfarin and ibuprofen'],
    n_results=5,
    where={"drug_name": {"$in": ["warfarin", "ibuprofen"]}}
)
for i in range(len(results['documents'][0])):
    doc = results['documents'][0][i]
    meta = results['metadatas'][0][i]
    dist = results['distances'][0][i]
    drug = meta.get('drug_name')
    section = meta.get('section')
    print(f"Chunk {i+1}: drug={drug} section={section} dist={round(dist,3)}")
    print(f"  Text: {doc[:150]}")
    print()