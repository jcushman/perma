# Generated by Django 4.2.13 on 2024-05-20 14:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('perma', '0040_folder_cached_has_children'),
    ]

    operations = [
        migrations.AddField(
            model_name='folder',
            name='tree_root',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='perma.folder'),
        ),
        migrations.RunSQL(
            sql="UPDATE perma_folder SET tree_root_id = CAST(SPLIT_PART(cached_path, '-', 1) AS INTEGER) WHERE cached_path != '';",
            reverse_sql=migrations.RunSQL.noop,
            elidable=True
        ),
    ]


