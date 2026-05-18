import logging

from django.contrib.auth import get_user_model

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

User = get_user_model()
logger = logging.getLogger(__name__)


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Disable all non-SSO signup."""

    def is_open_for_signup(self, request):
        return False


class PreExistingEmailAdapter(DefaultSocialAccountAdapter):
    """Only allow Google SSO for emails already registered in the admin panel."""

    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('email', '').lower().strip()
        if not email:
            messages.error(request, 'No email received from Google.')
            raise ImmediateHttpResponse(redirect('login'))

        if not sociallogin.account.extra_data.get('email_verified', False):
            messages.error(request, 'Your Google email is not verified.')
            raise ImmediateHttpResponse(redirect('login'))

        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            logger.warning('SSO login denied for unregistered email: %s', email)
            messages.error(
                request,
                'Access denied. Your email is not authorized to use this application.',
            )
            raise ImmediateHttpResponse(redirect('login'))
        except User.MultipleObjectsReturned:
            logger.error('Multiple users share email: %s', email)
            messages.error(request, 'Configuration error. Please contact the administrator.')
            raise ImmediateHttpResponse(redirect('login'))

        if sociallogin.is_existing:
            return

        sociallogin.connect(request, user)

    def is_open_for_signup(self, request, sociallogin):
        return False
