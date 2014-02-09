import json
from django.core import serializers
from django.template import RequestContext
from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponse, Http404
from django.core.urlresolvers import reverse
from django.conf import settings
from django.contrib.sites.models import Site
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from datetime import datetime
import urllib2, os, logging
from urlparse import urlparse
from perma.middleware import get_url_for_host, get_main_server_host

from perma.models import Link, Asset
from perma.utils import require_group, can_be_mirrored
from ratelimit.decorators import ratelimit

logger = logging.getLogger(__name__)


class DirectTemplateView(TemplateView):
    extra_context = None

    def get_context_data(self, **kwargs):
        """ Override Django's TemplateView to allow passing in extra_context. """
        context = super(self.__class__, self).get_context_data(**kwargs)
        if self.extra_context is not None:
            for key, value in self.extra_context.items():
                if callable(value):
                    context[key] = value()
                else:
                    context[key] = value
        return context

    @method_decorator(can_be_mirrored)
    def dispatch(self, request, *args, **kwargs):
        """ Add can_be_mirrored decorator. """
        return super(DirectTemplateView, self).dispatch(request, *args, **kwargs)

def stats(request):
    """
    The global stats
    """
    
    # TODO: generate these nightly. we shouldn't be doing this for every request
    top_links_all_time = list(Link.objects.all().order_by('-view_count')[:10])

    context = RequestContext(request, {'top_links_all_time': top_links_all_time})

    return render_to_response('stats.html', context)


def single_link_main_server(request, guid):
    return single_linky(request, guid)


@can_be_mirrored
@ratelimit(method='GET', rate=settings.MINUTE_LIMIT, block='True')
@ratelimit(method='GET', rate=settings.HOUR_LIMIT, block='True')
@ratelimit(method='GET', rate=settings.DAY_LIMIT, block='True')
def single_linky(request, guid):
    """
    Given a Perma ID, serve it up. Vesting also takes place here.
    """

    if request.method == 'POST' and request.user.is_authenticated():
        Link.objects.filter(guid=guid).update(vested = True, vested_by_editor = request.user, vested_timestamp = datetime.now())

        return HttpResponseRedirect(reverse('single_linky', args=[guid]))
    else:
        canonical_guid = Link.get_canonical_guid(guid)

        if canonical_guid != guid:
            return HttpResponsePermanentRedirect(reverse('single_linky', args=[canonical_guid]))

        context = None
        # User requested archive type
        serve_type = 'live'

        if 'type' in request.REQUEST:
            requested_type = request.REQUEST['type']

            if requested_type == 'image':
                serve_type = 'image'
            elif requested_type == 'pdf':
                serve_type = 'pdf'
            elif requested_type == 'source':
                serve_type = 'source'
            elif requested_type == 'text':
                serve_type = 'text'

        try:
            link = Link.objects.get(guid=guid)
        except Link.DoesNotExist:
            if settings.MIRROR_SERVER:
                # if we can't find the Link, and we're a mirror server, try fetching it from main server
                try:
                    req = urllib2.Request(get_url_for_host(request,
                                                           get_main_server_host(request),
                                                           reverse('single_link_main_server', args=[guid])+"?type="+serve_type),
                                          headers={'Content-Type': 'application/json'})
                    link_json = urllib2.urlopen(req)
                except urllib2.HTTPError:
                    raise Http404
                context = json.loads(link_json.read())
                context['asset'] = serializers.deserialize("json", context['asset']).next().object
                context['linky'] = serializers.deserialize("json", context['linky']).next().object
                print context
            else:
                raise Http404

    if not context:
        # Increment the view count if we're not the referrer
        parsed_url = urlparse(request.META.get('HTTP_REFERER', ''))
        current_site = Site.objects.get_current()
        
        if not current_site.domain in parsed_url.netloc:
            link.view_count += 1
            link.save()

        asset = Asset.objects.get(link=link)


        text_capture = None

        if serve_type == 'text':
            if asset.text_capture and asset.text_capture != 'pending':
                path_elements = [settings.GENERATED_ASSETS_STORAGE, asset.base_storage_path, asset.text_capture]
                file_path = os.path.sep.join(path_elements)

                with open(file_path, 'r') as f:
                    text_capture = f.read()
            
        # If we are going to serve up the live version of the site, let's make sure it's iframe-able
        display_iframe = False
        if serve_type == 'live':
            try:
                response = urllib2.urlopen(link.submitted_url)
                if 'X-Frame-Options' in response.headers:
                    # TODO actually check if X-Frame-Options specifically allows requests from us
                    display_iframe = False
                else:
                    display_iframe = True
            except urllib2.URLError:
                # Something is broken with the site, so we might as well display it in an iFrame so the user knows
                display_iframe = True

        asset= Asset.objects.get(link__guid=link.guid)

        created_datestamp = link.creation_timestamp
        pretty_date = created_datestamp.strftime("%B %d, %Y %I:%M GMT")

        context = {'linky': link, 'asset': asset, 'pretty_date': pretty_date, 'next': request.get_full_path(),
                   'display_iframe': display_iframe, 'serve_type': serve_type, 'text_capture': text_capture,
                   'asset_host':''}

    if request.META.get('CONTENT_TYPE') == 'application/json':
        context['asset_host'] = "http%s://%s" % ('s' if request.is_secure() else '', get_main_server_host(request))
        context['asset'] = serializers.serialize("json", [context['asset']], fields=['text_capture','image_capture','pdf_capture','warc_capture','base_storage_path'])
        context['linky'] = serializers.serialize("json", [context['linky']], fields=['dark_archived','guid','vested','view_count','creation_timestamp','submitted_url','submitted_title'])
        return HttpResponse(json.dumps(context), content_type="application/json")

    return render_to_response('single-link.html', context, RequestContext(request))


def rate_limit(request, exception):
    """
    When a user hits a rate limit, send them here.
    """
    
    return render_to_response("rate_limit.html")
