from django.conf.urls import patterns, url, include
from django.contrib import admin

admin.autodiscover()

urlpatterns = patterns('',
    url(r'^admin/', include(admin.site.urls)),  # Django admin
    url(r'^api/', include('api.urls')), # Our API mirrored for session access
    url(r'^monitor/', include('monitor.urls')), # Our app that monitors Perma
    url(r'^lockss/', include('lockss.urls', namespace='lockss')), # Our app that communicates with the mirror network
    url(r'^', include('perma.urls')), # The Perma app
)

handler404 = 'perma.views.common.server_error_404'
handler500 = 'perma.views.common.server_error_500'