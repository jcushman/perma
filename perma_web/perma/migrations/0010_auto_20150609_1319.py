# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from api.validations import get_mime_type


def migrate_assets(apps, schema_editor):
    # Update CDXLines to point to Link instead of Asset
    CDXLine = apps.get_model("perma", "CDXLine")
    for line in CDXLine.objects.all().select_related('asset'):
        line.link_id = line.asset.link_id
        line.save()

    # Create Captures
    Asset = apps.get_model("perma", "Asset")
    Capture = apps.get_model("perma", "Capture")
    for asset in Asset.objects.select_related('link').all():
        if asset.pdf_capture:
            status = 'success' if asset.pdf_capture.endswith(
                '.pdf') else 'pending' if asset.pdf_capture == 'pending' else 'failed'
            Capture(
                link_id=asset.link_id,
                role='primary',
                status=status,
                url="file:///%s/%s" % (asset.link_id, asset.pdf_capture) if status == 'success' else None,
                record_type="resource",
                content_type="application/pdf",
                user_upload="upload" in asset.pdf_capture,
            ).save()

        elif asset.image_capture:
            upload = "upload" in asset.image_capture
            status = 'success' if 'cap' in asset.image_capture or 'upload' in asset.image_capture else 'pending' if asset.image_capture == 'pending' else 'failed'
            Capture(
                link_id=asset.link_id,
                role='primary' if upload else 'screenshot',
                status=status,
                url="file:///%s/%s" % (asset.link_id, asset.image_capture) if status == 'success' else None,
                record_type="resource",
                content_type=get_mime_type(asset.image_capture),
                user_upload=upload,
            ).save()

        if asset.warc_capture:
            is_warc = asset.warc_capture == 'archive.warc.gz'
            status = 'success' if asset.warc_capture == 'archive.warc.gz' or asset.warc_capture == 'source/index.html' else 'pending' if asset.warc_capture == 'pending' else 'failed'
            url = None
            if status == 'success':
                url = asset.link.submitted_url if is_warc else "file:///%s/source/index.html"
            Capture(
                link_id=asset.link_id,
                role='primary',
                status=status,
                url=url,
                record_type="response" if is_warc else "resource",
                content_type="text/html",
            ).save()


class Migration(migrations.Migration):

    dependencies = [
        ('perma', '0009_auto_20150609_1540'),
    ]

    operations = [
        migrations.RunPython(migrate_assets),
    ]
