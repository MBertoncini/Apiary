"""
View per il deep-linking NFC.

L'app Flutter scrive sui tag NFC un record NDEF URI del tipo:
    https://cible99.pythonanywhere.com/a/<nfc_id>

Quando il tag viene scansionato dal telefono fuori dall'app:
- Se l'app è installata e gli App Link sono verificati (assetlinks.json /
  apple-app-site-association), l'OS apre direttamente l'app.
- Altrimenti l'OS apre il browser su /a/<nfc_id>, che mostra la landing
  page con i link allo store + tentativo di apertura via custom scheme.

Le tre view qui sono volutamente public-non-auth.
"""
import json
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET


# ─────────────────────────────────────────────────────────────────────────────
# Configurazione
# ─────────────────────────────────────────────────────────────────────────────
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=it.apiary.app"
APP_STORE_URL = "https://apps.apple.com/app/idREPLACE_APP_STORE_ID"
DEEP_LINK_HOST = "cible99.pythonanywhere.com"


# I file di metadata sono serviti embedded nel codice: questo evita
# config di static files (più complicato su PythonAnywhere quando il path
# include `.well-known`) e permette di aggiornare le SHA con un redeploy.
_ASSETLINKS_JSON = [
    {
        "relation": [
            "delegate_permission/common.handle_all_urls"
        ],
        "target": {
            "namespace": "android_app",
            "package_name": "it.apiary.app",
            "sha256_cert_fingerprints": [
                # Play App Signing (Firebase / Google Play Console)
                "91:01:34:DF:57:CC:19:3A:0A:0F:FB:DB:D9:17:7F:07:65:91:41:FB:73:4D:E7:66:D6:B1:20:3D:2C:80:90:2C",
                # Upload keystore release (apiary-release.jks)
                "77:21:67:86:CD:DA:96:9E:CF:30:53:F2:F0:7B:80:CC:48:AB:B6:05:7C:5F:CB:F0:57:03:0B:D0:05:6A:F5:0A",
                # Debug keystore (Android Studio)
                "2F:2A:65:9A:8F:CA:B0:69:83:A2:C2:75:11:E4:8E:EA:1F:65:79:A9:6C:60:41:AC:56:28:74:1C:47:91:35:C7",
            ],
        },
    }
]

# Apple App Site Association — sostituire TEAM_ID e BUNDLE_ID veri prima
# di pubblicare su App Store.
_AASA = {
    "applinks": {
        "details": [
            {
                "appIDs": [
                    "REPLACE_TEAM_ID.com.example.apiaryApp"
                ],
                "components": [
                    {
                        "/": "/a/*",
                        "comment": "Apre l'app Apiary quando si scansiona un tag NFC che contiene questo URL"
                    }
                ]
            }
        ]
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────────────────────
@require_GET
def assetlinks_json(request):
    """GET /.well-known/assetlinks.json — Android App Links verification."""
    response = JsonResponse(_ASSETLINKS_JSON, safe=False)
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_GET
def apple_aasa(request):
    """GET /.well-known/apple-app-site-association — iOS Universal Links.

    Apple richiede content-type `application/json` e nessun redirect.
    """
    response = HttpResponse(
        json.dumps(_AASA),
        content_type="application/json",
    )
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_GET
def nfc_landing(request, nfc_id):
    """
    GET /a/<nfc_id>/ — landing page di fallback.

    Mostrata quando il tag NFC viene scansionato su un dispositivo:
    - Senza l'app installata
    - O prima che gli App Link siano verificati (24-48h dopo il primo
      install/aggiornamento)
    - O da iPhone non compatibili con la lettura tag in background
    """
    return render(request, "nfc/nfc_landing.html", {
        "nfc_id": nfc_id,
        "deep_link_https": f"https://{DEEP_LINK_HOST}/a/{nfc_id}",
        "deep_link_custom": f"apiary://a/{nfc_id}",
        "play_store_url": PLAY_STORE_URL,
        "app_store_url": APP_STORE_URL,
    })
