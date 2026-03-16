from rest_framework.permissions import BasePermission


class IsOwnerOrGroupMember(BasePermission):
    """Permette accesso solo ai propri dati o dati del proprio gruppo."""

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'proprietario'):
            return obj.proprietario == request.user
        if hasattr(obj, 'apicoltore'):
            return obj.apicoltore == request.user
        if hasattr(obj, 'utente'):
            return obj.utente == request.user
        if hasattr(obj, 'creatore'):
            return obj.creatore == request.user
        if hasattr(obj, 'apiario'):
            return obj.apiario.proprietario == request.user
        return False
