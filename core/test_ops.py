"""Test degli endpoint di servizio per i bot (core/ops_views.py).

Eseguire con:  python manage.py test core.test_ops
"""

import os
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase


class OpsEndpointTests(TestCase):
    TOKEN = 'token-di-prova'

    def _get(self, url, token=TOKEN, **params):
        headers = {'HTTP_X_OPS_TOKEN': token} if token is not None else {}
        return self.client.get(url, params, **headers)

    def test_senza_ops_token_configurato_risponde_404(self):
        with mock.patch.dict(os.environ, {'OPS_TOKEN': ''}):
            self.assertEqual(self._get('/api/v1/ops/status/').status_code, 404)

    def test_token_errato_risponde_403(self):
        with mock.patch.dict(os.environ, {'OPS_TOKEN': self.TOKEN}):
            self.assertEqual(self._get('/api/v1/ops/status/', token='sbagliato').status_code, 403)
            self.assertEqual(self._get('/api/v1/ops/stats/', token=None).status_code, 403)

    def test_status(self):
        with mock.patch.dict(os.environ, {'OPS_TOKEN': self.TOKEN}):
            resp = self._get('/api/v1/ops/status/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['db_ok'])
        self.assertIn('pending', data['migrations'])
        self.assertIn('commit', data)

    def test_stats_solo_numeri(self):
        get_user_model().objects.create_user('apicoltore', password='x')
        with mock.patch.dict(os.environ, {'OPS_TOKEN': self.TOKEN}):
            resp = self._get('/api/v1/ops/stats/', days=7)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['periodo_giorni'], 7)
        self.assertEqual(data['utenti']['totale'], 1)
        self.assertIn('ControlloArnia', data['modelli'])
        self.assertNotIn('apicoltore', resp.content.decode())

    def test_errors_filtra_per_since_e_tiene_i_traceback(self):
        righe = [
            '2026-11-18 09:00:00,100: vecchio errore',
            '2026-11-18 10:00:00,200: Traceback (most recent call last):',
            '  File "x.py", line 1, in <module>',
            '2026-11-18 10:00:00,300: ValueError: nuovo',
        ]
        with tempfile.NamedTemporaryFile('w', suffix='.log', delete=False, encoding='utf-8') as fh:
            fh.write('\n'.join(righe) + '\n')
            path = fh.name
        try:
            env = {'OPS_TOKEN': self.TOKEN, 'OPS_ERROR_LOG': path}
            with mock.patch.dict(os.environ, env):
                resp = self._get('/api/v1/ops/errors/', since='2026-11-18 09:30:00')
            data = resp.json()
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(data['lines'], righe[1:])
            self.assertEqual(data['last_ts'], '2026-11-18 10:00:00')
        finally:
            os.unlink(path)
