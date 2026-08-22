import os
import unittest
from unittest.mock import patch

from providers import RestProviderPool, configured_rest_providers, load_provider_keys
from sorter_core import call_rest_pool


class ProviderKeyPoolTests(unittest.TestCase):
    @patch.dict(os.environ,{"OPENAI_API_KEY_1":"one","OPENAI_API_KEY_2":"two","OPENAI_API_KEY":"legacy"},clear=True)
    def test_numbered_keys_take_priority_and_legacy_remains_compatible(self):
        self.assertEqual(load_provider_keys("openai"),["one","two","legacy"])

    @patch.dict(os.environ,{"AI_PROVIDERS":"openai","OPENAI_API_KEY_1":"one","OPENAI_API_KEY_2":"two"},clear=True)
    def test_configures_one_pool_with_multiple_keys(self):
        pools=configured_rest_providers()
        self.assertEqual(len(pools),1)
        self.assertEqual(len(pools[0].clients),2)

    def test_rotates_on_quota_and_succeeds(self):
        class Client:
            def __init__(self,fail): self.fail=fail; self.last_usage={}
            def generate(self,*args):
                if self.fail: raise RuntimeError("429 rate_limit")
                return '{"items":[]}'
        class Pool:
            name="openai"; model="test"; index=0; last_usage={}
            def __init__(self): self.clients=[Client(True),Client(False)]
            @property
            def client(self): return self.clients[self.index]
            def rotate(self): self.index=(self.index+1)%len(self.clients); return True
        with patch("sorter_core.call_rest_provider",return_value={"items":[]} ) as call:
            call.side_effect=[RuntimeError("429 rate_limit"),{"items":[]}]
            result=call_rest_pool(Pool(),[],"",0)
        self.assertEqual(result,{"items":[]})
        self.assertEqual(call.call_count,2)

    def test_four_exhausted_keys_accept_a_fifth_for_current_run(self):
        pool=RestProviderPool("openai",["1","2","3","4"],"test")
        with patch("sorter_core.call_rest_provider") as call, patch("sorter_core.request_new_api_key",return_value="5") as ask:
            call.side_effect=[RuntimeError("429 quota") for _ in range(4)]+[{"items":[]}]
            self.assertEqual(call_rest_pool(pool,[],"",0),{"items":[]})
        self.assertEqual(len(pool.clients),5)
        self.assertEqual(call.call_count,5)
        ask.assert_called_once()


if __name__=="__main__": unittest.main()
