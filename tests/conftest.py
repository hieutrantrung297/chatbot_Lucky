"""Shared fixtures and mocks for all tests."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is in path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Load real .env if present (needed for integration tests that call AI) ──
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Fallback defaults cho CI / unit tests không cần API ────────────────────
os.environ.setdefault("PAGE_ACCESS_TOKEN", "test_token")
os.environ.setdefault("VERIFY_TOKEN", "test_verify")
os.environ.setdefault("APP_SECRET", "test_secret")
os.environ.setdefault("GITHUB_TOKEN", "test_github_token")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
os.environ.setdefault("GOOGLE_SHEET_ID", "test_sheet_id")
os.environ.setdefault("FACEBOOK_APP_ID", "123")
os.environ.setdefault("FACEBOOK_PAGE_ID", "456")
os.environ.setdefault("SERVER_URL", "https://test.example.com")


@pytest.fixture(autouse=True)
def mock_sheets():
    """Mock Google Sheets để không ghi thật."""
    with patch("app.sheets.append_order", return_value=None) as mock_append, \
         patch("app.sheets.get_orders_by_phone", return_value=[]) as mock_get:
        yield {"append": mock_append, "get": mock_get}


@pytest.fixture(autouse=True)
def mock_kb_search():
    """Mock knowledge base search để không cần load sentence-transformers model."""
    sample_result = (
        "Tiệm Lucky tại 97 Nguyễn Chí Thanh, Hoài Nhơn, Bình Định. "
        "Mở cửa 8:00-20:00 hàng ngày. "
        "Bánh Kem Sinh Nhật 16cm giá 220.000đ, 20cm giá 320.000đ. "
        "Đặt trước tối thiểu 2 ngày. Giao hàng trong 5km miễn phí."
    )
    with patch("app.knowledge_base.search", return_value=sample_result):
        yield


@pytest.fixture
def fresh_psid(tmp_path, monkeypatch):
    """Trả về một PSID mới và hướng data_dir về thư mục tmp để không ảnh hưởng data thật."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Invalidate settings cache
    from app import config
    config.get_settings.cache_clear()
    psid = "test_user_001"
    yield psid
    config.get_settings.cache_clear()
