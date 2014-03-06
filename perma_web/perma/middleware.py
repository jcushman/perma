import json

from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.conf import settings
from django.http import HttpResponsePermanentRedirect
from django.utils.functional import SimpleLazyObject

from perma.models import LinkUser

### helpers ###

def get_main_server_host(request):
    """
        Given request, return the host domain with the MIRROR_USERS_SUBDOMAIN included.
    """
    host = request.get_host()
    if not host.startswith(settings.MIRROR_USERS_SUBDOMAIN + '.'):
        host = settings.MIRROR_USERS_SUBDOMAIN + '.' + host
    return host

def get_generic_server_host(request):
    """
        Given request, return the host domain with the MIRROR_USERS_SUBDOMAIN excluded.
    """
    host = request.get_host()
    if host.startswith(settings.MIRROR_USERS_SUBDOMAIN + '.'):
        host = host[len(settings.MIRROR_USERS_SUBDOMAIN + '.'):]
    return host

def get_url_for_host(request, host, url=None):
    """
        Given request, return a version of url with host replaced.

        If url is None, the url for this request will be used.
    """
    return request.build_absolute_uri(location=url).replace(request.get_host(), host, 1)


### create fake request.user model from cookie on mirror servers ###

class FakeLinkUser(LinkUser):
    is_authenticated = lambda self: True
    groups = None

    def __init__(self, *args, **kwargs):
        self.groups = Group.objects.filter(pk__in=kwargs.pop('groups'))
        super(FakeLinkUser, self).__init__(*args, **kwargs)

def get_user(request):
    """
        When request.user is viewed on mirror server, try to build it from cookie. """
    if not hasattr(request, '_cached_user'):
        user_info = request.COOKIES.get(settings.MIRROR_COOKIE_NAME)
        if user_info:
            try:
                user_info = json.loads(user_info)
                request._cached_user = FakeLinkUser(**user_info)
            except Exception, e:
                print "Error loading mirror user:", e
        if not request._cached_user:
            request._cached_user = AnonymousUser()
    return request._cached_user

class MirrorAuthenticationMiddleware(AuthenticationMiddleware):
    def process_request(self, request):
        if not settings.MIRROR_SERVER:
            return super(MirrorAuthenticationMiddleware, self).process_request(request)
        request.user = SimpleLazyObject(lambda: get_user(request))


### forwarding ###

class MirrorForwardingMiddleware(object):
    def process_view(self, request, view_func, view_args, view_kwargs):
        """
            If we're doing mirroring, make sure that the user is directed to the main domain
            or the generic domain depending on whether the view they requested @can_be_mirrored.
        """
        if settings.MIRRORING_ENABLED:
            host = request.get_host()
            main_server_host = get_main_server_host(request)
            can_be_mirrored = getattr(view_func, 'can_be_mirrored', False)

            if can_be_mirrored and host == main_server_host:
                return HttpResponsePermanentRedirect(get_url_for_host(request, get_generic_server_host(request)))

            elif not can_be_mirrored and (settings.MIRROR_SERVER or host != main_server_host):
                return HttpResponsePermanentRedirect(get_url_for_host(request, get_main_server_host(request)))
