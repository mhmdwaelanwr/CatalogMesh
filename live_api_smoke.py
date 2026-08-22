#!/usr/bin/env python3
"""Opt-in live credential check. Never prints keys or sends product images."""
from providers import configured_rest_providers
from sorter_core import load_api_keys, load_env_file, validate_gemini_key, DEFAULT_ENV_FILE
def main()->int:
    load_env_file(DEFAULT_ENV_FILE); failures=0; gemini=load_api_keys(); rest=configured_rest_providers()
    for i,key in enumerate(gemini,1):
        ok,_=validate_gemini_key(key); print(f"gemini key {i}: {'OK' if ok else 'FAILED'}"); failures+=not ok
    for provider in rest:
        for i,(ok,_) in enumerate(provider.validate_all(),1):
            print(f"{provider.name} key {i}: {'OK' if ok else 'FAILED'}"); failures+=not ok
    if not gemini and not rest: print("No live API keys configured."); return 2
    return 1 if failures else 0
if __name__=="__main__": raise SystemExit(main())
