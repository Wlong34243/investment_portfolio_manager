import os
import logging
from google import genai
try:
    import config
except ImportError:
    config = None

def check_my_gemini_access():
    print("Checking your Gemini access (Vertex AI / ADC)...")

    project_id = getattr(config, 'GCP_PROJECT_ID', 're-property-manager-487122')
    location = getattr(config, 'GCP_LOCATION', 'us-central1')

    client = None
    try:
        # Path 1: Vertex AI (ADC)
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
        )
        print("✅ Using Vertex AI with Application Default Credentials (ADC).")
    except Exception as e:
        print(f"⚠️ ADC/Vertex AI setup error: {e}")
        # Path 2: API Key fallback
        api_key = os.environ.get('GEMINI_API_KEY')
        if api_key:
            client = genai.Client(api_key=api_key)
            print("✅ Falling back to AI Studio with GEMINI_API_KEY.")
        else:
            print("❌ No valid Gemini credentials found (ADC or API Key).")
            return

    if not client:
        return

    try:
        # For Vertex AI, we list models in the project/location
        print(f"Listing available models for {project_id} in {location}:\n")

        for model in client.models.list():
            # For 1.0.0 SDK, model object attributes are slightly different
            name = model.name
            print(f"📦 {name}")
            if hasattr(model, 'description') and model.description:
                print(f"   └ {model.description[:100]}...")
            print("")

        # Simple test generation
        test_model = getattr(config, 'GEMINI_MODEL', 'gemini-3.1-pro-preview-customtools')
        print(f"--- Running Test Generation with {test_model} ---")
        response = client.models.generate_content(
            model=test_model,
            contents="Hello! Give me a 5-word summary of your status."
        )
        print(f"✅ Response: {response.text.strip()}")

    except Exception as e:
        print(f"❌ Error during model check/generation: {e}")

if __name__ == "__main__":
    check_my_gemini_access()