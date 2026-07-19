from django.urls import path
from appeal.views import (
    AppealListView, AppealCheckingView, AppealObjectCheckingView,
    AppealMahallaCreateView, AppealMahallaRetrieveView, AppealMahallaObjectRetrieveView,
    AppealOpenAreaCreateView, AppealOpenAreaRetrieveView, AppealOpenAreaObjectRetrieveView


)

urlpatterns = [
    path('appeals', AppealListView.as_view()),
    path('appeals/<int:pk>/checking', AppealCheckingView.as_view()),
    path('appeals/objects/<int:pk>/checking', AppealObjectCheckingView.as_view()),

    path('appeals/mahalla', AppealMahallaCreateView.as_view()),
    path('appeals/mahalla/<int:pk>', AppealMahallaRetrieveView.as_view()),
    path('appeals/mahalla/objects/<int:pk>', AppealMahallaObjectRetrieveView.as_view()),

    path('appeals/open-area', AppealOpenAreaCreateView.as_view()),
    path('appeals/open-area/<int:pk>', AppealOpenAreaRetrieveView.as_view()),
    path('appeals/open-area/objects/<int:pk>', AppealOpenAreaObjectRetrieveView.as_view()),
]
