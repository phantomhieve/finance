from django.contrib import admin
from django.http import Http404
from django.urls import path, include
from django.views.generic import RedirectView
from django.http import JsonResponse

admin.site.site_header = 'Vault Administration'


def _blocked(request, *args, **kwargs):
    raise Http404

def oauth_discovery(request):
    base = request.build_absolute_uri('/')[:-1]
    return JsonResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/o/authorize/",
        "token_endpoint": f"{base}/o/token/",
        "registration_endpoint": f"{base}/o/register/",
        "revocation_endpoint": f"{base}/o/revoke_token/",
        "introspection_endpoint": f"{base}/o/introspect/",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["plain", "S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
        "scopes_supported": ["read", "write"],
        "service_documentation": f"{base}/",
        "logo_uri": f"{base}/static/icons/icon-512.png",
        "icon_url": f"{base}/static/icons/icon-512.png",
    })

def oauth_protected_resource(request, path=""):
    base = request.build_absolute_uri('/')[:-1]
    return JsonResponse({
        "resource": f"{base}/mcp/sse",
        "authorization_servers": [base],
        "scopes_supported": ["read", "write"],
        "bearer_methods_supported": ["header"],
        "logo_uri": f"{base}/static/icons/icon-512.png",
        "icon_url": f"{base}/static/icons/icon-512.png",
    })


urlpatterns = [
    path('.well-known/oauth-authorization-server', oauth_discovery),
    path('.well-known/oauth-authorization-server/', oauth_discovery),
    path('.well-known/openid-configuration', oauth_discovery),
    path('.well-known/openid-configuration/', oauth_discovery),
    path('.well-known/oauth-protected-resource', oauth_protected_resource),
    path('.well-known/oauth-protected-resource/', oauth_protected_resource),
    path('.well-known/oauth-protected-resource/<path:path>', oauth_protected_resource),
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
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('portfolio/', include('portfolio.urls')),
    path('jewellery/', include('jewellery.urls')),
    path('', include('tracker.urls')),
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
