from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_service import AIService

client = TestClient(app)


def test_clean_for_speech():
    raw_markdown = (
        "🪔 **दिवाळी विशेष स्टॉक सल्ला**\n\n"
        "खालील *महत्त्वाच्या* वस्तूंचा स्टॉक वाढवा:\n"
        "• 1. **साखर (Sugar)** — अपेक्षित मागणी: 100 kg\n"
        "• 2. **खाद्यतेल (Cooking Oil)** — अपेक्षित मागणी: 50 Ltr\n\n"
        "अधिक माहितीसाठी [येथे क्लिक करा](https://example.com)."
    )
    cleaned = AIService._clean_for_speech(raw_markdown)
    # Ensure asterisks and bullet symbols are stripped
    assert "*" not in cleaned
    assert "•" not in cleaned
    assert "🪔" not in cleaned
    assert "दिवाळी विशेष स्टॉक सल्ला" in cleaned
    assert "साखर (Sugar)" in cleaned
    assert "खाद्यतेल (Cooking Oil)" in cleaned


def test_voice_assistant_html_ui_endpoint():
    # Test /api/v1/ai/voice-assistant
    res = client.get("/api/v1/ai/voice-assistant")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Retail-OS AI Voice Copilot" in res.text
    assert "micBtn" in res.text
    assert "SpeechRecognition" in res.text
    assert "speechSynthesis" in res.text

    # Test /voice-assistant redirect
    res_root = client.get("/voice-assistant", follow_redirects=False)
    assert res_root.status_code in (302, 307)
    assert "/api/v1/ai/voice-assistant" in res_root.headers["location"]


@pytest.fixture
def voice_auth_setup(unique_slug):
    email = f"voice-{unique_slug}@retailtest.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Voice AI Test Store",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Voice Admin",
            "password": "Password123!",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {"headers": headers, "email": email}


def test_voice_query_text_endpoint(voice_auth_setup):
    headers = voice_auth_setup["headers"]

    # 1. Marathi query
    res = client.post(
        "/api/v1/ai/voice-query",
        json={"query": "आजचा एकूण गल्ला किती झाला?", "language": "mr-IN"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "query" in data
    assert "answer" in data
    assert "speech_text" in data
    assert len(data["speech_text"]) > 0
    assert "*" not in data["speech_text"]
    assert data["language"] in ("mr-IN", "hi-IN", "en-IN")

    # 2. English query via /voice
    res_en = client.post(
        "/api/v1/ai/voice",
        json={"query": "What are today's sales figures?", "language": "en-IN"},
        headers=headers,
    )
    assert res_en.status_code == 200
    d_en = res_en.json()
    assert "speech_text" in d_en
    assert "today" in d_en["speech_text"].lower() or "sales" in d_en["speech_text"].lower()


def test_voice_query_audio_base64_handling(voice_auth_setup):
    headers = voice_auth_setup["headers"]

    mock_audio_response = {
        "query": "साखरेचा स्टॉक किती बाकी आहे?",
        "transcription": "साखरेचा स्टॉक किती बाकी आहे?",
        "intent": "stock_alerts",
        "answer": "साखरेचा स्टॉक सध्या 50 किलो शिल्लक आहे.",
        "speech_text": "साखरेचा स्टॉक सध्या 50 किलो शिल्लक आहे.",
        "data": {"product": "Sugar", "stock": 50},
        "suggested_actions": ["Check inventory"],
    }

    with patch.object(AIService, "_call_gemini_audio_copilot", return_value=mock_audio_response):
        res = client.post(
            "/api/v1/ai/voice-query",
            json={
                "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA...",
                "audio_mime_type": "audio/webm",
                "language": "mr-IN",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["query"] == "साखरेचा स्टॉक किती बाकी आहे?"
        assert data["speech_text"] == "साखरेचा स्टॉक सध्या 50 किलो शिल्लक आहे."
        assert data["language"] == "mr-IN"


def test_chat_query_includes_speech_text(voice_auth_setup):
    headers = voice_auth_setup["headers"]

    res = client.post(
        "/api/v1/ai/chat",
        json={"query": "How many items are low in stock?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "speech_text" in data
    assert data["speech_text"] is not None
    assert "*" not in data["speech_text"]
