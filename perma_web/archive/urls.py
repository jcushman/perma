from django.conf.urls import patterns, url

urlpatterns = patterns('archive.views',
    url(r'^search/?$', 'search', name='search'),
    url(r'^fetch/(?P<path>(?:[A-Za-z0-9]{2}/)+)(?P<guid>.+)\.warc\.gz$', 'fetch_warc', name='fetch_warc'),
    url(r'^fetch/(?P<path>(?:[A-Za-z0-9]{2}/)+)(?P<guid>.+)_metadata.json$', 'fetch_metadata', name='fetch_metadata'),
    url(r'^permission/$', 'permission', name='permission'),
    url(r'^titledb.xml$', 'titledb', name='titledb'),
)