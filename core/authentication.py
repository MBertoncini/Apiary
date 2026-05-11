from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthenticationWithActivity(JWTAuthentication):
    """Aggiorna `last_login` ad ogni richiesta API autenticata (throttled).

    Why: SimpleJWT aggiorna `last_login` solo all'emissione del token (`/token/`),
    mai sul refresh. Con `REFRESH_TOKEN_LIFETIME = 3650 giorni` l'app mobile
    può non rifare un login completo per anni, lasciando `last_login` a NULL
    per la maggioranza degli utenti. Qui lo aggiorniamo sul traffico reale così
    l'admin mostra l'ultima attività effettiva.
    """

    ACTIVITY_THROTTLE = timedelta(hours=1)

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        self._touch_last_login(user)
        return user, validated_token

    def _touch_last_login(self, user):
        now = timezone.now()
        if user.last_login and (now - user.last_login) < self.ACTIVITY_THROTTLE:
            return
        type(user).objects.filter(pk=user.pk).update(last_login=now)
        user.last_login = now
