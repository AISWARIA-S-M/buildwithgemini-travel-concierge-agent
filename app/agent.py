import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types

load_dotenv()

# Hardcoded GCP Project ID and Bucket Name to prevent Agent Platform environment resolution issues
GCP_PROJECT_ID = "qwiklabs-gcp-01-177db1a37a1b"
BUCKET_NAME = "travel-concierge-assets-qwiklabs-gcp-01-177db1a37a1b"

db = firestore.Client(project=GCP_PROJECT_ID)
storage_client = storage.Client(project=GCP_PROJECT_ID)


def search_destinations(city: str = "", category: str = "") -> str:
    """Searches the Firestore database for travel destinations.

    Args:
        city: Optional city name to filter by (e.g. 'Kyoto', 'Paris', 'San Francisco').
        category: Optional category filter (e.g. 'Culture & Heritage', 'Beach & Tropical', 'Art & Culinary').

    Returns:
        JSON string containing list of matching travel destinations.
    """
    collection_ref = db.collection("destinations")
    docs = collection_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        match_city = not city or city.lower() in data.get("city", "").lower()
        match_cat = not category or category.lower() in data.get("category", "").lower()
        if match_city and match_cat:
            results.append(data)

    if not results:
        return f"No destinations found matching city='{city}' category='{category}'."
    return json.dumps(results, indent=2)


def add_destination(
    name: str,
    city: str,
    country: str,
    category: str,
    description: str,
    rating: float = 4.5,
    best_season: str = "All Year",
) -> str:
    """Adds a new travel destination to the Firestore database.

    Args:
        name: Name of the destination attraction or experience.
        city: City where the destination is located.
        country: Country where the destination is located.
        category: Travel category (e.g. 'Culture & Heritage', 'Beach & Tropical', 'Art & Culinary').
        description: Short description of the destination.
        rating: Rating score out of 5.0 (default 4.5).
        best_season: Recommended time of year to visit.

    Returns:
        A confirmation message with details of the saved destination.
    """
    doc_id = f"dest_{city.lower().replace(' ', '_')}_{name.lower().replace(' ', '_')[:10]}"
    data = {
        "id": doc_id,
        "name": name,
        "city": city,
        "country": country,
        "category": category,
        "description": description,
        "rating": float(rating),
        "best_season": best_season,
    }
    db.collection("destinations").document(doc_id).set(data)
    return f"Successfully added destination '{name}' in {city}, {country} (ID: {doc_id})."


def calculate_travel_budget(
    destination: str,
    duration_days: int,
    accommodation_style: str = "mid-range",
    travelers: int = 1,
    currency: str = "USD",
) -> str:
    """Calculates an estimated travel budget for a trip.

    Args:
        destination: Name of the destination city or country.
        duration_days: Number of days for the trip.
        accommodation_style: Travel style level ('budget', 'mid-range', or 'luxury').
        travelers: Total number of travelers.
        currency: Output currency code ('USD', 'EUR', 'JPY', 'GBP').

    Returns:
        JSON string detailing estimated costs for lodging, dining, activities, transport, and total.
    """
    style_multipliers = {
        "budget": {"lodging": 50, "food": 30, "activities": 20},
        "mid-range": {"lodging": 150, "food": 70, "activities": 50},
        "luxury": {"lodging": 400, "food": 180, "activities": 150},
    }
    rates = style_multipliers.get(accommodation_style.lower(), style_multipliers["mid-range"])

    currency_rates = {"USD": 1.0, "EUR": 0.92, "JPY": 155.0, "GBP": 0.78}
    fx = currency_rates.get(currency.upper(), 1.0)

    lodging = rates["lodging"] * duration_days * travelers * fx
    food = rates["food"] * duration_days * travelers * fx
    activities = rates["activities"] * duration_days * travelers * fx
    transport = 100 * travelers * fx
    total = lodging + food + activities + transport

    breakdown = {
        "destination": destination,
        "duration_days": duration_days,
        "travelers": travelers,
        "style": accommodation_style,
        "currency": currency.upper(),
        "estimated_breakdown": {
            "lodging": round(lodging, 2),
            "food_and_dining": round(food, 2),
            "activities": round(activities, 2),
            "transport_allowance": round(transport, 2),
            "total_estimated_cost": round(total, 2),
        },
    }
    return json.dumps(breakdown, indent=2)


