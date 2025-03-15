#!/usr/bin/env python
"""
Script di test completo per trovare gli endpoint corretti dell'API.
"""
import requests
import json
from datetime import datetime

# Configurazione base
SERVER_URL = 'https://Cible99.pythonanywhere.com'
USERNAME = 'Michele'
PASSWORD = 'D0m0d0ss0la2629!!'

def test_endpoint(url, method='GET', data=None, headers=None):
    """Test generico per qualsiasi endpoint."""
    print(f"Testing: {url}")
    
    try:
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers)
        elif method.upper() == 'POST':
            response = requests.post(url, data=data, headers=headers)
        else:
            print(f"Metodo {method} non supportato")
            return None
        
        print(f"  Status code: {response.status_code}")
        
        if response.status_code < 400:  # Se è una risposta di successo
            try:
                json_data = response.json()
                print(f"  JSON response ✓")
                return response
            except:
                print(f"  Non è una risposta JSON")
                print(f"  Content: {response.text[:100]}...")
                return response
        else:
            print(f"  Error response: {response.text[:100]}...")
            return None
            
    except Exception as e:
        print(f"  Exception: {str(e)}")
        return None

def find_auth_endpoint():
    """Tenta di trovare l'endpoint di autenticazione corretto."""
    print("\n🔑 Cercando l'endpoint di autenticazione...")
    
    # Lista di possibili percorsi per l'endpoint di autenticazione
    auth_paths = [
        '/api/v1/token/',
        '/api/token/',
        '/api/auth/token/',
        '/api/v1/auth/token/',
        '/token/',
        '/api-auth/token/',
        '/api/login/',
        '/api/v1/login/',
        '/api-token-auth/'
    ]
    
    # Dati di autenticazione
    auth_data = {
        'username': USERNAME,
        'password': PASSWORD
    }
    
    for path in auth_paths:
        url = f"{SERVER_URL}{path}"
        response = test_endpoint(url, method='POST', data=auth_data)
        
        if response and response.status_code < 400:
            try:
                data = response.json()
                if 'access' in data or 'token' in data:
                    print(f"✅ Endpoint di autenticazione trovato: {url}")
                    return url, data.get('access') or data.get('token')
            except:
                pass
    
    print("❌ Nessun endpoint di autenticazione trovato")
    return None, None

def check_api_structure():
    """Controlla la struttura generale dell'API per vedere quali endpoint sono disponibili."""
    print("\n🔍 Verificando la struttura dell'API...")
    
    # Lista di percorsi base comuni da testare
    base_paths = [
        '',
        '/api',
        '/api/v1',
        '/api/docs',
        '/api/swagger',
        '/api/redoc',
        '/admin'
    ]
    
    for path in base_paths:
        url = f"{SERVER_URL}{path}"
        test_endpoint(url)

def test_known_paths(token=None):
    """Testa alcuni endpoint noti per verificare se l'API è accessibile."""
    print("\n🔍 Testando endpoint noti...")
    
    # Lista di percorsi specifici da testare
    endpoints = [
        '/api/v1/apiari/',
        '/api/apiari/',
        '/api/v1/arnie/',
        '/api/arnie/',
        '/api/v1/sync/',
        '/api/sync/'
    ]
    
    headers = None
    if token:
        headers = {'Authorization': f'Bearer {token}'}
    
    for path in endpoints:
        url = f"{SERVER_URL}{path}"
        test_endpoint(url, headers=headers)

def main():
    """Funzione principale per eseguire i test."""
    print("🐝 Test Completo dell'API Apiario Manager")
    print("----------------------------------------")
    
    # Step 1: Controlla la struttura dell'API
    check_api_structure()
    
    # Step 2: Trova l'endpoint di autenticazione
    auth_url, token = find_auth_endpoint()
    
    # Step 3: Testa gli endpoint noti (se abbiamo un token)
    test_known_paths(token)
    
    print("\nTest completati!")
    
    if auth_url:
        print(f"\n✅ Endpoint di autenticazione corretto: {auth_url}")
        print("Modifica l'app Flutter per utilizzare questo endpoint.")
    else:
        print("\n❌ Non è stato possibile trovare l'endpoint di autenticazione.")
        print("Verifica che il server API sia configurato correttamente.")

if __name__ == "__main__":
    main()