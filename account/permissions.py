from rest_framework import permissions

from account.models import UserRoles


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(user and user.is_authenticated and (user.role == UserRoles.ADMIN or user.is_superuser))


class IsCenterDirector(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == UserRoles.CD


class IsCenterManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == UserRoles.CM


class IsRegionalManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == UserRoles.RM


class IsMinistryEmployee(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == UserRoles.ME


class IsLegalEntity(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == UserRoles.LE


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or request.user.role == UserRoles.ADMIN


class IsAdminOrCenterDirector(permissions.BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(
            user
            and user.is_authenticated
            and (user.role in (UserRoles.ADMIN, UserRoles.CD) or user.is_superuser)
        )
