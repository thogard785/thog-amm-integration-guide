import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from capture_quotes import RPC


class CaptureRpcTests(unittest.TestCase):
    def test_single_and_batch_rate_limits_retry_the_same_pinned_request(self):
        for batch in (False, True):
            limited = {'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32007, 'message': 'rate limit'}}
            success = {'jsonrpc': '2.0', 'id': 1, 'result': '0x1234'}
            payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'eth_call', 'params': [{}, '0x64']}
            if batch:
                limited, success, payload = [limited], [success], [payload]
            with patch('urllib.request.urlopen', side_effect=[io.BytesIO(json.dumps(limited).encode()), io.BytesIO(json.dumps(success).encode())]) as request, patch('time.sleep'):
                self.assertEqual(RPC('http://unused').send(payload), success)
                self.assertEqual(request.call_args_list[0].args[0].data, request.call_args_list[1].args[0].data)

    def test_contract_reverts_are_not_retried(self):
        response = {'jsonrpc': '2.0', 'id': 1, 'error': {'code': 3, 'message': 'execution reverted'}}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as request:
            self.assertEqual(RPC('http://unused').send({}), response)
            self.assertEqual(request.call_count, 1)

    def test_existing_capture_is_rejected_before_any_network_access(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'fixture.gz'
            output.write_bytes(b'existing reviewed fixture')
            for script in ['capture_quotes.py', 'capture_events.py']:
                result = subprocess.run([sys.executable, str(Path(__file__).with_name(script)), '--rpc', 'http://127.0.0.1:1', '--output', str(output)], capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b'output already exists', result.stderr)
                self.assertEqual(output.read_bytes(), b'existing reviewed fixture')


if __name__ == '__main__':
    unittest.main()
