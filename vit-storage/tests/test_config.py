import os
from tachyon.core.config import settings, get_env, get_int_env

def test_settings_default():
    assert settings.PORT == 8080
    assert settings.ENVIRONMENT == "development"

def test_get_env_helpers():
    # Test setting fallback
    assert get_env("PORT") == "8080"
    assert get_int_env("PORT") == 8080

    # Test active override fallback
    os.environ["MOCK_PORT_OVERRIDE"] = "9999"
    assert get_env("MOCK_PORT_OVERRIDE") == "9999"
    assert get_int_env("MOCK_PORT_OVERRIDE") == 9999
