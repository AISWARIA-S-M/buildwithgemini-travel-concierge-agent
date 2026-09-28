import sys
from google.cloud import firestore

# Project ID hardcoded as required (must be string ID, not project number)
PROJECT_ID = "qwiklabs-gcp-01-177db1a37a1b"

SAMPLE_DESTINATIONS = [
    {
        "id": "dest_kyoto",
        "name": "Kyoto Historic Temples & Bamboo Grove",
        "city": "Kyoto",
        "country": "Japan",
        "category": "Culture & Heritage",
        "rating": 4.9,
        "description": "Explore ancient shrines, traditional tea houses, and Arashiyama bamboo groves.",
        "best_season": "Spring & Autumn"
    },
    {
        "id": "dest_sf",
        "name": "San Francisco Coastal & Bay Experience",
        "city": "San Francisco",
        "country": "USA",
        "category": "Sightseeing & Nature",
        "rating": 4.8,
        "description": "Walk across the Golden Gate Bridge, tour Alcatraz Island, and explore Fisherman's Wharf.",
        "best_season": "Fall & Summer"
    },
    {
        "id": "dest_paris",
        "name": "Paris Art, Gastronomy & Landmarks",
        "city": "Paris",
        "country": "France",
        "category": "Art & Culinary",
        "rating": 4.9,
        "description": "Visit the Louvre Museum, Eiffel Tower, and enjoy world-class Parisian cafes and pastry shops.",
        "best_season": "Spring & Autumn"
    },
    {
        "id": "dest_cancun",
        "name": "Cancun Riviera & Maya Ruins",
        "city": "Cancun",
        "country": "Mexico",
        "category": "Beach & Tropical",
        "rating": 4.7,
        "description": "Relax on white sand beaches and explore ancient Mayan pyramids at Chichen Itza.",
        "best_season": "Winter & Spring"
    }
]

def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("destinations")
    
    count = 0
    for item in SAMPLE_DESTINATIONS:
        doc_id = item["id"]
        collection_ref.document(doc_id).set(item)
        print(f"Seeded destination: {item['name']} ({doc_id})")
        count += 1

    print(f"Successfully seeded {count} items into 'destinations' collection!")

if __name__ == "__main__":
    seed_database()
