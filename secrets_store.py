from __future__ import annotations
import os
SERVICE="product-sorter-pro"
SECRET_NAMES=tuple(f"{provider}_API_KEY_{i}" for provider in ("GEMINI","OPENAI","ANTHROPIC") for i in range(1,5))
def save(values:dict[str,str])->bool:
    try:
        import keyring
        for name in SECRET_NAMES:
            if values.get(name): keyring.set_password(SERVICE,name,values[name])
        return True
    except Exception:return False
def load_into_environment()->bool:
    try:
        import keyring
        for name in SECRET_NAMES:
            value=keyring.get_password(SERVICE,name)
            if value: os.environ.setdefault(name,value)
        return True
    except Exception:return False
