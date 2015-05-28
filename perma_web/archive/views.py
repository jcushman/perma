import hashlib
from mimetypes import MimeTypes
import os
import re
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from django.core.files.storage import default_storage
from hanzo import warctools

from django.http import HttpResponse, HttpResponseBadRequest, Http404
from django.shortcuts import get_object_or_404, render
from api.validations import get_mime_type

from perma.models import Link, Asset


def search(request):
    strip_guid_re = re.compile('[^0-9A-Za-z]+')
    updates = Link.objects.order_by('creation_timestamp').select_related('assets')  # todo -- order by update date

    # apply from_date
    if 'updates_since' in request.GET:
        from_date = datetime.utcfromtimestamp(int(request.GET['updates_since']))
        updates = updates.filter(creation_timestamp__gte=from_date)  # todo -- search by update date

    # apply Archival Unit limits
    month = int(request.GET['creation_month'])
    year = int(request.GET['creation_year'])
    updates = updates.filter(creation_timestamp__year=year, creation_timestamp__month=month)

    # apply offset
    offset = int(request.GET.get('offset', 0))
    updates = updates[offset:offset+1000]

    # export file names
    files_to_index = []
    for update in updates:
        path = update.assets.first().warc_storage_path()
        files_to_index.extend([
            '%s/%s.warc.gz' % (path, update.guid),
            '%s/%s_metadata.json' % (path, update.guid),
        ])

    return HttpResponse("\n".join(files_to_index), content_type="text/plain")


def fetch_warc(request, path, guid):
    # TODO: check that path matches start of filename

    # setup for all assets
    mime = MimeTypes()

    asset = get_object_or_404(Asset, link_id=guid)

    out = open('temp.warc.gz', 'wb')

    def write_resource_record(file_path, url, content_type):
        data = default_storage.open(file_path).read()
        warc_date = default_storage.created_time(file_path)

        headers = [
            (warctools.WarcRecord.TYPE, warctools.WarcRecord.RESOURCE),
            (warctools.WarcRecord.ID, warctools.WarcRecord.random_warc_uuid()),
            (warctools.WarcRecord.DATE, warctools.warc.warc_datetime_str(warc_date)),
            (warctools.WarcRecord.URL, url),
            (warctools.WarcRecord.BLOCK_DIGEST, b'sha1:%s' % hashlib.sha1(data).hexdigest())
        ]
        record = warctools.WarcRecord(headers=headers, content=(content_type, data))
        record.write_to(out, gzip=True)

    # build warcinfo header
    headers = [
        (warctools.WarcRecord.ID, warctools.WarcRecord.random_warc_uuid()),
        (warctools.WarcRecord.TYPE, warctools.WarcRecord.WARCINFO),
        (warctools.WarcRecord.DATE, warctools.warc.warc_datetime_str(asset.link.creation_timestamp))
    ]
    warcinfo_fields = [
        b'operator: Perma.cc',
        b'format: WARC File Format 1.0',
        b'Perma-GUID: %s' % guid,
    ]
    data = b'\r\n'.join(warcinfo_fields) + b'\r\n'
    warcinfo_record = warctools.WarcRecord(headers=headers, content=(b'application/warc-fields', data))
    warcinfo_record.write_to(out, gzip=True)

    # write image capture
    if asset.image_capture and ('cap' in asset.image_capture or 'upload' in asset.image_capture):
        file_path = os.path.join(asset.base_storage_path, asset.image_capture)
        mime_type = get_mime_type(asset.image_capture)
        write_resource_record(file_path, "file:///%s/%s" % (guid, asset.image_capture), mime_type)

    # write PDF capture
    if asset.pdf_capture and ('cap' in asset.pdf_capture or 'upload' in asset.pdf_capture):
        file_path = os.path.join(asset.base_storage_path, asset.pdf_capture)
        write_resource_record(file_path, "file:///%s/%s" % (guid, asset.pdf_capture), 'application/pdf')

    # write text capture
    if asset.text_capture == 'instapaper_cap.html':
        file_path = os.path.join(asset.base_storage_path, asset.text_capture)
        write_resource_record(file_path, "file:///%s/%s" % (guid, asset.text_capture), 'text/html')

    if asset.warc_capture:
        # write WARC capture
        if asset.warc_capture == 'archive.warc.gz':
            file_path = os.path.join(asset.base_storage_path, asset.warc_capture)
            with default_storage.open(file_path) as warc_file:
                while True:
                    data = warc_file.read(1024*100)
                    if not data:
                        break
                    out.write(data)

        # write wget capture
        elif asset.warc_capture == 'source/index.html':
            for root, dirs, files in default_storage.walk(os.path.join(asset.base_storage_path, 'source')):
                rel_path = root.split(asset.base_storage_path, 1)[-1]
                for file_name in files:
                    mime_type = mime.guess_type(file_name)[0]
                    write_resource_record(os.path.join(root, file_name), "file:///%s%s/%s" % (guid, rel_path, file_name), mime_type)


    return HttpResponse(file_type)


def permission(request):
    return HttpResponse("LOCKSS system has permission to collect, preserve, and serve this open access Archival Unit")


def titledb(request):
    # build list of all year/month combos since we started, in the form [[2014, "01"],[2014, "02"],...]
    first_archive_date = Link.objects.order_by('creation_timestamp')[0].creation_timestamp
    start_month = date(year=first_archive_date.year, month=first_archive_date.month, day=1)
    today = date.today()
    archival_units = []
    while start_month <= today:
        archival_units.append([start_month.year, '%02d' % start_month.month])
        start_month += relativedelta(months=1)

    return render(request, 'archive/titledb.xml', {
        'archival_units': archival_units,
    })