from django.utils import translation
from rest_framework.response import Response
from rest_framework.views import APIView

from damaged_object.dashboard_analytics import (
    _parse_int,
    get_composition_stats,
    get_dashboard_overview,
    get_dynamics_stats,
    get_map_inspector,
    get_map_points,
    get_operational_feed,
    get_plan_execution_stats,
    get_regional_ranking,
    resolve_scope,
)


class DashboardOverviewStatView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        return Response(data=get_dashboard_overview(scope), status=200)


class DashboardDynamicsStatView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        period = request.query_params.get('period', 'monthly')
        if period not in ('daily', 'monthly', 'yearly'):
            period = 'monthly'
        return Response(data=get_dynamics_stats(scope, period=period), status=200)


class DashboardCompositionStatView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        return Response(data=get_composition_stats(scope), status=200)


class DashboardRegionalRankingView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        return Response(data=get_regional_ranking(scope), status=200)


class DashboardPlanExecutionView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        return Response(data=get_plan_execution_stats(scope), status=200)


class DashboardOperationalFeedView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        return Response(data=get_operational_feed(scope), status=200)


class DashboardMapPointsView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        return Response(data=get_map_points(scope), status=200)


class DashboardMapInspectorView(APIView):
    def get(self, request, *args, **kwargs):
        translation.activate(request.LANGUAGE_CODE)
        scope = resolve_scope(request)
        target_type = request.query_params.get('target_type', scope['scope_level'])
        target_id = _parse_int(request.query_params.get('target_id'))
        return Response(
            data=get_map_inspector(scope, target_type=target_type, target_id=target_id),
            status=200,
        )