def get_live_destination_weather(location: str) -> str:
    """Fetches real live weather conditions and location details for any destination city worldwide via Open-Meteo public API.

    Args:
        location: Name of the city or travel spot (e.g. 'Kyoto', 'Paris', 'Cancun', 'Tokyo').

    Returns:
        JSON string with real-time temperature, humidity, wind speed, timezone, and coordinates.
    """
    api_key = os.environ.get("OPEN_METEO_API_KEY", "")

    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(location)}&count=1&language=en&format=json"
    if api_key:
        geo_url += f"&apikey={api_key}"

    req = urllib.request.Request(geo_url, headers={"User-Agent": "TravelConciergeAgent/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            geo_data = json.loads(resp.read().decode())
    except Exception as e:
        return f"Error geocoding location '{location}': {str(e)}"

    results = geo_data.get("results")
    if not results:
        return f"Location '{location}' not found in geocoding database."

    loc = results[0]
    lat, lon = loc["latitude"], loc["longitude"]
    city_name = loc.get("name", location)
    country = loc.get("country", "")
    timezone = loc.get("timezone", "")

    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
    if api_key:
        weather_url += f"&apikey={api_key}"

    req_w = urllib.request.Request(weather_url, headers={"User-Agent": "TravelConciergeAgent/1.0"})
    try:
        with urllib.request.urlopen(req_w) as resp_w:
            weather_data = json.loads(resp_w.read().decode())
    except Exception as e:
        return f"Error fetching live weather for '{location}': {str(e)}"

    current = weather_data.get("current", {})
    units = weather_data.get("current_units", {})

    info = {
        "location": city_name,
        "country": country,
        "timezone": timezone,
        "coordinates": {"latitude": lat, "longitude": lon},
        "current_weather": {
            "temperature": f"{current.get('temperature_2m')} {units.get('temperature_2m', '°C')}",
            "relative_humidity": f"{current.get('relative_humidity_2m')} {units.get('relative_humidity_2m', '%')}",
            "wind_speed": f"{current.get('wind_speed_10m')} {units.get('wind_speed_10m', 'km/h')}",
            "time_utc": current.get("time"),
        },
    }
    return json.dumps(info, indent=2)


def geocode_address(address: str) -> str:
    """Converts an address or landmark into latitude/longitude coordinates using Google Maps Geocoding API.

    Args:
        address: Address or landmark name (e.g., 'Kiyomizu-dera, Kyoto' or 'Eiffel Tower, Paris').

    Returns:
        JSON string with formatted address and location coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY is not configured in environment."

    geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
    try:
        with urllib.request.urlopen(geo_url) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return f"Error calling Geocoding API: {str(e)}"

    if data.get("status") != "OK" or not data.get("results"):
        return f"Geocoding failed for '{address}': status={data.get('status')}."

    first = data["results"][0]
    loc = first.get("geometry", {}).get("location", {})
    res = {
        "address_query": address,
        "formatted_address": first.get("formatted_address"),
        "location": {
            "latitude": loc.get("lat"),
            "longitude": loc.get("lng"),
        },
    }
    return json.dumps(res, indent=2)


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 1000.0,
) -> str:
    """Finds nearby points of interest of a given type around coordinates using Places API (New).

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Place type category (e.g. 'restaurant', 'tourist_attraction', 'cafe', 'museum', 'lodging').
        radius_meters: Search radius in meters (default: 1000.0).

    Returns:
        JSON string listing nearby places with display name, formatted address, and location coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY is not configured in environment."

    places_url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.types",
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 10,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius_meters,
            }
        },
    }
    req = urllib.request.Request(
        places_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return f"Error calling Places API (New): {str(e)}"

    places = data.get("places", [])
    if not places:
        return f"No nearby places found of type '{place_type}' within {radius_meters}m radius."

    results = []
    for p in places:
        name = p.get("displayName", {}).get("text", "")
        results.append(
            {
                "name": name,
                "address": p.get("formattedAddress"),
                "location": p.get("location"),
                "types": p.get("types", []),
            }
        )
    return json.dumps(results, indent=2)


def generate_destination_image(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates an image for a travel destination item using gemini-3.1-flash-lite-image in the global region, saves it as an artifact, and uploads to public Cloud Storage.

    Args:
        prompt: Description of the destination scene or attraction to generate an image for (e.g. 'Scenic sunset over Mount Fuji with cherry blossoms').
        tool_context: Context for saving artifacts in the ADK session.

    Returns:
        JSON string containing public Cloud Storage https URL and artifact filename.
    """
    genai_client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location="global",
    )

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )
    except Exception as e:
        return f"Error generating image with gemini-3.1-flash-lite-image: {str(e)}"

    image_bytes = None
    mime_type = "image/jpeg"
    if response and response.candidates:
        for candidate in response.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        image_bytes = part.inline_data.data
                        mime_type = part.inline_data.mime_type or "image/jpeg"
                        break
            if image_bytes:
                break

    if not image_bytes:
        return "Failed to retrieve image bytes from gemini-3.1-flash-lite-image response."

    ext = "jpg" if "jpeg" in mime_type.lower() else "png"
    clean_filename = f"destination_{int(datetime.datetime.now().timestamp())}.{ext}"

    # (1) Save artifact in tool_context so it appears in Playground Artifacts panel
    if tool_context:
        try:
            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=clean_filename, artifact=part)
        except Exception as err:
            print(f"Warning: Failed to save artifact in tool_context: {err}")

    # (2) Upload image bytes directly to public Cloud Storage bucket without saving to local file
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(clean_filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)
        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{clean_filename}"
    except Exception as err:
        return f"Image generated, but error uploading to Cloud Storage bucket '{BUCKET_NAME}': {str(err)}"

    result = {
        "status": "success",
        "prompt": prompt,
        "artifact_filename": clean_filename,
        "public_url": public_url,
    }
    return json.dumps(result, indent=2)


def generate_destination_video(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates a short video for a travel destination using Google's gemini-omni-flash-preview model in the global region, saves it as an artifact, and uploads to public Cloud Storage.

    Args:
        prompt: Description of the travel destination scene or activity to generate a video for (e.g. 'A short drone clip flying over a white sand beach in Cancun').
        tool_context: Context for saving artifacts in the ADK session.

    Returns:
        JSON string containing public Cloud Storage https URL and artifact filename.
    """
    genai_client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location="global",
    )

    try:
        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )
    except Exception as e:
        return f"Error generating video with gemini-omni-flash-preview: {str(e)}"

    video_bytes = None
    mime_type = "video/mp4"

    if hasattr(interaction, "output_video") and interaction.output_video:
        if hasattr(interaction.output_video, "data") and interaction.output_video.data:
            data = interaction.output_video.data
            if isinstance(data, str):
                video_bytes = base64.b64decode(data)
            else:
                video_bytes = data
    elif hasattr(interaction, "outputs") and interaction.outputs:
        for out in interaction.outputs:
            if hasattr(out, "data") and out.data:
                video_bytes = base64.b64decode(out.data) if isinstance(out.data, str) else out.data
                break

    if not video_bytes:
        return "Failed to retrieve video bytes from gemini-omni-flash-preview response."

    clean_filename = f"destination_video_{int(datetime.datetime.now().timestamp())}.mp4"

    # (1) Save artifact in tool_context so it appears in Playground Artifacts panel
    if tool_context:
        try:
            part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=clean_filename, artifact=part)
        except Exception as err:
            print(f"Warning: Failed to save video artifact in tool_context: {err}")

    # (2) Upload video bytes directly to public Cloud Storage bucket without saving to local file
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(clean_filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)
        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{clean_filename}"
    except Exception as err:
        return f"Video generated, but error uploading to Cloud Storage bucket '{BUCKET_NAME}': {str(err)}"

    result = {
        "status": "success",
        "prompt": prompt,
        "artifact_filename": clean_filename,
        "public_url": public_url,
    }
    return json.dumps(result, indent=2)


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback
from google.adk.agents.callback_context import CallbackContext
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

