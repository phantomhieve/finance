from django.contrib import admin
from django.http import Http404
from django.urls import path, include
from django.views.generic import RedirectView

admin.site.site_header = 'Vault Administration'


def _blocked(request, *args, **kwargs):
    raise Http404


urlpatterns = [
    path('sw.js', RedirectView.as_view(url='/static/sw.js', permanent=True)),
    path('vault-manage/', admin.site.urls),
    # Block allauth endpoints we don't use (must come before the allauth include)
    path('accounts/signup/', _blocked),
    path('accounts/login/', _blocked),
    path('accounts/password/', _blocked),
    path('accounts/password/reset/', _blocked),
    path('accounts/password/reset/done/', _blocked),
    path('accounts/password/reset/key/<path:uidb36>/', _blocked),
    path('accounts/password/change/', _blocked),
    path('accounts/password/set/', _blocked),
    path('accounts/email/', _blocked),
    path('accounts/confirm-email/', _blocked),
    path('accounts/confirm-email/<str:key>/', _blocked),
    path('accounts/social/signup/', _blocked),
    path('accounts/google/login/token/', _blocked),
    path('accounts/reauthenticate/', _blocked),
    path('accounts/2fa/', _blocked),
    path('accounts/', include('allauth.urls')),
    path('portfolio/', include('portfolio.urls')),
    path('', include('tracker.urls')),
]
