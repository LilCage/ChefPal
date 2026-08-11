"""语音输入 TDD：POST /api/voice/transcribe 上传音频 → 百炼 ASR 转文字。"""
from app.routers import voice as voice_router
from app.services import asr as asr_service

AUDIO_BYTES = b"RIFF-fake-audio-data-for-test"


def _mock_asr(monkeypatch, text="冰箱里有西红柿、鸡蛋", error=None):
    async def _fake(audio_bytes: bytes, mime_type: str = "audio/mpeg") -> str:
        if error:
            raise error
        return text

    monkeypatch.setattr(asr_service, "transcribe_audio", _fake)
    return _fake


def _upload(client, headers=None, data=AUDIO_BYTES, mime="audio/mpeg"):
    return client.post(
        "/api/voice/transcribe",
        files={"file": ("voice.mp3", data, mime)},
        headers=headers,
    )


# ---------- 转写 ----------
def test_transcribe_success(client, auth_headers, monkeypatch):
    _mock_asr(monkeypatch)
    res = _upload(client, auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["text"] == "冰箱里有西红柿、鸡蛋"


def test_transcribe_passes_audio_and_mime(monkeypatch):
    captured = {}

    async def _fake(audio_bytes: bytes, mime_type: str = "audio/mpeg") -> str:
        captured["audio"] = audio_bytes
        captured["mime"] = mime_type
        return "西红柿"

    monkeypatch.setattr(asr_service, "transcribe_audio", _fake)
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        # 需要登录
        from app.core.config import get_settings
        from app.services import wechat as wechat_service

        async def _code2session(code: str) -> dict:
            return {"openid": "openid-voice", "session_key": "s"}

        monkeypatch.setattr(wechat_service, "code2session", _code2session)
        token = client.post("/api/auth/login", json={"code": "c"}).json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        res = _upload(client, headers, data=b"myaudio", mime="audio/wav")
        assert res.status_code == 200
        assert captured["audio"] == b"myaudio"
        assert captured["mime"] == "audio/wav"


def test_transcribe_empty_file_400(client, auth_headers, monkeypatch):
    _mock_asr(monkeypatch)
    res = _upload(client, auth_headers, data=b"")
    assert res.status_code == 400
    assert "音频" in res.json()["message"]


def test_transcribe_requires_auth(client, monkeypatch):
    _mock_asr(monkeypatch)
    assert _upload(client).status_code == 401


def test_transcribe_service_error_502(client, auth_headers, monkeypatch):
    _mock_asr(monkeypatch, error=asr_service.ASRError("mock 识别失败"))
    res = _upload(client, auth_headers)
    assert res.status_code == 502


def test_transcribe_rate_limit(client, auth_headers, monkeypatch):
    from app.core.response import AppError

    _mock_asr(monkeypatch)

    async def _over(db, user_id, limit):
        raise AppError("今日调用已达上限，明日再来吧", code=429, status_code=429)

    monkeypatch.setattr(voice_router, "ensure_within_limit", _over)
    res = _upload(client, auth_headers)
    assert res.status_code == 429
    assert "上限" in res.json()["message"]