# Load agent engine resource name from deployment_metadata.json
DEPLOYMENT_METADATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "deployment_metadata.json"
)

agent_engine_resource_name = None
if os.path.exists(DEPLOYMENT_METADATA_PATH):
    try:
        with open(DEPLOYMENT_METADATA_PATH, "r") as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id")
    except Exception as e:
        print(f"Warning: Failed to read deployment_metadata.json: {e}")

if not agent_engine_resource_name:
    agent_engine_resource_name = "projects/1070403015650/locations/us-east1/reasoningEngines/1907685659540193280"

MEMORY_BANK_ID = agent_engine_resource_name.split("/")[-1]

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)


def memory_service_builder():
    """Builds VertexAiMemoryBankService using the deployed Reasoning Engine / Memory Bank ID."""
    return VertexAiMemoryBankService(
        project=GCP_PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE callback: after each turn, extracts and saves durable facts to Memory Bank."""
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Memory extraction note: {e}")
    return None


a2ui_schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = a2ui_schema_manager.generate_system_prompt(
    role_description=(
        "You are a helpful travel concierge AI assistant. "
        "You MUST pay special attention to and remember all user food allergies, dietary restrictions (e.g., peanuts, gluten, shellfish, dairy, vegan), "
        "and health preferences mentioned across conversations. Always consult retrieved user memories to filter out unsafe food, restaurant, or activity options and personalize your recommendations. "
        "Use your search_destinations, add_destination, calculate_travel_budget, get_live_destination_weather, geocode_address, find_nearby_places, generate_destination_image, and generate_destination_video tools to help users discover destinations, plan budgets, geocode locations, find nearby places, generate destination imagery, and generate video highlights. You can also write and execute Python code in your sandbox to do data processing or calculations."
    ),
    workflow_description="Analyze the user request, call relevant tools if needed, and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        client_kwargs={
            "vertexai": True,
            "project": GCP_PROJECT_ID,
            "location": "us-east1",
        },
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        add_destination,
        calculate_travel_budget,
        get_live_destination_weather,
        geocode_address,
        find_nearby_places,
        generate_destination_image,
        generate_destination_video,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)









