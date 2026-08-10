from rest_framework import generics, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import User
from .permissions import IsAdmin
from .serializers import UserCreateSerializer, UserSerializer


class MeView(generics.RetrieveUpdateAPIView):
    """Profil de l'utilisateur connecté."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ModelViewSet):
    """Gestion des utilisateurs — admin uniquement (RF-62)."""

    queryset = User.objects.all().order_by("email")
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer
