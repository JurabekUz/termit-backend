from rest_framework import permissions

from account.models import UserRoles


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == UserRoles.ADMIN


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
