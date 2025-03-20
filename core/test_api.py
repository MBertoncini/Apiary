#!/usr/bin/env python3
import requests
import json
import sys

# Configurazione
BASE_URL = "https://cible99.pythonanywhere.com/api/v1"
USERNAME = "Michele"  # Inserisci il tuo username
PASSWORD = "D0m0d0ss0la2629!!"  # Inserisci la tua password

def login():
    """Effettua il login e restituisce il token di accesso"""
    url = f"{BASE_URL}/token/"
    
    data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        return token_data.get("access")
    except requests.exceptions.RequestException as e:
        print(f"Errore durante il login: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Codice status: {e.response.status_code}")
            print(f"Contenuto risposta: {e.response.text}")
        return None

def test_endpoint(token, endpoint):
    """Testa un endpoint dell'API"""
    url = f"{BASE_URL}/{endpoint}"
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        return True, data
    except requests.exceptions.RequestException as e:
        error_msg = f"Errore durante la richiesta a {endpoint}: {e}"
        if hasattr(e, 'response') and e.response:
            error_msg += f"\nCodice status: {e.response.status_code}"
            error_msg += f"\nContenuto risposta: {e.response.text[:500]}"  # Limita l'output
        return False, error_msg

def main():
    print(f"Test delle API di backend su {BASE_URL}")
    print("-" * 80)
    
    # Effettua il login
    print("Effettuo il login...")
    token = login()
    
    if not token:
        print("Login fallito. Impossibile continuare i test.")
        sys.exit(1)
    
    print("Login effettuato con successo! ✓")
    print("-" * 80)
    
    # Lista degli endpoint da testare
    endpoints = [
        "users/me/",
        "apiari/",
        "arnie/",
        "controlli/",
        "regine/",
        "fioriture/",
        "trattamenti/",
        "pagamenti/",
        "quote/"
    ]
    
    # Test degli endpoint
    failures = 0
    for endpoint in endpoints:
        print(f"Test endpoint: {endpoint}")
        success, result = test_endpoint(token, endpoint)
        
        if success:
            if isinstance(result, list):
                count = len(result)
            elif isinstance(result, dict) and "results" in result:
                count = len(result["results"])
            else:
                count = 1 if result else 0
            
            print(f"  Successo! ✓ ({count} elementi)")
        else:
            print(f"  Fallito! ✗")
            print(f"  {result}")
            failures += 1
        
        print("-" * 80)
    
    # Riepilogo
    if failures == 0:
        print("Tutti i test sono stati completati con successo! ✓")
    else:
        print(f"{failures} test falliti su {len(endpoints)}.")
        print("Controlla i log per maggiori dettagli.")

if __name__ == "__main__":
    main()